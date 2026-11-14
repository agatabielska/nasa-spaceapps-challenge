
"""Sentinel-2 (before/after) + NISAR HH/HV + CROMA change map, parallelised, memory-lean,
resumable and retry-safe.
 
Usage:
  python scripts/compare_optical_copy.py --workers 8 --device auto
  python scripts/compare_optical_copy.py --retries 6 --rounds 4 --clean-scenes
 
Resilience notes:
  * STAC search results are cached as JSON, so a restart doesn't need the network for it.
  * Every scene is processed in three persisted steps, each saved atomically
    (write to .tmp, then os.replace):
        1. warp RGB   -> outputs/cache/scenes/<id>_<gridtag>_rgb.npy
        2. warp SCL   -> outputs/cache/scenes/<id>_<gridtag>_scl.npy
        3. finalize   -> ..._valid.npy + ..._meta.json   (meta.json = "scene is done")
    On restart, finished scenes are skipped entirely, and half-finished scenes resume at
    the step that failed (e.g. RGB is kept if only the SCL download died).
  * Each network step is retried with exponential backoff + jitter, and the asset URL is
    re-signed on every attempt (Planetary Computer SAS tokens expire).
  * If a worker process dies (OOM, broken pool), unfinished scenes are re-queued in a new
    pool for up to --rounds rounds.
  * Scenes that still fail are skipped for this run. If any scene failed, the final mosaic
    is used for this run's plot but NOT cached, so the next run completes the missing
    scenes (reusing everything already downloaded) instead of freezing an incomplete mosaic.
  * Corrupt / unreadable cache files are deleted and recomputed instead of crashing.
  * The median is computed straight from the per-scene .npy files via mmap, in row bands.
"""
import os
os.environ.setdefault("GDAL_CACHEMAX", "128")   # MB per process
 
import argparse
import hashlib
import json
import random
import sys
import time
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
SCENE_DIR = CACHE_DIR / "scenes"
# Sentinel-2 SCL classes to drop: nodata, saturated, cloud shadow, cloud (med/high), cirrus, snow
SCL_BAD = [0, 1, 3, 8, 9, 10, 11]
MIN_USABLE_FRACTION = 0.01
 
 
# ----------------------------------------------------------------------------
# Small robustness helpers
# ----------------------------------------------------------------------------
def retry(fn, what: str, attempts: int = 5, base_delay: float = 2.0, max_delay: float = 60.0):
    """Call fn(); on exception sleep (exponential backoff + jitter) and try again."""
    for a in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if a == attempts:
                raise
            delay = min(base_delay * 2 ** (a - 1), max_delay) + random.uniform(0, 1)
            print(f"    retry {a}/{attempts - 1} for {what}: {type(e).__name__}: "
                  f"{str(e)[:150]} (sleeping {delay:.0f}s)", flush=True)
            time.sleep(delay)
 
 
def atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        np.save(f, arr)
    os.replace(tmp, path)
 
 
def atomic_write_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)
 
 
def safe_unlink(*paths) -> None:
    for p in paths:
        try:
            Path(p).unlink()
        except OSError:
            pass
 
 
def signed(href: str) -> str:
    """Fresh Planetary Computer SAS URL (called on every attempt; tokens expire)."""
    try:
        import planetary_computer
    except ImportError:
        return href
    return planetary_computer.sign(href.split("?")[0])
 
 
def scene_paths(item_id: str, grid: dict, scene_dir=SCENE_DIR) -> dict:
    base = Path(scene_dir) / f"{item_id}_{grid['tag']}"
    return dict(
        rgb=Path(f"{base}_rgb.npy"),
        scl=Path(f"{base}_scl.npy"),
        valid=Path(f"{base}_valid.npy"),
        meta=Path(f"{base}_meta.json"),
    )
 
 
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
    wkt = crs.to_wkt()
    tr = tuple(transform)[:6]
    # Short fingerprint of the grid: per-scene cache files are only reused for the same grid.
    tag = hashlib.md5(f"{wkt}|{tr}|{h}x{w}".encode()).hexdigest()[:10]
    return dict(
        crs_wkt=wkt,                     # plain types so it pickles cleanly to workers
        transform=tr,
        height=h, width=w,
        wgs84_bbox=[min(xs), min(ys), max(xs), max(ys)],
        tag=tag,
    )
 
 
