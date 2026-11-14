"""Burn-scar detection from Sentinel-2 (dNBR) and NISAR L-band SAR, fused.

Spectral bands used
-------------------
Sentinel-2 L2A (Microsoft Planetary Computer)
  B04   665 nm   red             10 m   dark-char test + false-colour display
  B8A   865 nm   narrow NIR      20 m   NBR
  B12  2190 nm   SWIR-2          20 m   NBR
  SCL            scene class.    20 m   cloud / shadow / cirrus / snow mask
  NBR  = (B8A - B12) / (B8A + B12)          dNBR = NBR_before - NBR_after
  False colour R=B12, G=B8A, B=B04: burn scars dark red/brown, vegetation green.

NISAR L2 GCOV (L-band), linear power
  HHHH, HVHV. Fire removes canopy volume scattering, so HV usually drops and
  RFDI = (HH - HV) / (HH + HV) usually rises. SAR sees through cloud and smoke.

Method
------
1. Sentinel-2 median composites (cloud masked) before / after on the NISAR grid.
2. Optical burn mask: dNBR (with scene offset) + vegetated before + dark after.
3. SAR features (dB changes, RFDI, smoothed versions, optional CROMA change).
4. Gradient-boosting model trained on the optical mask (pseudo-labels), spatial
   block cross-validation, then predicted over the whole NISAR footprint,
   including places where optical data is missing.
5. Fusion into classes, cleanup, GeoTIFFs, figure.

Usage
-----
  python scripts/detect_burns.py --workers 64
  pip install scikit-learn scipy   (if missing)
"""

import argparse
import os
import time
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
import pystac_client
import rasterio
import torch
from affine import Affine
from matplotlib.patches import Patch
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage as ndi
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

CACHE_DIR = Path("outputs/cache")
OUT_DIR = Path("outputs/burns")

BANDS = ("B04", "B8A", "B12")  # order used everywhere: index 0 = red, 1 = NIR, 2 = SWIR
NATIVE_RES = {"B04": 10.0, "B8A": 20.0, "B12": 20.0, "SCL": 20.0}
# SCL classes dropped: nodata, saturated, cloud shadow, cloud (med/high), cirrus, snow
SCL_BAD = (0, 1, 3, 8, 9, 10, 11)

DEFAULT_CROMA = (
    "outputs/explainability/"
    "NISAR_L2_PR_GCOV_025_087_A_022_2005_DHDH_A_20260714T052401_20260714T052434_"
    "P05023_F_F_J_001_NISAR_L2_PR_GCOV_028_087_A_022_2005_DHDH_A_20260819T052400_"
    "20260819T052432_P05023_N_F_J_001_croma_embedding_change.npz"
)

CLASS_NAMES = {
    1: "burned: optical + SAR agree",
    2: "burned: optical only",
    3: "burned: SAR only (optical gap)",
}
CLASS_COLORS = {1: "#e41a1c", 2: "#ff7f00", 3: "#00bcd4"}


# ----------------------------------------------------------------------------
# Analysis grid (everything is resampled onto the NISAR T1 grid)
# ----------------------------------------------------------------------------
def get_grid(tif_path: str, max_size: int) -> dict:
    with rasterio.open(tif_path) as src:
        scale = max(max(src.height, src.width) / max_size, 1.0)
        h = max(1, round(src.height / scale))
        w = max(1, round(src.width / scale))
        transform = src.transform * Affine.scale(src.width / w, src.height / h)
        crs, bounds = src.crs, src.bounds
    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    corners = [
        t.transform(x, y)
        for x, y in (
            (bounds.left, bounds.bottom), (bounds.right, bounds.top),
            (bounds.left, bounds.top), (bounds.right, bounds.bottom),
        )
    ]
    xs, ys = zip(*corners)
    return dict(
        crs_wkt=crs.to_wkt(),
        transform=tuple(transform)[:6],
        height=h,
        width=w,
        wgs84_bbox=[min(xs), min(ys), max(xs), max(ys)],
    )


