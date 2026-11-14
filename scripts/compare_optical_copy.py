
"""Sentinel-2 (before/after) + NISAR HH/HV + CROMA change map, parallelised and memory-lean.
 
Usage:
  python scripts/compare_optical_copy.py --workers 8 --device auto
 
Memory notes (what changed vs. the original):
  * Default workers = 8 (warping is network-bound; 32 processes just multiply RAM use).
  * Heavy imports (matplotlib, pystac_client, planetary_computer, pyproj) are lazy, so
    spawned workers only import numpy/rasterio/affine.
  * GDAL cache is 128 MB per process.
  * Workers are recycled (max_tasks_per_child, Python 3.11+) to release GDAL buffers.
  * Scenes are written to on-disk memmaps as they finish instead of being held in RAM,
    and the median is computed from the memmaps in small row bands (no np.stack copy).
  * The CROMA array is subsampled before the float32 cast (no full-res float copy).
"""
import os
os.environ.setdefault("GDAL_CACHEMAX", "128")   # MB per process
 
import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
 
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import Window
 
# NOTE: torch, matplotlib, pyproj, pystac_client, planetary_computer are imported lazily
# so spawned workers don't pay for them.
 
MAX_PLOT_SIZE = 2000
CACHE_DIR = Path("outputs/cache")
TMP_DIR = CACHE_DIR / "tmp"
# Sentinel-2 SCL classes to drop: nodata, saturated, cloud shadow, cloud (med/high), cirrus, snow
SCL_BAD = [0, 1, 3, 8, 9, 10, 11]
 
 
# ----------------------------------------------------------------------------
# Common plotting grid (everything is resampled onto this)
# ----------------------------------------------------------------------------
def get_grid(tif_path: str) -> dict:
    from pyproj import Transformer
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
        crs_wkt=crs.to_wkt(),            # plain types so it pickles cleanly to workers
        transform=tuple(transform)[:6],
        height=h, width=w,
        wgs84_bbox=[min(xs), min(ys), max(xs), max(ys)],
    )
 
 
# ----------------------------------------------------------------------------
# Sentinel-2: search (main process) -> warp per scene (worker processes)
# ----------------------------------------------------------------------------
def search_scenes(grid: dict, date_range: str, label: str,
                  max_items: int, max_cloud: float) -> list:
    import pystac_client
    import planetary_computer
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
    return [
        (label, i.id, i.datetime.isoformat() if i.datetime else None,
         i.assets["visual"].href, i.assets["SCL"].href)
        for i in items
    ]
 
 
def warp_scene(task):
    """Runs in a worker process: warp one scene's RGB + SCL onto the NISAR grid."""
    (label, item_id, acquired_at, visual_href, scl_href), grid = task
    H, W = int(grid["height"]), int(grid["width"])
    crs = CRS.from_wkt(grid["crs_wkt"])
    transform = Affine(*grid["transform"])
    try:
        rgb = np.zeros((3, H, W), dtype=np.uint8)
        scl = np.zeros((H, W), dtype=np.uint8)
        env = dict(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            GDAL_HTTP_MAX_RETRY="3",
            GDAL_HTTP_RETRY_DELAY="1",
        )
        with rasterio.Env(**env):
            with rasterio.open(visual_href) as src:
                reproject(
                    rasterio.band(src, [1, 2, 3]), rgb,
                    dst_transform=transform, dst_crs=crs,
                    src_nodata=0, dst_nodata=0, resampling=Resampling.bilinear,
                )
            with rasterio.open(scl_href) as src:
                reproject(
                    rasterio.band(src, 1), scl,
                    dst_transform=transform, dst_crs=crs,
                    resampling=Resampling.nearest,
                )
        valid = (rgb.max(axis=0) > 0) & ~np.isin(scl, SCL_BAD)
        return label, item_id, acquired_at, rgb, valid, None
    except Exception:  # noqa: BLE001
        return label, item_id, acquired_at, None, None, traceback.format_exc(limit=4)
 
 
def median_mosaic(rgb_mm, val_mm, n, device):
    """Per-pixel nanmedian over the first n scenes, read from memmaps in row bands.
 
    Returns (HxWx3 float32 in [0,1], valid mask).
    """
    import torch
    _, _, H, W = rgb_mm.shape
    mosaic = np.empty((3, H, W), dtype=np.float32)
    step = 128 if device.type == "cuda" else 48   # small bands keep peak memory low
    for y0 in range(0, H, step):
        y1 = min(y0 + step, H)
        block = torch.from_numpy(np.ascontiguousarray(rgb_mm[:n, :, y0:y1])).to(device).float()
        mask = torch.from_numpy(np.ascontiguousarray(val_mm[:n, y0:y1])).to(device)[:, None]
        block.masked_fill_(~mask, float("nan"))       # in place: no extra copy
        del mask
        mosaic[:, y0:y1] = torch.nanmedian(block, dim=0).values.cpu().numpy()
        del block
        if device.type == "cuda":
            torch.cuda.empty_cache()
    img = mosaic.transpose(1, 2, 0)
    valid = np.isfinite(img).all(axis=-1)
    img = np.nan_to_num(img, nan=0.0)
    if valid.any():
        lo, hi = np.percentile(img[valid], (2, 98))
        img = np.clip((img - lo) / (hi - lo + 1e-8), 0, 1)
    return img.astype(np.float32), valid
 
 