# ----------------------------------------------------------------------------
# Sentinel-2: search (main process, cached) -> warp per scene (worker processes)
# ----------------------------------------------------------------------------
def search_scenes(grid: dict, date_range: str, label: str,
                  max_items: int, max_cloud: float, attempts: int) -> list:
    cache = CACHE_DIR / (
        f"search_{label}_{date_range.replace('/', '_')}_{max_items}_{max_cloud:g}_{grid['tag']}.json"
    )
    if cache.exists():
        try:
            with cache.open() as f:
                scenes = [tuple(s) for s in json.load(f)]
            if scenes:
                print(f"[{label}] {len(scenes)} candidate scenes (cached search)")
                return scenes
        except (OSError, ValueError):
            safe_unlink(cache)
 
    import pystac_client
 
    def _search():
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1")
        return list(catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=grid["wgs84_bbox"],
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": max_cloud}},
        ).items())
 
    items = retry(_search, f"STAC search [{label}]", attempts=attempts)
    if not items:
        raise ValueError(f"No Sentinel-2 scenes for {date_range}")
    items.sort(key=lambda i: (i.properties["eo:cloud_cover"], i.id))
    items = items[:max_items]
    print(f"[{label}] {len(items)} candidate scenes")
    scenes = [
        (label, i.id, i.datetime.isoformat() if i.datetime else None,
         i.assets["visual"].href.split("?")[0],      # unsigned; re-signed in the worker
         i.assets["SCL"].href.split("?")[0])
        for i in items
    ]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(cache, scenes)
    return scenes
 
 
def _gdal_env():
    return rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="1",
        GDAL_HTTP_TIMEOUT="60",
        GDAL_HTTP_CONNECTTIMEOUT="30",
    )
 
 
def _warp_rgb(href, H, W, crs, transform):
    rgb = np.zeros((3, H, W), dtype=np.uint8)       # fresh buffer on every attempt
    with _gdal_env():
        with rasterio.open(signed(href)) as src:
            reproject(
                rasterio.band(src, [1, 2, 3]), rgb,
                dst_transform=transform, dst_crs=crs,
                src_nodata=0, dst_nodata=0, resampling=Resampling.bilinear,
            )
    return rgb
 
 
def _warp_scl(href, H, W, crs, transform):
    scl = np.zeros((H, W), dtype=np.uint8)
    with _gdal_env():
        with rasterio.open(signed(href)) as src:
            reproject(
                rasterio.band(src, 1), scl,
                dst_transform=transform, dst_crs=crs,
                resampling=Resampling.nearest,
            )
    return scl
 
 
def warp_scene(task):
    """Worker process: resumable, retried processing of ONE scene.
 
    Returns (label, item_id, acquired_at, usable_fraction, error_or_None).
    Heavy arrays go to disk, not back through the process pipe.
    """
    (label, item_id, acquired_at, visual_href, scl_href), grid, scene_dir, attempts = task
    H, W = int(grid["height"]), int(grid["width"])
    p = scene_paths(item_id, grid, scene_dir)
    step = "start"
    try:
        Path(scene_dir).mkdir(parents=True, exist_ok=True)
 
        # Already finished in an earlier run?
        if p["meta"].exists():
            try:
                with p["meta"].open() as f:
                    frac = float(json.load(f)["usable_fraction"])
                if frac < MIN_USABLE_FRACTION or p["valid"].exists():
                    return label, item_id, acquired_at, frac, None
            except (OSError, ValueError, KeyError):
                pass
            safe_unlink(p["meta"])   # meta unreadable / valid file missing: redo finalize
 
        crs = CRS.from_wkt(grid["crs_wkt"])
        transform = Affine(*grid["transform"])
 
        step = "rgb"
        if not p["rgb"].exists():
            rgb = retry(lambda: _warp_rgb(visual_href, H, W, crs, transform),
                        f"{item_id} RGB", attempts=attempts)
            atomic_save_npy(p["rgb"], rgb)
            del rgb
 
        step = "scl"
        if not p["scl"].exists():
            scl = retry(lambda: _warp_scl(scl_href, H, W, crs, transform),
                        f"{item_id} SCL", attempts=attempts)
            atomic_save_npy(p["scl"], scl)
            del scl
 
        step = "finalize"
        try:
            rgb_mm = np.load(p["rgb"], mmap_mode="r")
            scl = np.load(p["scl"])
            valid = (rgb_mm.max(axis=0) > 0) & ~np.isin(scl, SCL_BAD)
        except Exception:
            # corrupt intermediate file: drop both so the next round redoes them
            safe_unlink(p["rgb"], p["scl"])
            raise
        frac = float(valid.mean())
        if frac >= MIN_USABLE_FRACTION:
            atomic_save_npy(p["valid"], valid)
        del rgb_mm, scl, valid
        atomic_write_json(p["meta"], dict(usable_fraction=frac, acquired_at=acquired_at))
        safe_unlink(p["scl"])                   # only needed to build `valid`
        if frac < MIN_USABLE_FRACTION:
            safe_unlink(p["rgb"])               # scene barely touches the area
        return label, item_id, acquired_at, frac, None
    except Exception:  # noqa: BLE001
        return (label, item_id, acquired_at, None,
                f"step={step}\n" + traceback.format_exc(limit=4))
 
 