def grid_affine(grid: dict) -> Affine:
    return Affine(*grid["transform"])


def grid_crs(grid: dict) -> CRS:
    return CRS.from_wkt(grid["crs_wkt"])


def scene_window(bbox, grid: dict, pad: int = 4):
    """Pixel window (y0, y1, x0, x1) of the grid touched by a WGS84 bbox, or None."""
    t = Transformer.from_crs("EPSG:4326", grid["crs_wkt"], always_xy=True)
    west, south, east, north = bbox
    pts = [t.transform(x, y) for x, y in ((west, south), (west, north), (east, south), (east, north))]
    inv = ~grid_affine(grid)
    cols, rows = zip(*[inv * p for p in pts])
    y0 = max(int(np.floor(min(rows))) - pad, 0)
    y1 = min(int(np.ceil(max(rows))) + pad, grid["height"])
    x0 = max(int(np.floor(min(cols))) - pad, 0)
    x1 = min(int(np.ceil(max(cols))) + pad, grid["width"])
    if y1 <= y0 or x1 <= x0:
        return None
    return y0, y1, x0, x1


# ----------------------------------------------------------------------------
# Sentinel-2: search -> warp each scene (threads) -> median composite (GPU)
# ----------------------------------------------------------------------------
def boa_offset(item) -> float:
    """L2A processing baseline >= 04.00 stores reflectance as (DN - 1000) / 10000."""
    try:
        return 1000.0 if float(item.properties.get("s2:processing_baseline", "05.00")) >= 4.0 else 0.0
    except ValueError:
        return 1000.0


def search_scenes(grid: dict, date_range: str, label: str, per_tile: int, max_cloud: float) -> list:
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    items = list(catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=grid["wgs84_bbox"],
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).items())
    if not items:
        raise ValueError(f"No Sentinel-2 scenes for {date_range}")
    # Keep the clearest few scenes PER TILE so every part of the footprint stays covered
    by_tile = {}
    for it in items:
        tile = it.properties.get("s2:mgrs_tile") or it.id.split("_")[-2]
        by_tile.setdefault(tile, []).append(it)
    keep = []
    for tile_items in by_tile.values():
        tile_items.sort(key=lambda i: i.properties["eo:cloud_cover"])
        keep += tile_items[:per_tile]
    print(f"[{label}] {len(items)} scenes found, {len(by_tile)} tiles, using {len(keep)}")
    return [
        (label, i.id, {b: i.assets[b].href for b in (*BANDS, "SCL")}, i.bbox, boa_offset(i), grid)
        for i in keep
    ]


def open_band(href: str, native_res: float, target_res):
    """Open a COG at the coarsest overview that is still finer than the target grid."""
    if target_res and target_res > 2 * native_res:
        level = int(np.floor(np.log2(target_res / native_res))) - 1  # overview_level 0 = factor 2
        for lv in range(min(level, 3), -1, -1):
            try:
                return rasterio.open(href, overview_level=lv)
            except Exception:  # noqa: BLE001  (overview missing -> try a finer one)
                continue
    return rasterio.open(href)


def warp_band(href, band, shape, transform, crs, target_res, resampling) -> np.ndarray:
    dst = np.zeros(shape, dtype=np.uint8 if band == "SCL" else np.uint16)
    with open_band(href, NATIVE_RES[band], target_res) as src:
        reproject(
            rasterio.band(src, 1), dst,
            dst_transform=transform, dst_crs=crs,
            src_nodata=0, dst_nodata=0, resampling=resampling,
        )
    return dst