def _make_executor(n_workers: int):
    kwargs = dict(max_workers=n_workers, mp_context=get_context("spawn"))
    if sys.version_info >= (3, 11):
        kwargs["max_tasks_per_child"] = 4   # recycle workers so GDAL buffers are released
    return ProcessPoolExecutor(**kwargs)
 
 
def fetch_all_mosaics(grid, jobs: dict, workers: int, device, max_items, max_cloud):
    """jobs = {label: date_range}. All scenes of all labels share one process pool."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    H, W = int(grid["height"]), int(grid["width"])
    results, todo, acquisition_times = {}, {}, {}
 
    for label, dr in jobs.items():
        cache = CACHE_DIR / f"s2_v4_{label}_{dr.replace('/', '_')}_{H}x{W}.npz"
        if cache.exists():
            with np.load(cache) as d:
                print(f"[{label}] loaded cached mosaic")
                results[label] = (d["rgb"], d["valid"])
                acquisition_times[label] = (
                    list(d["acquired_at"].astype(str)) if "acquired_at" in d.files else []
                )
        else:
            todo[label] = (dr, cache)
    if not todo:
        return results, acquisition_times
 
    # ---- search + allocate on-disk buffers --------------------------------
    tasks = []
    store = {}
    for label, (dr, _) in todo.items():
        scenes = search_scenes(grid, dr, label, max_items, max_cloud)
        acquisition_times[label] = [s[2] for s in scenes]
        tasks += [(s, grid) for s in scenes]
        n = len(scenes)
        rgb_path = TMP_DIR / f"{label}_rgb.npy"
        val_path = TMP_DIR / f"{label}_val.npy"
        store[label] = dict(
            rgb=np.lib.format.open_memmap(rgb_path, mode="w+", dtype=np.uint8, shape=(n, 3, H, W)),
            val=np.lib.format.open_memmap(val_path, mode="w+", dtype=bool, shape=(n, H, W)),
            paths=(rgb_path, val_path),
            used=0,
            used_times=[],
        )
 
    # ---- warp in worker processes, stream results to disk ------------------
    n_workers = max(1, min(workers, len(tasks)))
    print(f"Warping {len(tasks)} scenes on {n_workers} processes...")
    shown_error = False
    with _make_executor(n_workers) as ex:
        futures = [ex.submit(warp_scene, t) for t in tasks]
        for k, fut in enumerate(as_completed(futures), 1):
            label, item_id, acquired_at, rgb, valid, err = fut.result()
            if err:
                if not shown_error:
                    print(err)
                    shown_error = True
                print(f"  [{label}] skipped {item_id}")
                continue
            frac = float(valid.mean())
            if frac < 0.01:
                continue  # scene barely touches the area
            print(f"  ({k}/{len(tasks)}) [{label}] {item_id}: {frac:.0%} usable")
            s = store[label]
            i = s["used"]
            s["rgb"][i] = rgb
            s["val"][i] = valid
            s["used"] += 1
            s["used_times"].append(acquired_at)
            del rgb, valid
 
    # ---- median per label, from memmaps ------------------------------------
    for label, (dr, cache) in todo.items():
        s = store[label]
        n_used = s["used"]
        if n_used == 0:
            raise RuntimeError(f"[{label}] no usable Sentinel-2 data")
        s["rgb"].flush()
        s["val"].flush()
        img, valid = median_mosaic(s["rgb"], s["val"], n_used, device)
        acquisition_times[label] = [t for t in s["used_times"] if t is not None]
        np.savez_compressed(
            cache, rgb=img, valid=valid,
            acquired_at=np.array(acquisition_times[label], dtype=str),
        )
        print(f"[{label}] mosaic from {n_used} scenes, {valid.mean():.0%} covered")
        results[label] = (img, valid)
 
        # release memmaps and delete temp files
        rgb_mm, val_mm = s.pop("rgb"), s.pop("val")
        del rgb_mm, val_mm
        for p in s["paths"]:
            try:
                p.unlink()
            except OSError:
                pass
    return results, acquisition_times
 
 
def display_rgb(rgb, valid, footprint):
    """White outside the NISAR footprint, light gray where optical data is missing."""
    out = rgb.copy()
    out[~valid] = 0.85
    out[~footprint] = 1.0
    return out
 
 
# ----------------------------------------------------------------------------
# NISAR / CROMA
# ----------------------------------------------------------------------------
def load_sar_db(tif_path: str, grid: dict, band_rows: int = 64) -> np.ndarray:
    """Downsample in horizontal bands so peak RAM stays small regardless of file size."""
    H, W = grid["height"], grid["width"]
    out = np.empty((H, W), dtype=np.float32)
    with rasterio.open(tif_path) as src:
        sh = src.height / H
        for y0 in range(0, H, band_rows):
            y1 = min(y0 + band_rows, H)
            r0 = int(round(y0 * sh))
            r1 = src.height if y1 == H else max(int(round(y1 * sh)), r0 + 1)
            out[y0:y1] = src.read(
                1,
                window=Window(0, r0, src.width, r1 - r0),
                out_shape=(y1 - y0, W),
                resampling=Resampling.average,
                out_dtype="float32",
            )
    out[~np.isfinite(out) | (out <= 0)] = np.nan
    return 10 * np.log10(out)
 
 
def resize_nearest(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Nearest-neighbour subsample; picks pixels first so no full-size float copy is made."""
    yi = (np.arange(h) * a.shape[0] / h).astype(int)
    xi = (np.arange(w) * a.shape[1] / w).astype(int)
    return a[np.ix_(yi, xi)].astype(np.float32)
 
 