def median_mosaic(rgb_paths, val_paths, device):
    """Per-pixel nanmedian over the scenes, read from per-scene .npy mmaps in row bands.
 
    Returns (HxWx3 float32 in [0,1], valid mask).
    """
    import torch
    rgb_mms = [np.load(p, mmap_mode="r") for p in rgb_paths]
    val_mms = [np.load(p, mmap_mode="r") for p in val_paths]
    _, H, W = rgb_mms[0].shape
    mosaic = np.empty((3, H, W), dtype=np.float32)
    step = 128 if device.type == "cuda" else 48   # small bands keep peak memory low
    for y0 in range(0, H, step):
        y1 = min(y0 + step, H)
        rgb_band = np.stack([m[:, y0:y1] for m in rgb_mms])      # (n,3,h,W) copy of band only
        val_band = np.stack([m[y0:y1] for m in val_mms])         # (n,h,W)
        block = torch.from_numpy(rgb_band).to(device).float()
        mask = torch.from_numpy(val_band).to(device)[:, None]
        block.masked_fill_(~mask, float("nan"))       # in place: no extra copy
        del mask, rgb_band, val_band
        mosaic[:, y0:y1] = torch.nanmedian(block, dim=0).values.cpu().numpy()
        del block
        if device.type == "cuda":
            torch.cuda.empty_cache()
    del rgb_mms, val_mms
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
 
 
def run_tasks(tasks, workers: int, rounds: int):
    """Run scene tasks; re-queue unfinished ones in a fresh pool for up to `rounds` rounds.
 
    Returns (done: {(label,item_id): (acquired_at, frac)}, still_pending: [tasks]).
    """
    done = {}
    pending = list(tasks)
    key = lambda t: (t[0][0], t[0][1])  # noqa: E731
    for rnd in range(1, rounds + 1):
        if not pending:
            break
        if rnd > 1:
            wait = min(10 * (rnd - 1), 60)
            print(f"Round {rnd}/{rounds}: {len(pending)} unfinished scenes, "
                  f"waiting {wait}s before retrying...", flush=True)
            time.sleep(wait)
        n_workers = max(1, min(workers, len(pending)))
        print(f"Warping {len(pending)} scenes on {n_workers} processes...", flush=True)
        shown_error = False
        try:
            with _make_executor(n_workers) as ex:
                fut_map = {ex.submit(warp_scene, t): t for t in pending}
                for k, fut in enumerate(as_completed(fut_map), 1):
                    t = fut_map[fut]
                    try:
                        label, item_id, acquired_at, frac, err = fut.result()
                    except Exception as e:  # noqa: BLE001  (worker died / pool broken)
                        print(f"  worker failure on {t[0][1]}: {type(e).__name__}: {e}",
                              flush=True)
                        continue
                    if err:
                        if not shown_error:
                            print(err, flush=True)
                            shown_error = True
                        print(f"  [{label}] {item_id}: failed ({err.splitlines()[0]}), "
                              f"will retry later", flush=True)
                        continue
                    done[(label, item_id)] = (acquired_at, frac)
                    note = "usable" if frac >= MIN_USABLE_FRACTION else "skipped (no overlap)"
                    print(f"  ({k}/{len(pending)}) [{label}] {item_id}: {frac:.0%} {note}",
                          flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"Process pool error: {type(e).__name__}: {e}", flush=True)
        pending = [t for t in pending if key(t) not in done]
    return done, pending
 
 