def process_scene(task):
    """Thread worker. Returns (label, item_id, (y0, x0), float16 (3,h,w) reflectance, error)."""
    label, item_id, hrefs, bbox, offset, grid = task
    try:
        win = scene_window(bbox, grid)
        if win is None:
            return label, item_id, None, None, None
        y0, y1, x0, x1 = win
        shape = (y1 - y0, x1 - x0)
        transform = grid_affine(grid) * Affine.translation(x0, y0)
        crs = grid_crs(grid)
        target_res = abs(transform.a) if crs.is_projected else None
        with rasterio.Env():
            scl = warp_band(hrefs["SCL"], "SCL", shape, transform, crs, target_res, Resampling.nearest)
            bad = np.isin(scl, SCL_BAD)
            if (~bad).sum() < 50:  # fully clouded / outside: skip the expensive band reads
                return label, item_id, None, None, None
            stack = np.empty((len(BANDS), *shape), np.float32)
            nodata = np.zeros(shape, bool)
            for i, band in enumerate(BANDS):
                dn = warp_band(hrefs[band], band, shape, transform, crs, target_res, Resampling.bilinear)
                nodata |= dn == 0
                stack[i] = (dn.astype(np.float32) - offset) / 10000.0
        stack[:, bad | nodata] = np.nan  # same mask in every band
        np.clip(stack, 0.0, 2.0, out=stack)
        if np.isfinite(stack[0]).sum() < 50:
            return label, item_id, None, None, None
        return label, item_id, (y0, x0), stack.astype(np.float16), None
    except Exception:  # noqa: BLE001
        return label, item_id, None, None, traceback.format_exc(limit=4)


def median_composite(scenes, H: int, W: int, device: torch.device, band_rows: int = 128):
    """Per-pixel nan-median over scene crops, row band by row band (on GPU if available)."""
    out = torch.full((len(BANDS), H, W), float("nan"))
    for r0 in range(0, H, band_rows):
        r1 = min(r0 + band_rows, H)
        members = [(y0, x0, a) for (y0, x0), a in scenes if y0 < r1 and y0 + a.shape[1] > r0]
        if not members:
            continue
        block = torch.full((len(members), len(BANDS), r1 - r0, W), float("nan"), device=device)
        for k, (y0, x0, a) in enumerate(members):
            ys, ye = max(y0, r0), min(y0 + a.shape[1], r1)
            piece = torch.from_numpy(a[:, ys - y0:ye - y0].astype(np.float32)).to(device)
            block[k, :, ys - r0:ye - r0, x0:x0 + a.shape[2]] = piece
        out[:, r0:r1] = torch.nanmedian(block, dim=0).values.cpu()
    bands = out.numpy()
    return bands, np.isfinite(bands).all(axis=0)


