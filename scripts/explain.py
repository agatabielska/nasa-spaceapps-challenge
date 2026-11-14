"""Create pixel-level foundation-model change maps for temporal pairs.

Example:
  python scripts/explain.py -c configs/nisar_unlabeled.yaml --nisar --model croma
"""
import importlib.util
import multiprocessing
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
import torch
import torch.nn.functional as F

from src.cdet.cli import build_parser, parse_config
from src.cdet.data.providers import (
    RasterAcquisition,
    build_temporal_series,
    parse_manifest,
)
from src.cdet.explainability import gradient_saliency, occlusion_saliency
from src.cdet.data.nisar_preprocess import acquisition_time, extract_gcov_to_geotiff


_CROMA_SOURCE = "https://raw.githubusercontent.com/antofuller/CROMA/main/use_croma.py"
_CROMA_WEIGHTS = "https://huggingface.co/antofuller/CROMA/resolve/main/CROMA_base.pt"
_WORKER_MODEL = None
_WORKER_MODEL_NAME = None
_WORKER_METHOD = None
_WORKER_TILE_STRIDE = None
_WORKER_BATCH_SIZE = None
_WORKER_OUTPUT_DIR = None


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        print(f"Downloading {url} ...", flush=True)
        urllib.request.urlretrieve(url, destination)


