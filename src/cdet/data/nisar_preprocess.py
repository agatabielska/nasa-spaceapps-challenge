"""NISAR GCOV download and extraction helpers.

The HDF5 layout differs slightly between product revisions, so extraction searches
dataset paths by frequency and polarization instead of hard-coding one revision.
If no unambiguous dataset is found, the error lists candidates for inspection.
"""
import re
from pathlib import Path
from typing import Dict, Optional, Sequence

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin


def acquisition_time(granule: str) -> str:
    match = re.search(r"(\d{8}T\d{6})", granule)
    if not match:
        raise ValueError(f"Cannot find acquisition timestamp in granule ID: {granule}")
    return match.group(1)


def download_granules(granules: Sequence[str], raw_dir: str) -> None:
    try:
        import asf_search
    except ImportError as exc:
        raise RuntimeError("Install the nisar extra before downloading from ASF") from exc
    target = Path(raw_dir)
    target.mkdir(parents=True, exist_ok=True)
    for granule in granules:
        products = asf_search.granule_search(granule)
        if not products:
            raise RuntimeError(f"ASF returned no product for {granule}")
        products[0].download(path=str(target))


def _dataset_candidates(handle: h5py.File, frequency: str, polarization: str):
    frequency_name = f"frequency{frequency.upper()}"
    found = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            lowered = name.lower()
            parts = lowered.strip("/").split("/")
            if frequency_name.lower() in parts and parts[-1] == polarization.lower():
                found.append(name)

    handle.visititems(visit)
    return found


def extract_gcov_to_geotiff(
    h5_path: str,
    output_paths: Dict[str, str],
    frequency: str = "A",
    bbox: Optional[Sequence[float]] = None,
    epsg: Optional[int] = None,
) -> None:
    """Extract configured polarization rasters, optionally crop in product CRS."""
    with h5py.File(h5_path, "r") as handle:
        for polarization, output in output_paths.items():
            candidates = _dataset_candidates(handle, frequency, polarization)
            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected one dataset for {frequency}/{polarization}, found {candidates}. "
                    "Inspect the product with h5ls and configure the correct product."
                )
            data = np.asarray(handle[candidates[0]][()], dtype=np.float32)
            if data.ndim != 2:
                raise ValueError(f"{candidates[0]} is not a 2-D raster: shape={data.shape}")
            grid = handle[candidates[0]].parent
            x = np.asarray(grid["xCoordinates"][()])
            y = np.asarray(grid["yCoordinates"][()])
            if data.shape != (len(y), len(x)):
                raise ValueError(f"Coordinate dimensions do not match {candidates[0]}")
            rows, cols = np.arange(len(y)), np.arange(len(x))
            if bbox:
                min_x, min_y, max_x, max_y = bbox
                cols = np.flatnonzero((x >= min_x) & (x <= max_x))
                rows = np.flatnonzero((y >= min_y) & (y <= max_y))
                if not len(rows) or not len(cols):
                    raise ValueError(
                        f"bbox {list(bbox)} does not intersect NISAR grid "
                        f"x=[{x.min()}, {x.max()}], y=[{y.min()}, {y.max()}]"
                    )
                data = data[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
                x, y = x[cols.min():cols.max() + 1], y[rows.min():rows.max() + 1]
            dx = float(abs(np.median(np.diff(x)))) if len(x) > 1 else 1.0
            dy = float(abs(np.median(np.diff(y)))) if len(y) > 1 else 1.0
            transform = from_origin(float(x[0]) - dx / 2, float(y[0]) + dy / 2, dx, dy)
            projection = grid["projection"].attrs
            detected_epsg = int(projection.get("epsg_code", 0)) or epsg
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(
                path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
                count=1, dtype="float32", crs=f"EPSG:{detected_epsg}" if detected_epsg else None,
                transform=transform, compress="deflate",
            ) as dst:
                dst.write(data, 1)
