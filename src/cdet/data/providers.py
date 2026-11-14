"""Composable local raster provider and temporal pairing.

Acquisition discovery is deliberately independent of a catalogue. Downloaders can
write GeoTIFFs using any API (ASF, Copernicus, STAC, or a local export), then point
the provider at them. This keeps credentials and catalogue-specific code outside
the model.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import rasterio

from src.cdet.data.base import Scene


@dataclass(frozen=True)
class RasterAcquisition:
    date: str
    files: Tuple[str, ...]
    source: str = "local"
    bands: Tuple[str, ...] = ()


@dataclass
class TemporalSeries:
    acquisitions: List[RasterAcquisition]
    scenes: List[np.ndarray]
    dates: List[str]
    band_names: Tuple[str, ...]
    crs: Optional[str] = None
    transform: Optional[object] = None

    def pair(self, first: int, second: int) -> Scene:
        return Scene(
            self.scenes[first], self.scenes[second], name=f"{self.dates[first]}_{self.dates[second]}",
            dates=(self.dates[first], self.dates[second]), band_names=self.band_names,
            crs=self.crs, transform=self.transform,
        )


class LocalRasterProvider:
    """Read one GeoTIFF per band and enforce spatial alignment."""

    def load(self, acquisition: RasterAcquisition) -> Tuple[np.ndarray, Optional[str], Optional[object]]:
        arrays = []
        crs = transform = None
        reference_shape = None
        for filename in acquisition.files:
            with rasterio.open(filename) as src:
                arr = src.read(1).astype(np.float32)
                if reference_shape is None:
                    reference_shape, crs, transform = arr.shape, str(src.crs), src.transform
                elif arr.shape != reference_shape:
                    raise ValueError(f"Unaligned raster {filename}: {arr.shape} != {reference_shape}")
                elif str(src.crs) != crs or src.transform != transform:
                    raise ValueError(f"Unaligned raster georeferencing: {filename}")
                arrays.append(arr)
        if not arrays:
            raise ValueError(f"Acquisition {acquisition.date!r} has no raster files")
        return np.stack(arrays), crs, transform


def build_temporal_series(
    acquisitions: Sequence[RasterAcquisition],
    provider: Optional[LocalRasterProvider] = None,
) -> TemporalSeries:
    """Load chronologically sorted acquisitions from any provider implementation."""
    provider = provider or LocalRasterProvider()
    ordered = sorted(acquisitions, key=lambda a: a.date)
    scenes, crs, transform = [], None, None
    for acquisition in ordered:
        image, current_crs, current_transform = provider.load(acquisition)
        if scenes and (image.shape != scenes[0].shape or current_crs != crs or current_transform != transform):
            raise ValueError("All temporal acquisitions must be co-registered with equal CRS and transform")
        scenes.append(image)
        crs, transform = crs or current_crs, transform or current_transform
    if not scenes:
        raise ValueError("At least one acquisition is required")
    bands = ordered[0].bands or tuple(f"band_{i}" for i in range(scenes[0].shape[0]))
    return TemporalSeries(ordered, scenes, [a.date for a in ordered], tuple(bands), crs, transform)


def parse_manifest(path: str) -> List[RasterAcquisition]:
    """Read a simple CSV manifest: date,source,band1.tif,band2.tif,... ."""
    import csv

    rows = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if not row or row[0].startswith("#"):
                continue
            if row[0].lower() == "date":
                continue
            rows.append(RasterAcquisition(row[0], tuple(row[2:]), row[1] if len(row) > 1 else "local"))
    return rows