def fetch_composites(grid: dict, windows: dict, args, device: torch.device) -> dict:
    """windows = {label: 'YYYY-MM-DD/YYYY-MM-DD'}; all scenes share one thread pool."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    H, W = grid["height"], grid["width"]
    result, todo = {}, {}
    for label, dr in windows.items():
        cache = CACHE_DIR / f"s2burn_{label}_{dr.replace('/', '_')}_{H}x{W}.npz"
        if cache.exists() and not args.refresh:
            d = np.load(cache)
            result[label] = (d["bands"], d["valid"])
            print(f"[{label}] loaded cached composite")
        else:
            todo[label] = (dr, cache)
    if not todo:
        return result

    tasks = []
    for label, (dr, _) in todo.items():
        tasks += search_scenes(grid, dr, label, args.per_tile, args.max_cloud)

    collected = {label: [] for label in todo}
    n_workers = max(1, min(args.workers, len(tasks)))
    print(f"Warping {len(tasks)} scenes with {n_workers} threads ...")
    t0, shown = time.time(), False
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = [ex.submit(process_scene, t) for t in tasks]
        for k, fut in enumerate(as_completed(futures), 1):
            label, item_id, origin, arr, err = fut.result()
            if err:
                if not shown:
                    print(err)
                    shown = True
                print(f"  ({k}/{len(tasks)}) [{label}] FAILED {item_id}")
                continue
            if arr is None:
                continue
            print(f"  ({k}/{len(tasks)}) [{label}] {item_id}: {np.isfinite(arr[0]).mean():.0%} of its window usable")
            collected[label].append((origin, arr))
    print(f"Scenes done in {time.time() - t0:.0f} s")

    for label, (dr, cache) in todo.items():
        if not collected[label]:
            raise RuntimeError(f"[{label}] no usable Sentinel-2 data in {dr}")
        bands, valid = median_composite(collected[label], H, W, device)
        np.savez_compressed(cache, bands=bands, valid=valid)
        print(f"[{label}] composite from {len(collected[label])} scenes, {valid.mean():.0%} of the grid covered")
        result[label] = (bands, valid)
    return result


# ----------------------------------------------------------------------------
# NISAR
# ----------------------------------------------------------------------------
def load_sar_linear(path: str, grid: dict) -> np.ndarray:
    """Linear power on the analysis grid; block-average resampling = multilooking."""
    with rasterio.open(path) as src:
        a = src.read(
            1, out_shape=(grid["height"], grid["width"]), resampling=Resampling.average
        ).astype(np.float32)
    a[~np.isfinite(a) | (a <= 0)] = np.nan
    return a


def resize_nearest(a: np.ndarray, h: int, w: int) -> np.ndarray:
    yi = (np.arange(h) * a.shape[0] / h).astype(int)
    xi = (np.arange(w) * a.shape[1] / w).astype(int)
    return a[yi][:, xi]


def nan_uniform(a: np.ndarray, size: int) -> np.ndarray:
    """Box-filter mean that ignores NaN (extra speckle suppression + spatial context)."""
    m = np.isfinite(a).astype(np.float32)
    s = ndi.uniform_filter(np.where(m > 0, a, 0.0).astype(np.float32), size, mode="nearest")
    w = ndi.uniform_filter(m, size, mode="nearest")
    return np.where(w > 0.5, s / np.maximum(w, 1e-6), np.nan).astype(np.float32)


def sar_features(hh1, hv1, hh2, hv2, croma=None) -> dict:
    db = lambda x: 10.0 * np.log10(x)  # noqa: E731
    rfdi = lambda hh, hv: (hh - hv) / (hh + hv)  # noqa: E731
    f = {
        "hv_pre": db(hv1), "hv_post": db(hv2),
        "hh_pre": db(hh1), "hh_post": db(hh2),
        "d_hv": db(hv2) - db(hv1),
        "d_hh": db(hh2) - db(hh1),
        "rfdi_pre": rfdi(hh1, hv1), "rfdi_post": rfdi(hh2, hv2),
        "d_rfdi": rfdi(hh2, hv2) - rfdi(hh1, hv1),
        "d_ratio": (db(hv2) - db(hh2)) - (db(hv1) - db(hh1)),
    }
    for k in ("d_hv", "d_hh"):  # remove the scene-wide radiometric / moisture offset
        f[k] = f[k] - np.nanmedian(f[k])
    for k in ("d_hv", "d_hh", "d_rfdi"):
        f[k + "_s5"] = nan_uniform(f[k], 5)
        f[k + "_s15"] = nan_uniform(f[k], 15)
    if croma is not None:
        f["croma"] = croma
        f["croma_s9"] = nan_uniform(croma, 9)
    return {k: v.astype(np.float32) for k, v in f.items()}


# ----------------------------------------------------------------------------
# Optical burn mask (dNBR)
# ----------------------------------------------------------------------------
def nbr(b: np.ndarray) -> np.ndarray:
    nir, swir = b[1], b[2]
    den = nir + swir
    return np.where(den > 0.02, (nir - swir) / np.maximum(den, 1e-6), np.nan)


def optical_burn(pre, v_pre, post, v_post, args) -> dict:
    with np.errstate(invalid="ignore", divide="ignore"):
        nbr_pre, nbr_post = nbr(pre), nbr(post)
        valid = v_pre & v_post & np.isfinite(nbr_pre) & np.isfinite(nbr_post)
        dnbr = np.where(valid, nbr_pre - nbr_post, np.nan).astype(np.float32)
        veg = valid & (nbr_pre > args.min_pre_nbr)
        offset = float(np.nanmedian(dnbr[veg])) if veg.any() else 0.0
        dnbr = dnbr - offset  # removes phenology / sun-angle bias between the two dates
        m1 = veg
        m2 = m1 & (dnbr > args.dnbr)
        m3 = m2 & (post[0] < args.max_post_red)   # char is dark in red; harvested stubble is not
        m4 = m3 & (nbr_post < args.max_post_nbr)
    n = max(int(valid.sum()), 1)
    print(f"Optical rules (dNBR offset removed: {offset:+.3f})")
    for name, m in (
        ("valid in both dates", valid),
        (f"+ vegetated before (NBR > {args.min_pre_nbr})", m1),
        (f"+ dNBR > {args.dnbr}", m2),
        (f"+ red after < {args.max_post_red}", m3),
        (f"+ NBR after < {args.max_post_nbr}", m4),
    ):
        print(f"  {name:<42s} {int(m.sum()):>10,d} px  ({m.sum() / n:6.2%} of valid)")
    return dict(dnbr=dnbr, burn=m4, valid=valid, nbr_pre=nbr_pre, nbr_post=nbr_post, offset=offset)


# ----------------------------------------------------------------------------
# SAR model trained on optical pseudo-labels
# ----------------------------------------------------------------------------
def report_indicators(opt, feats, footprint) -> None:
    ok = opt["valid"] & footprint
    y = opt["burn"][ok]
    if y.sum() < 50 or y.all():
        print("Skipping indicator report (too few optical burn pixels)")
        return
    print(f"Single-indicator agreement with the optical burn mask (base rate {y.mean():.2%}):")
    cands = [("-dHV (dB, 5x5)", -feats["d_hv_s5"]), ("-dHH (dB, 5x5)", -feats["d_hh_s5"]),
             ("dRFDI (5x5)", feats["d_rfdi_s5"])]
    if "croma_s9" in feats:
        cands.append(("CROMA change (9x9)", feats["croma_s9"]))
    for name, score in cands:
        s = score[ok]
        good = np.isfinite(s)
        if good.sum() < 100 or len(np.unique(y[good])) < 2:
            continue
        print(f"  {name:<20s} AUC {roc_auc_score(y[good], s[good]):.3f}   "
              f"AP {average_precision_score(y[good], s[good]):.3f}")


def train_sar_model(feats, opt, footprint, args):
    names = list(feats)
    H, W = footprint.shape
    pos = opt["burn"] & footprint
    neg = opt["valid"] & footprint & ~pos & (opt["dnbr"] < args.neg_dnbr)
    py, px = np.nonzero(pos)
    ny, nx = np.nonzero(neg)
    if len(py) < 200 or len(ny) < 200:
        print(f"Too few optical pseudo-labels (burn {len(py)}, not-burn {len(ny)}); no SAR model")
        return None, names
    rng = np.random.default_rng(0)
    n_pos = min(len(py), args.samples // 4)
    n_neg = min(len(ny), args.samples - n_pos)
    ip = rng.choice(len(py), n_pos, replace=False)
    ineg = rng.choice(len(ny), n_neg, replace=False)
    ys = np.concatenate([py[ip], ny[ineg]])
    xs = np.concatenate([px[ip], nx[ineg]])
    y = np.concatenate([np.ones(n_pos, int), np.zeros(n_neg, int)])
    X = np.stack([feats[n][ys, xs] for n in names], axis=1)
    groups = (ys // args.block) * (W // args.block + 1) + xs // args.block

    def make():
        return HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, max_leaf_nodes=31, l2_regularization=1.0,
            class_weight="balanced", early_stopping=True, random_state=0,
        )

    n_splits = min(5, len(np.unique(groups)))
    if n_splits >= 2:
        oof = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=n_splits).split(X, y, groups):
            oof[te] = make().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        print(f"SAR model, spatial {n_splits}-fold CV vs optical pseudo-labels: "
              f"AUC {roc_auc_score(y, oof):.3f}, AP {average_precision_score(y, oof):.3f} "
              f"(sample base rate {y.mean():.2f})")
        print("  note: this measures agreement with dNBR, not true accuracy")
    model = make().fit(X, y)
    return model, names


def predict_prob(model, feats, names, footprint, chunk: int = 256) -> np.ndarray:
    H, W = footprint.shape
    prob = np.full((H, W), np.nan, np.float32)
    for r0 in range(0, H, chunk):
        r1 = min(r0 + chunk, H)
        m = footprint[r0:r1].reshape(-1)
        if not m.any():
            continue
        X = np.stack([feats[n][r0:r1] for n in names], axis=-1).reshape(-1, len(names))
        p = np.full(m.shape, np.nan, np.float32)
        p[m] = model.predict_proba(X[m])[:, 1]
        prob[r0:r1] = p.reshape(r1 - r0, W)
    return prob


# ----------------------------------------------------------------------------
# Fusion, cleanup, outputs
# ----------------------------------------------------------------------------
def fuse(opt, sar_prob, footprint, args) -> np.ndarray:
    cls = np.zeros(footprint.shape, np.uint8)
    if sar_prob is None:
        cls[opt["valid"] & opt["burn"]] = 2
        return cls
    p = np.nan_to_num(sar_prob, nan=0.0)
    cls[opt["valid"] & opt["burn"] & (p > args.sar_thr)] = 1
    cls[opt["valid"] & opt["burn"] & (p <= args.sar_thr)] = 2
    cls[~opt["valid"] & footprint & (p > args.sar_only_thr)] = 3
    return cls


def cleanup(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    st = np.ones((3, 3), bool)
    m = ndi.binary_closing(mask, structure=st)
    m = ndi.binary_opening(m, structure=st)
    lab, n = ndi.label(m)
    if n:
        sizes = ndi.sum(m, lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= min_pixels
        m = keep[lab]
    return m


def write_raster(path: Path, arr: np.ndarray, grid: dict) -> None:
    nodata = float("nan") if np.issubdtype(arr.dtype, np.floating) else None
    with rasterio.open(
        path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
        dtype=arr.dtype, crs=grid_crs(grid), transform=grid_affine(grid),
        compress="deflate", nodata=nodata,
    ) as dst:
        dst.write(arr, 1)


# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------
def false_colour(b: np.ndarray, valid: np.ndarray, footprint: np.ndarray) -> np.ndarray:
    """R=B12, G=B8A, B=B04. White outside the NISAR footprint, light gray = no optical data."""
    rgb = np.stack([b[2], b[1], b[0]], axis=-1)
    out = np.zeros(rgb.shape, np.float32)
    for c in range(3):
        v = rgb[..., c][valid]
        lo, hi = np.percentile(v, (2, 98)) if v.size else (0.0, 1.0)
        out[..., c] = np.clip((rgb[..., c] - lo) / (hi - lo + 1e-6), 0, 1)
    out[~valid] = 0.85
    out[~footprint] = 1.0
    return out


def plot_results(path, fc_pre, fc_post, opt, feats, sar_prob, cls, burned_ha, args) -> None:
    H, W = cls.shape
    fig, axes = plt.subplots(2, 3, figsize=(20, 13), constrained_layout=True)

    def show(ax, data, title, cmap, label, vmin=None, vmax=None, norm=None, ticks=None):
        c = plt.get_cmap(cmap).copy() if isinstance(cmap, str) else cmap.copy()
        c.set_bad("white")
        kw = dict(norm=norm) if norm is not None else dict(vmin=vmin, vmax=vmax)
        im = ax.imshow(np.ma.masked_invalid(data), cmap=c, interpolation="nearest", **kw)
        ax.set_title(title, fontsize=12)
        ax.axis("off")
        cb = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02, label=label)
        if ticks is not None:
            cb.set_ticks(ticks)

    axes[0, 0].imshow(fc_pre)
    axes[0, 0].set_title(f"Sentinel-2 before ({args.before})\nfalse colour B12/B8A/B04", fontsize=12)
    axes[0, 1].imshow(fc_post)
    axes[0, 1].set_title(f"Sentinel-2 after ({args.after})\nburn = dark red/brown, vegetation = green", fontsize=12)

    bounds = [-1.5, -0.25, -0.1, 0.1, 0.27, 0.44, 0.66, 2.0]
    sev = mcolors.ListedColormap(
        ["#1a9850", "#a6d96a", "#f0f0f0", "#fee08b", "#fdae61", "#f46d43", "#a50026"])
    show(axes[0, 2], opt["dnbr"], "dNBR (USGS severity classes)", sev, "dNBR",
         norm=mcolors.BoundaryNorm(bounds, sev.N), ticks=bounds[1:-1])

    show(axes[1, 0], feats["d_hv_s5"], "NISAR dHV (dB, 5x5 mean)\nred = backscatter drop",
         "RdBu", "dB", vmin=-4, vmax=4)
    if sar_prob is not None:
        show(axes[1, 1], sar_prob, "SAR burn probability (model trained on dNBR)",
             "viridis", "probability", vmin=0, vmax=1)
    else:
        axes[1, 1].axis("off")

    axes[1, 2].imshow(fc_post)
    overlay = np.zeros((H, W, 4), np.float32)
    for k, col in CLASS_COLORS.items():
        overlay[cls == k] = (*mcolors.to_rgb(col), 0.85)
    axes[1, 2].imshow(overlay, interpolation="nearest")
    axes[1, 2].set_title(f"Detected burns: {burned_ha:,.0f} ha", fontsize=12, fontweight="bold")
    axes[1, 2].axis("off")
    present = [k for k in CLASS_NAMES if (cls == k).any()]
    if present:
        axes[1, 2].legend(
            handles=[Patch(color=CLASS_COLORS[k], label=CLASS_NAMES[k]) for k in present],
            loc="lower left", fontsize=9, framealpha=0.9)
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nisar-dir", default="data/nisar")
    ap.add_argument("--croma", default=DEFAULT_CROMA, help="optional CROMA change .npz (used as a feature)")
    ap.add_argument("--before", default="2026-07-01/2026-07-14", help="Sentinel-2 window before the fire")
    ap.add_argument("--after", default="2026-08-15/2026-08-25", help="Sentinel-2 window after the fire")
    ap.add_argument("--max-size", type=int, default=2500, help="longest side of the analysis grid (px)")
    ap.add_argument("--workers", type=int, default=(os.cpu_count() or 4) * 2, help="download/warp threads")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--per-tile", type=int, default=4, help="clearest scenes kept per MGRS tile")
    ap.add_argument("--max-cloud", type=float, default=70.0)
    ap.add_argument("--dnbr", type=float, default=0.27, help="dNBR burn threshold (USGS moderate-low)")
    ap.add_argument("--neg-dnbr", type=float, default=0.10, help="dNBR below this = confident not burned")
    ap.add_argument("--min-pre-nbr", type=float, default=0.10, help="must be vegetated before the fire")
    ap.add_argument("--max-post-nbr", type=float, default=0.15)
    ap.add_argument("--max-post-red", type=float, default=0.15, help="B04 reflectance after the fire")
    ap.add_argument("--sar-thr", type=float, default=0.5)
    ap.add_argument("--sar-only-thr", type=float, default=0.8, help="stricter threshold where optical is missing")
    ap.add_argument("--min-ha", type=float, default=2.0, help="drop burn patches smaller than this")
    ap.add_argument("--samples", type=int, default=400_000, help="training pixels for the SAR model")
    ap.add_argument("--block", type=int, default=128, help="spatial CV block size (px)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached Sentinel-2 composites")
    args = ap.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        ap.error("--device=cuda requested but CUDA is not available")
    device = torch.device("cuda" if args.device != "cpu" and torch.cuda.is_available() else "cpu")
    print(f"Median compositing on: {device}; download threads: {args.workers}")

    os.environ.update(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MULTIPLEX="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="1",
        VSI_CACHE="TRUE",
        GDAL_CACHEMAX="1024",
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    nd = Path(args.nisar_dir)
    paths = [str(nd / n) for n in ("T1_HHHH.tif", "T1_HVHV.tif", "T2_HHHH.tif", "T2_HVHV.tif")]
    grid = get_grid(paths[0], args.max_size)
    H, W = grid["height"], grid["width"]
    crs = grid_crs(grid)
    pix_ha = abs(grid_affine(grid).a * grid_affine(grid).e) / 1e4
    if not crs.is_projected:
        print("WARNING: NISAR CRS is not projected, hectare figures are not meaningful")
    print(f"Analysis grid {W}x{H}px, pixel ~ {np.sqrt(pix_ha) * 100:.0f} m")

    # --- NISAR -------------------------------------------------------------
    print("Loading NISAR ...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        hh1, hv1, hh2, hv2 = ex.map(lambda p: load_sar_linear(p, grid), paths)
    footprint = np.isfinite(hh1) & np.isfinite(hv1) & np.isfinite(hh2) & np.isfinite(hv2)

    croma = None
    if args.croma and Path(args.croma).exists():
        print("Loading CROMA change map (feature) ...")
        with np.load(args.croma) as d:
            croma = resize_nearest(d["combined"].astype(np.float32), H, W)
        croma[~footprint] = np.nan
    feats = sar_features(hh1, hv1, hh2, hv2, croma)
    del hh1, hv1, hh2, hv2

    # --- Sentinel-2 --------------------------------------------------------
    print("Fetching Sentinel-2 ...")
    comp = fetch_composites(grid, {"BEFORE": args.before, "AFTER": args.after}, args, device)
    pre, v_pre = comp["BEFORE"]
    post, v_post = comp["AFTER"]

    # --- Optical burn mask, SAR model, fusion --------------------------------
    opt = optical_burn(pre, v_pre, post, v_post, args)
    opt["valid"] &= footprint
    opt["burn"] &= footprint
    report_indicators(opt, feats, footprint)

    model, names = train_sar_model(feats, opt, footprint, args)
    sar_prob = predict_prob(model, feats, names, footprint) if model is not None else None

    cls = fuse(opt, sar_prob, footprint, args)
    min_px = max(1, int(np.ceil(args.min_ha / pix_ha)))
    cls[~cleanup(cls > 0, min_px)] = 0

    # --- Outputs -------------------------------------------------------------
    print("\nBurned area")
    total = 0.0
    for k, name in CLASS_NAMES.items():
        ha = (cls == k).sum() * pix_ha
        total += ha
        print(f"  {name:<34s} {ha:>10,.0f} ha")
    print(f"  {'TOTAL':<34s} {total:>10,.0f} ha  ({total / max((footprint.sum() * pix_ha), 1):.2%} of footprint)")

    write_raster(OUT_DIR / "burn_class.tif", cls, grid)
    write_raster(OUT_DIR / "dnbr.tif", opt["dnbr"].astype(np.float32), grid)
    if sar_prob is not None:
        write_raster(OUT_DIR / "sar_burn_probability.tif", sar_prob, grid)
    plot_results(
        OUT_DIR / "burn_detection.png",
        false_colour(pre, v_pre, footprint), false_colour(post, v_post, footprint),
        opt, feats, sar_prob, cls, total, args,
    )
    print(f"\nSaved to {OUT_DIR}/: burn_class.tif (0 none, 1 agree, 2 optical only, 3 SAR only), "
          f"dnbr.tif, sar_burn_probability.tif, burn_detection.png")


if __name__ == "__main__":
    main()