# ----------------------------------------------------------------------------
def main():
    import torch
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
 
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--max-items", type=int, default=64)
    ap.add_argument("--max-cloud", type=float, default=70.0)
    args = ap.parse_args()
 
    if args.device == "cuda" and not torch.cuda.is_available():
        ap.error("--device=cuda requested but CUDA is not available")
    device = torch.device(
        "cuda" if args.device in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
    )
    torch.set_num_threads(min(args.workers, 8))
    print(f"Median device: {device}, workers: {args.workers}")
 
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
    date_range_t1 = "2026-06-30/2026-07-13"
    date_range_t2 = "2026-08-20/2026-09-02"
 
    grid = get_grid(nisar_t1_tif)
    H, W = grid["height"], grid["width"]
 
    print("Loading NISAR...")
    with ThreadPoolExecutor(max_workers=2) as ex:  # rasterio releases the GIL during reads
        hh1, hv1, hh2, hv2 = ex.map(
            lambda p: load_sar_db(p, grid),
            [nisar_t1_tif, nisar_t1_hv_tif, nisar_t2_tif, nisar_t2_hv_tif],
        )
    footprint = (np.isfinite(hh1) & np.isfinite(hv1) &
                 np.isfinite(hh2) & np.isfinite(hv2))
 
    print("Loading CROMA change map...")
    with np.load(explainability_npz) as d:
        change = resize_nearest(d["combined"], H, W)   # subsample BEFORE float32 cast
    change[~footprint] = np.nan
    c_vmax = float(np.nanpercentile(change[footprint], 99.5))
    c_thr = float(np.nanpercentile(change[footprint], 95))
 
    print("Fetching Sentinel-2...")
    mosaics, acquisition_times = fetch_all_mosaics(
        grid, {"BEFORE": date_range_t1, "AFTER": date_range_t2},
        args.workers, device, args.max_items, args.max_cloud,
    )
    s2_1, v1 = mosaics["BEFORE"]
    s2_2, v2 = mosaics["AFTER"]
    s2_1_show = display_rgb(s2_1, v1, footprint)
    s2_2_show = display_rgb(s2_2, v2, footprint)
    del mosaics, s2_1, s2_2
 
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.imsave(output_dir / "sentinel2_before.png", s2_1_show)
    plt.imsave(output_dir / "sentinel2_after.png", s2_2_show)
    with (output_dir / "sentinel2_acquisition_times.json").open("w") as f:
        json.dump({
            "before": {"requested_window": date_range_t1,
                       "used_acquisitions": acquisition_times["BEFORE"]},
            "after": {"requested_window": date_range_t2,
                      "used_acquisitions": acquisition_times["AFTER"]},
        }, f, indent=2)
    print("Saved Sentinel-2 images and acquisition times under outputs/")
 
    # CROMA overlay on the "after" optical image (top 5% change only)
    cmap = plt.get_cmap("magma")
    change_filled = np.nan_to_num(change)
    norm = np.clip(change_filled / c_vmax, 0, 1)
    overlay = cmap(norm).astype(np.float32)
    overlay[..., 3] = np.where(change_filled > c_thr, 0.8, 0.0)
    del norm, change_filled
 
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
 