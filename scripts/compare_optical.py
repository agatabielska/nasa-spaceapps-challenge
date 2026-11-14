"""Sentinel-2 (before/after) + NISAR HH/HV + CROMA change map, all in one figure."""

import warnings
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import rasterio
import pystac_client
import planetary_computer
from affine import Affine
from matplotlib.gridspec import GridSpec
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import reproject

MAX_PLOT_SIZE = 2000
CACHE_DIR = Path("outputs/cache")
# Sentinel-2 SCL classes to drop: nodata, saturated, cloud shadow, cloud (med/high), cirrus, snow
SCL_BAD = [0, 1, 3, 8, 9, 10, 11]


# ----------------------------------------------------------------------------
# Common plotting grid (everything is resampled onto this)
# ----------------------------------------------------------------------------
def get_grid(tif_path: str) -> dict:
    with rasterio.open(tif_path) as src:
        scale = max(max(src.height, src.width) / MAX_PLOT_SIZE, 1.0)
        h = max(1, round(src.height / scale))
        w = max(1, round(src.width / scale))
        transform = src.transform * Affine.scale(src.width / w, src.height / h)
        bounds, crs = src.bounds, src.crs
    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs, ys = zip(
        t.transform(bounds.left, bounds.bottom),
        t.transform(bounds.right, bounds.top),
        t.transform(bounds.left, bounds.top),
        t.transform(bounds.right, bounds.bottom),
    )
    return dict(
        crs=crs, transform=transform, height=h, width=w,
        wgs84_bbox=[min(xs), min(ys), max(xs), max(ys)],
    )


