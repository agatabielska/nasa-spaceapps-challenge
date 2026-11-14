"""Prediction visualisations: probability map, binary mask and TP/FP/FN error map."""
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from src.cdet.viz.common import compute_limits, downsample, to_rgb

_COLORS = {"TP": (0.1, 0.8, 0.1), "FP": (0.9, 0.1, 0.1), "FN": (0.1, 0.3, 0.95)}


def error_map(pred: np.ndarray, gt: np.ndarray) -> np.ndarray:
    """RGB map: green = true positive, red = false alarm, blue = missed change, black = TN."""
    pred, gt = pred.astype(bool), gt.astype(bool)
    out = np.zeros(pred.shape + (3,), dtype=np.float32)
    out[pred & gt] = _COLORS["TP"]
    out[pred & ~gt] = _COLORS["FP"]
    out[~pred & gt] = _COLORS["FN"]
    return out


def plot_prediction(
    t1: np.ndarray,
    t2: np.ndarray,
    prob: np.ndarray,
    threshold: float,
    gt: Optional[np.ndarray] = None,
    limits: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    title: Optional[str] = None,
    max_pixels: int = 2000,
):
    """T1 | T2 | [ground truth] | probability | [error map] (or binary prediction w/o GT)."""
    t1, t2, prob = downsample(t1, max_pixels), downsample(t2, max_pixels), downsample(prob, max_pixels)
    gt = None if gt is None else downsample(gt, max_pixels)
    limits = limits or compute_limits([t1, t2])
    pred = prob >= threshold

    panels = [("T1", to_rgb(t1, limits), {}), ("T2", to_rgb(t2, limits), {})]
    if gt is not None:
        panels.append(("Ground truth", gt, {"cmap": "gray", "vmin": 0, "vmax": 1}))
    panels.append(("P(change)", prob, {"cmap": "magma", "vmin": 0, "vmax": 1}))
    if gt is not None:
        panels.append((f"Errors @ {threshold:.2f}", error_map(pred, gt), {}))
    else:
        panels.append((f"Prediction @ {threshold:.2f}", pred, {"cmap": "gray", "vmin": 0, "vmax": 1}))

    fig, axes = plt.subplots(1, len(panels), figsize=(3.6 * len(panels), 3.8))
    for ax, (name, image, kwargs) in zip(np.atleast_1d(axes), panels):
        ax.imshow(image, interpolation="nearest", **kwargs)
        ax.set_title(name, fontsize=9)
        ax.axis("off")
    if gt is not None:
        np.atleast_1d(axes)[-1].legend(
            handles=[Patch(color=c, label=k) for k, c in _COLORS.items()],
            loc="lower right", fontsize=7, framealpha=0.8,
        )
    if title:
        fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    return fig
