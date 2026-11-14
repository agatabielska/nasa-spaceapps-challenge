"""Shared plotting helpers (contrast stretch, figure -> array)."""
from typing import Sequence, Tuple

import numpy as np


def _three_channels(img: np.ndarray) -> np.ndarray:
    """First three channels as RGB; fewer channels are shown as grey."""
    return img[:3] if img.shape[0] >= 3 else np.repeat(img[:1], 3, axis=0)


def compute_limits(images: Sequence[np.ndarray], percentiles=(2, 98)) -> Tuple[np.ndarray, np.ndarray]:
    """Per-channel stretch limits shared by several images, so colours stay comparable."""
    stacked = np.concatenate([_three_channels(im).reshape(3, -1) for im in images], axis=1)
    low, high = np.percentile(stacked, percentiles, axis=1)
    return low, high


def to_rgb(img: np.ndarray, limits: Tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """[C, H, W] normalised image -> [H, W, 3] float in [0, 1] using ``limits``."""
    low, high = limits
    rgb = (_three_channels(img) - low[:, None, None]) / np.maximum(high - low, 1e-8)[:, None, None]
    return np.clip(rgb.transpose(1, 2, 0), 0.0, 1.0)


def downsample(array: np.ndarray, max_pixels: int = 2000) -> np.ndarray:
    """Stride-subsample the last two axes so plots of huge SAR scenes stay light."""
    step = max(1, max(array.shape[-2:]) // max_pixels)
    return array[..., ::step, ::step]


def fig_to_array(fig) -> np.ndarray:
    """Render a matplotlib figure to an RGB uint8 array (for W&B image logging)."""
    fig.canvas.draw()
    return np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