# ----------------------------------------------------------------------------
# Sentinel-2
# ----------------------------------------------------------------------------
def fetch_sentinel2_rgb(grid: dict, date_range: str, label: str,
                        max_items: int = 40, max_cloud: float = 70.0):
    """Cloud-masked median mosaic on the NISAR grid. Returns (rgb float HxWx3, valid HxW)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"s2_{label}_{date_range.replace('/', '_')}_{grid['height']}x{grid['width']}.npz"
    if cache.exists():
        d = np.load(cache)
        print(f"[{label}] loaded cached mosaic")
        return d["rgb"], d["valid"]

    H, W = grid["height"], grid["width"]
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
    items.sort(key=lambda i: i.properties["eo:cloud_cover"])
    items = items[:max_items]
    print(f"[{label}] {len(items)} candidate scenes")

    rgbs, valids = [], []
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3",
               GDAL_HTTP_RETRY_DELAY="1")
    for n, item in enumerate(items, 1):
        try:
            rgb = np.zeros((3, H, W), dtype=np.uint8)
            scl = np.zeros((H, W), dtype=np.uint8)
            with rasterio.Env(**env):
                with rasterio.open(item.assets["visual"].href) as src:
                    reproject(
                        rasterio.band(src, [1, 2, 3]), rgb,
                        dst_transform=grid["transform"], dst_crs=grid["crs"],
                        src_nodata=0, dst_nodata=0, resampling=Resampling.bilinear,
                    )
                with rasterio.open(item.assets["SCL"].href) as src:
                    reproject(
                        rasterio.band(src, 1), scl,
                        dst_transform=grid["transform"], dst_crs=grid["crs"],
                        resampling=Resampling.nearest,
                    )
            valid = (rgb.max(axis=0) > 0) & ~np.isin(scl, SCL_BAD)
            frac = valid.mean()
            if frac < 0.01:
                continue  # scene barely touches the area
            print(f"  [{label}] {n}/{len(items)} {item.id}: {frac:.0%} usable")
            rgbs.append(rgb)
            valids.append(valid)
        except Exception as e:  # noqa: BLE001
            print(f"  [{label}] skipped {item.id}: {e}")

    if not rgbs:
        raise RuntimeError(f"[{label}] no usable Sentinel-2 data")

    rgb_stack = np.stack(rgbs)      # (N, 3, H, W) uint8
    valid_stack = np.stack(valids)  # (N, H, W)
    mosaic = np.full((3, H, W), np.nan, dtype=np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for y0 in range(0, H, 128):  # row bands keep memory low
            y1 = min(y0 + 128, H)
            block = rgb_stack[:, :, y0:y1].astype(np.float32)
            block = np.where(valid_stack[:, None, y0:y1], block, np.nan)
            mosaic[:, y0:y1] = np.nanmedian(block, axis=0)

    img = np.transpose(mosaic, (1, 2, 0))
    valid = np.isfinite(img).all(axis=-1)
    img = np.nan_to_num(img, nan=0.0)
    if valid.any():
        lo, hi = np.percentile(img[valid], (2, 98))
        img = np.clip((img - lo) / (hi - lo + 1e-8), 0, 1)
    np.savez_compressed(cache, rgb=img.astype(np.float32), valid=valid)
    print(f"[{label}] mosaic from {len(rgbs)} scenes, {valid.mean():.0%} covered")
    return img.astype(np.float32), valid


def display_rgb(rgb, valid, footprint):
    """White outside the NISAR footprint, light gray where optical data is missing."""
    out = rgb.copy()
    out[~valid] = 0.85
    out[~footprint] = 1.0
    return out


# ----------------------------------------------------------------------------
# NISAR / CROMA
# ----------------------------------------------------------------------------
def load_sar_db(tif_path: str, grid: dict) -> np.ndarray:
    with rasterio.open(tif_path) as src:
        data = src.read(
            1, out_shape=(grid["height"], grid["width"]),
            resampling=Resampling.average,
        ).astype(np.float32)
    data[~np.isfinite(data) | (data <= 0)] = np.nan
    return 10 * np.log10(data)


def resize_nearest(a: np.ndarray, h: int, w: int) -> np.ndarray:
    yi = (np.arange(h) * a.shape[0] / h).astype(int)
    xi = (np.arange(w) * a.shape[1] / w).astype(int)
    return a[yi][:, xi]


# ----------------------------------------------------------------------------
def main():
    nisar_t1_tif = "data/nisar/T1_HHHH.tif"
    nisar_t1_hv_tif = "data/nisar/T1_HVHV.tif"
    nisar_t2_tif = "data/nisar/T2_HHHH.tif"
    nisar_t2_hv_tif = "data/nisar/T2_HVHV.tif"
    explainability_npz = (
        "outputs/explainability/"
        "NISAR_L2_PR_GCOV_025_087_A_022_2005_DHDH_A_20260714T052401_20260714T052434_"
        "P05023_F_F_J_001_NISAR_L2_PR_GCOV_028_087_A_022_2005_DHDH_A_20260819T052400_"
        "20260819T052432_P05023_N_F_J_001_croma_embedding_change.npz"
    )
    output_plot = "multimodal_comparison_full.png"

    # Widen these if the optical mosaic still has gray holes
    date_range_t1 = "2026-07-01/2026-07-14"
    date_range_t2 = "2026-08-15/2026-08-25"

    grid = get_grid(nisar_t1_tif)
    H, W = grid["height"], grid["width"]

    print("Loading NISAR...")
    hh1, hv1 = load_sar_db(nisar_t1_tif, grid), load_sar_db(nisar_t1_hv_tif, grid)
    hh2, hv2 = load_sar_db(nisar_t2_tif, grid), load_sar_db(nisar_t2_hv_tif, grid)
    footprint = (np.isfinite(hh1) & np.isfinite(hv1) &
                 np.isfinite(hh2) & np.isfinite(hv2))

    print("Loading CROMA change map...")
    with np.load(explainability_npz) as d:
        change = resize_nearest(d["combined"].astype(np.float32), H, W)
    change[~footprint] = np.nan
    c_vmax = float(np.nanpercentile(change[footprint], 99.5))
    c_thr = float(np.nanpercentile(change[footprint], 95))

    print("Fetching Sentinel-2...")
    s2_1, v1 = fetch_sentinel2_rgb(grid, date_range_t1, "BEFORE")
    s2_2, v2 = fetch_sentinel2_rgb(grid, date_range_t2, "AFTER")
    s2_1_show = display_rgb(s2_1, v1, footprint)
    s2_2_show = display_rgb(s2_2, v2, footprint)

    # CROMA overlay on the "after" optical image (top 5% change only)
    overlay = np.zeros((H, W, 4), dtype=np.float32)
    cmap = plt.get_cmap("magma")
    norm = np.clip(np.nan_to_num(change) / c_vmax, 0, 1)
    overlay[:] = cmap(norm)
    overlay[..., 3] = np.where(np.nan_to_num(change) > c_thr, 0.8, 0.0)

    print("Plotting...")
    fig = plt.figure(figsize=(18, 16), dpi=150, constrained_layout=True)
    gs = GridSpec(3, 3, figure=fig)

    def panel(pos, data, title, cmap_name, vmin, vmax, cbar_label):
        ax = fig.add_subplot(gs[pos])
        c = plt.get_cmap(cmap_name).copy()
        c.set_bad("white")
        im = ax.imshow(np.ma.masked_invalid(data), cmap=c, vmin=vmin, vmax=vmax)
        ax.set_title(title, fontsize=12)
        ax.axis("off")
        fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02, label=cbar_label)

    # Row 1: optical
    ax = fig.add_subplot(gs[0, 0]); ax.imshow(s2_1_show)
    ax.set_title(f"Sentinel-2 (T1: before, {date_range_t1})", fontsize=12); ax.axis("off")
    ax = fig.add_subplot(gs[0, 1]); ax.imshow(s2_2_show)
    ax.set_title(f"Sentinel-2 (T2: after, {date_range_t2})", fontsize=12); ax.axis("off")
    ax = fig.add_subplot(gs[0, 2]); ax.imshow(s2_2_show); ax.imshow(overlay)
    ax.set_title("Sentinel-2 (after) + top 5% CROMA change", fontsize=12); ax.axis("off")

    # Row 2: HH
    panel((1, 0), hh1, "NISAR HH (T1: before)", "gray", -25, 5, "dB")
    panel((1, 1), hh2, "NISAR HH (T2: after)", "gray", -25, 5, "dB")
    panel((1, 2), hh2 - hh1, "HH change (T2 - T1)", "RdBu_r", -6, 6, "dB difference")

    # Row 3: HV + CROMA
    panel((2, 0), hv1, "NISAR HV (T1: before)", "gray", -35, -5, "dB")
    panel((2, 1), hv2, "NISAR HV (T2: after)", "gray", -35, -5, "dB")
    panel((2, 2), change, "CROMA foundation-model change map", "magma", 0, c_vmax,
          f"Change intensity (clipped at p99.5 = {c_vmax:.2f})")

    fig.savefig(output_plot, bbox_inches="tight", facecolor="white")
    print(f"Saved {output_plot}")


if __name__ == "__main__":
    main()