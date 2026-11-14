"""Numerical transforms shared by optical and SAR providers."""
from typing import Tuple

import numpy as np


def sar_to_normalized_db(power: np.ndarray, db_min: float = -30.0, db_max: float = 0.0) -> np.ndarray:
    """Convert non-negative power to clipped dB values scaled to [-1, 1]."""
    db = 10.0 * np.log10(np.maximum(power.astype(np.float32), 1e-10))
    return np.clip((np.clip(db, db_min, db_max) - db_min) / (db_max - db_min) * 2 - 1, -1, 1)


def normalized_to_db(value: np.ndarray, db_min: float = -30.0, db_max: float = 0.0) -> np.ndarray:
    """Invert :func:`sar_to_normalized_db`."""
    return ((value + 1.0) / 2.0) * (db_max - db_min) + db_min


def augment_flips_rot(rng: np.random.Generator, *arrays: np.ndarray):
    """Apply one identical random geometric transform to all arrays."""
    out = list(arrays)
    if rng.random() < 0.5:
        out = [np.flip(a, axis=-1).copy() for a in out]
    if rng.random() < 0.5:
        out = [np.flip(a, axis=-2).copy() for a in out]
    k = int(rng.integers(0, 4))
    return tuple(np.rot90(a, k, axes=(-2, -1)).copy() for a in out)