def _load_croma(cache_dir: Path, device: torch.device):
    try:
        import einops  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("CROMA requires einops; install the foundation extra") from exc
    source = cache_dir / "use_croma.py"
    weights = cache_dir / "CROMA_base.pt"
    _download(_CROMA_SOURCE, source)
    _download(_CROMA_WEIGHTS, weights)
    spec = importlib.util.spec_from_file_location("croma_runtime", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load downloaded CROMA source: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.PretrainedCROMA(
        pretrained_path=str(weights), size="base", modality="SAR", image_resolution=120
    )
    return model.to(device).eval()


def _load_model(
    model_name: str,
    ckpt: Optional[str],
    foundation_dir: Path,
    device: torch.device,
):
    if model_name == "checkpoint":
        if not ckpt:
            raise ValueError("--ckpt is required when --model=checkpoint")
        from src.cdet.inference import load_module

        return load_module(ckpt, device=str(device))
    return _load_croma(foundation_dir, device)


def _init_worker(
    model_name: str,
    ckpt: Optional[str],
    foundation_dir: str,
    device_name: str,
    method: str,
    tile_stride: int,
    batch_size: int,
    output_dir: str,
) -> None:
    """Load one independent model copy per worker, including onto its GPU."""
    global _WORKER_MODEL, _WORKER_MODEL_NAME, _WORKER_METHOD
    global _WORKER_TILE_STRIDE, _WORKER_BATCH_SIZE, _WORKER_OUTPUT_DIR
    device = torch.device(device_name)
    _WORKER_MODEL = _load_model(model_name, ckpt, Path(foundation_dir), device)
    _WORKER_MODEL_NAME = model_name
    _WORKER_METHOD = method
    _WORKER_TILE_STRIDE = tile_stride
    _WORKER_BATCH_SIZE = batch_size
    _WORKER_OUTPUT_DIR = Path(output_dir)


def _explain_scene(task: tuple[np.ndarray, np.ndarray, str]) -> str:
    t1, t2, scene_name = task
    if _WORKER_MODEL is None:
        raise RuntimeError("explain worker was not initialized with a model")
    if _WORKER_MODEL_NAME == "croma":
        if t1.shape[0] != 2:
            raise ValueError(
                f"CROMA SAR mode requires exactly two related bands, got {t1.shape[0]}"
            )
        maps = {
            "combined": _croma_change_map(
                _WORKER_MODEL, t1, t2,
                stride=_WORKER_TILE_STRIDE, batch_size=_WORKER_BATCH_SIZE,
            )
        }
        method_name = "croma_embedding_change"
    elif _WORKER_METHOD == "gradient":
        maps = gradient_saliency(_WORKER_MODEL, t1, t2)
        method_name = _WORKER_METHOD
    else:
        maps = {"combined": occlusion_saliency(_WORKER_MODEL, t1, t2)}
        method_name = _WORKER_METHOD

    stem = _WORKER_OUTPUT_DIR / f"{scene_name}_{method_name}"
    np.savez_compressed(stem.with_suffix(".npz"), **maps)
    fig, ax = plt.subplots(figsize=(7, 6))
    image = maps["combined"]
    im = ax.imshow(image, cmap="magma")
    ax.set_title(f"{scene_name}: {_WORKER_METHOD} attribution")
    ax.axis("off")
    fig.colorbar(im, ax=ax, label="relative importance")
    fig.savefig(stem.with_suffix(".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)
    return f"Saved {stem}.npz and {stem}.png"


@torch.no_grad()
def _croma_change_map(
    model, t1: np.ndarray, t2: np.ndarray, tile: int = 120, stride: int = 96,
    batch_size: int = 64,
) -> np.ndarray:
    """Compare local CROMA SAR embeddings with overlap and edge suppression."""
    
    # 1. Rygorystyczna wspólna maska (część wspólna poprawnych danych dla obu obrazów)
    valid_mask = (
        np.isfinite(t1).all(axis=0) & (t1.max(axis=0) > 1e-6) &
        np.isfinite(t2).all(axis=0) & (t2.max(axis=0) > 1e-6)
    )

    device = next(model.parameters()).device
    _, height, width = t1.shape
    output = np.zeros((height, width), dtype=np.float32)
    counts = np.zeros((height, width), dtype=np.float32)
    pending_a, pending_b, pending_coords = [], [], []
    edge_weight = np.outer(np.hanning(tile), np.hanning(tile)).astype(np.float32)
    edge_weight = 0.15 + 0.85 * edge_weight

    def flush() -> None:
        if not pending_a:
            return
        a = torch.cat(pending_a, dim=0)
        b = torch.cat(pending_b, dim=0)
        e1 = F.normalize(model(SAR_images=a)["SAR_encodings"], dim=-1)
        e2 = F.normalize(model(SAR_images=b)["SAR_encodings"], dim=-1)
        changes = (1.0 - (e1 * e2).sum(dim=-1)).reshape(-1, 1, 15, 15)
        for change, (y, x, y2, x2) in zip(changes, pending_coords):
            patch = F.interpolate(
                change[None], size=(y2 - y, x2 - x), mode="bilinear", align_corners=False
            )
            h, w = y2 - y, x2 - x
            weight = edge_weight[:h, :w]
            output[y:y2, x:x2] += patch[0, 0].cpu().numpy() * weight
            counts[y:y2, x:x2] += weight
        pending_a.clear()
        pending_b.clear()
        pending_coords.clear()

    y_starts = list(range(0, max(height - tile + 1, 1), stride))
    x_starts = list(range(0, max(width - tile + 1, 1), stride))
    if y_starts[-1] != max(height - tile, 0):
        y_starts.append(max(height - tile, 0))
    if x_starts[-1] != max(width - tile, 0):
        x_starts.append(max(width - tile, 0))
    for y in y_starts:
        for x in x_starts:
            y2, x2 = min(y + tile, height), min(x + tile, width)
            
            # COPY jest tu krytyczne, aby nie nadpisać oryginalnych obrazów t1/t2 w pamięci
            a_np = np.asarray(t1[:, y:y2, x:x2], dtype=np.float32).copy()
            b_np = np.asarray(t2[:, y:y2, x:x2], dtype=np.float32).copy()
            tile_mask = valid_mask[y:y2, x:x2]
            
            # --- KLUCZOWA ZMIANA ---
            # Zastępujemy obszary poza twardą, wspólną maską tą samą uśrednioną wartością.
            # Ponieważ sztuczna ramka będzie identyczna w t1 i t2, model nie wykryje na niej zmian.
            has_valid = tile_mask.any()
            for image in (a_np, b_np):
                for channel in image:
                    if has_valid:
                        fill = float(np.nanmedian(channel[tile_mask]))
                    else:
                        fill = 1e-4
                    channel[~tile_mask] = fill

            a = torch.from_numpy(a_np).float()[None].to(device)
            b = torch.from_numpy(b_np).float()[None].to(device)
            a = F.interpolate(a, size=(tile, tile), mode="bilinear", align_corners=False)
            b = F.interpolate(b, size=(tile, tile), mode="bilinear", align_corners=False)
            
            a = torch.log10(a.clamp_min(1e-8))
            b = torch.log10(b.clamp_min(1e-8))
            for value in (a, b):
                value.sub_(value.mean(dim=(-2, -1), keepdim=True)).div_(
                    value.std(dim=(-2, -1), keepdim=True).clamp_min(1e-6)
                )
            pending_a.append(a)
            pending_b.append(b)
            pending_coords.append((y, x, y2, x2))
            if len(pending_a) >= batch_size:
                flush()
    flush()
    
    # 2. Finalne przeliczenie wag i wyzerowanie absolutnie wszystkiego co jest poza poprawnymi danymi
    final_output = output / np.maximum(counts, 1e-6)
    final_output[~valid_mask] = 0.0
    
    return final_output
def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--ckpt", default=None, help="custom Lightning checkpoint (model=checkpoint)")
    parser.add_argument("--manifest", default=None, help="CSV manifest; omit when using --nisar")
    parser.add_argument("--nisar", action="store_true", help="use the two granules in data.nisar")
    parser.add_argument(
        "--model", choices=["croma", "checkpoint"], default="croma",
        help="foundation model to download, or use a local checkpoint",
    )
    parser.add_argument(
        "--device", default="auto", choices=["auto", "cpu", "cuda"],
        help="inference device; auto selects CUDA when available",
    )
    parser.add_argument("--batch-size", type=int, default=64, help="CROMA tile batch size")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="number of processes; each loads its own model on the selected device",
    )
    parser.add_argument(
        "--tile-stride", type=int, default=96,
        help="distance between 120px CROMA tiles; smaller values increase overlap",
    )
    parser.add_argument("--method", choices=["gradient", "occlusion"], default="gradient")
    parser.add_argument("--output", default=None)
    args_cfg, args = parse_config(parser)
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("--device=cuda requested but CUDA is not available")
    device = torch.device(
        "cuda" if args.device == "auto" and torch.cuda.is_available() else
        ("cuda" if args.device == "cuda" else "cpu")
    )
    print(f"Using device: {device}", flush=True)
    if args.nisar:
        nc = args_cfg.data.nisar
        if len(nc.granules) != 2:
            parser.error("data.nisar.granules must contain exactly two granules")
        granules = sorted(nc.granules, key=acquisition_time)
        for granule, output_paths in zip(granules, (nc.t1_files, nc.t2_files)):
            outputs = dict(zip(nc.polarizations, output_paths))
            extract_gcov_to_geotiff(
                str(Path(nc.raw_dir) / f"{granule}.h5"),
                outputs,
                frequency=nc.frequency,
                bbox=list(nc.bbox) if nc.bbox else None,
                epsg=nc.epsg,
            )
        acquisitions = [
            RasterAcquisition(granules[0], tuple(nc.t1_files), "nisar", tuple(nc.polarizations)),
            RasterAcquisition(granules[1], tuple(nc.t2_files), "nisar", tuple(nc.polarizations)),
        ]
        series = build_temporal_series(acquisitions)
    elif args.manifest:
        series = build_temporal_series(parse_manifest(args.manifest))
    else:
        parser.error("provide --manifest PATH or use --nisar")
    out_dir = Path(args.output or args_cfg.output_dir) / "explainability"
    out_dir.mkdir(parents=True, exist_ok=True)
    foundation_dir = Path(args_cfg.output_dir) / "foundation_models"
    if args.model == "croma":
        # Download once before spawning workers so they do not race on the cache.
        _download(_CROMA_SOURCE, foundation_dir / "use_croma.py")
        _download(_CROMA_WEIGHTS, foundation_dir / "CROMA_base.pt")

    tasks = [
        (series.scenes[index], series.scenes[index + 1], f"{series.dates[index]}_{series.dates[index + 1]}")
        for index in range(len(series.scenes) - 1)
    ]
    worker_args = (
        args.model, args.ckpt, str(foundation_dir), str(device), args.method,
        args.tile_stride, args.batch_size, str(out_dir),
    )
    if args.workers == 1:
        _init_worker(*worker_args)
        messages = map(_explain_scene, tasks)
    else:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            initargs=worker_args,
        ) as executor:
            messages = executor.map(_explain_scene, tasks)
            for message in messages:
                print(message, flush=True)
        return
    for message in messages:
        print(message, flush=True)


if __name__ == "__main__":
    main()
