"""Small, source-independent data contracts."""
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class Scene:
    """Aligned image pair in CHW layout, with an optional binary change mask."""

    t1: np.ndarray
    t2: np.ndarray
    mask: Optional[np.ndarray] = None
    name: str = "scene"
    dates: Tuple[str, str] = ("", "")
    band_names: Tuple[str, ...] = ()
    crs: Optional[str] = None
    transform: Optional[object] = None

    def __post_init__(self) -> None:
        if self.t1.ndim != 3 or self.t2.ndim != 3:
            raise ValueError("t1 and t2 must have shape [channels, height, width]")
        if self.t1.shape != self.t2.shape:
            raise ValueError(f"t1/t2 shapes differ: {self.t1.shape} vs {self.t2.shape}")
        if self.mask is not None and self.mask.shape != self.t1.shape[-2:]:
            raise ValueError("mask must have shape [height, width] matching the images")

