"""OSCD GeoTIFF loader kept compatible with the original experiments."""
from pathlib import Path

import numpy as np
import rasterio

from src.cdet.data.base import Scene

TRAIN_CITIES = ["abudhabi", "aguasclaras", "beihai", "bercy", "bordeaux", "cupertino",
                "hongkong", "mumbai", "nantes", "paris", "pisa", "rennes", "saclay_e"]
TEST_CITIES = ["brasilia", "chongqing", "dubai", "lasvegas", "milano", "montpellier",
               "norcia", "rio", "saclay_w", "valencia"]


def _read(directory: Path, bands):
    arrays = []
    for band in bands:
        with rasterio.open(directory / f"{band}.tif") as src:
            arrays.append(src.read(1).astype(np.float32))
    return np.stack(arrays)


def load_scene(data_dir: str, city: str, bands, scale: float = 5000.0) -> Scene:
    root = Path(data_dir) / "Onera Satellite Change Detection dataset - Images" / city
    t1, t2 = _read(root / "imgs_1_rect", bands), _read(root / "imgs_2_rect", bands)
    t1, t2 = np.clip(t1 / scale * 2 - 1, -1, 1), np.clip(t2 / scale * 2 - 1, -1, 1)
    return Scene(t1, t2, name=city, band_names=tuple(bands))