def fetch_all_mosaics(grid, jobs: dict, workers: int, device, max_items, max_cloud,
                      attempts: int, rounds: int, clean_scenes: bool):
    """jobs = {label: date_range}. All scenes of all labels share one process pool."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    H, W = int(grid["height"]), int(grid["width"])
    results, todo, acquisition_times = {}, {}, {}
 
    for label, dr in jobs.items():
        cache = CACHE_DIR / f"s2_v4_{label}_{dr.replace('/', '_')}_{H}x{W}.npz"
        if cache.exists():
            try:
                with np.load(cache) as d:
                    rgb, valid = d["rgb"], d["valid"]
                    times = list(d["acquired_at"].astype(str)) if "acquired_at" in d.files else []
                print(f"[{label}] loaded cached mosaic")
                results[label] = (rgb, valid)
                acquisition_times[label] = times
                continue
            except Exception as e:  # noqa: BLE001
                print(f"[{label}] cached mosaic unreadable ({type(e).__name__}); recomputing")
                safe_unlink(cache)
        todo[label] = (dr, cache)
    if not todo:
        return results, acquisition_times
 
    # ---- search (cached) ---------------------------------------------------
    scene_sets, tasks = {}, []
    for label, (dr, _) in todo.items():
        scenes = search_scenes(grid, dr, label, max_items, max_cloud, attempts)
        scene_sets[label] = scenes
        tasks += [(s, grid, str(SCENE_DIR), attempts) for s in scenes]
 
    # ---- warp (resumable, retried, re-queued) ------------------------------
    done, pending = run_tasks(tasks, workers, rounds)
    if pending:
        print(f"WARNING: {len(pending)} scene(s) still failed after {rounds} round(s). "
              f"Re-run the script to resume only those.", flush=True)
 
    # ---- median per label, from the per-scene files ------------------------
    for label, (dr, cache) in todo.items():
        usable, times, n_failed = [], [], 0
        for s in scene_sets[label]:
            r = done.get((label, s[1]))
            if r is None:
                n_failed += 1
                continue
            acq, frac = r
            if frac < MIN_USABLE_FRACTION:
                continue
            usable.append(scene_paths(s[1], grid))
            if acq is not None:
                times.append(acq)
        if not usable:
            raise RuntimeError(f"[{label}] no usable Sentinel-2 data "
                               f"({n_failed} scene(s) failed; re-run to resume)")
        img, valid = median_mosaic([u["rgb"] for u in usable],
                                   [u["valid"] for u in usable], device)
        acquisition_times[label] = times
        print(f"[{label}] mosaic from {len(usable)} scenes, {valid.mean():.0%} covered")
        results[label] = (img, valid)
 
        if n_failed:
            print(f"[{label}] {n_failed} scene(s) missing -> mosaic NOT cached; "
                  f"re-run to complete it (finished scenes are reused).")
            continue
 
        tmp = cache.with_name(cache.stem + ".tmp.npz")
        np.savez_compressed(tmp, rgb=img, valid=valid,
                            acquired_at=np.array(times, dtype=str))
        os.replace(tmp, cache)
 
        if clean_scenes:
            for s in scene_sets[label]:
                safe_unlink(*scene_paths(s[1], grid).values())
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
    ap.add_argument("--retries", type=int, default=5,
                    help="attempts per network step (RGB download, SCL download, STAC search)")
    ap.add_argument("--rounds", type=int, default=3,
                    help="how many times unfinished scenes are re-queued in a fresh pool")
    ap.add_argument("--clean-scenes", action="store_true",
                    help="delete per-scene cache files after a complete mosaic is cached")
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
        args.retries, args.rounds, args.clean_scenes,
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
 