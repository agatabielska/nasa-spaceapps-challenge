"""Exploratory data analysis plots: understand the data before modelling."""
from typing import Dict, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np

from src.cdet.data.base import Scene
from src.cdet.data.transforms import normalized_to_db
from src.cdet.viz.common import compute_limits, downsample, to_rgb


def plot_oscd_scene(scene: Scene, percentiles=(2, 98)):
    """T1 | T2 | ground truth | ground truth over T2 for one optical scene."""
    limits = compute_limits([scene.t1, scene.t2], percentiles)
    rgb1, rgb2 = to_rgb(scene.t1, limits), to_rgb(scene.t2, limits)
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8))
    axes[0].imshow(rgb1, interpolation="nearest"); axes[0].set_title("Time 1")
    axes[1].imshow(rgb2, interpolation="nearest"); axes[1].set_title("Time 2")
    axes[2].imshow(scene.mask, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    axes[2].set_title("Ground-truth change")
    axes[3].imshow(rgb2, interpolation="nearest")
    axes[3].imshow(np.ma.masked_where(~scene.mask, scene.mask), cmap="autumn", alpha=0.7, vmin=0, vmax=1)
    axes[3].set_title("Ground truth over T2")
    for ax in axes:
        ax.axis("off")
    h, w = scene.mask.shape
    fig.suptitle(
        f"{scene.name}  |  {w}x{h} px  |  changed: {int(scene.mask.sum()):,} px "
        f"({scene.mask.mean():.2%})"
    )
    fig.tight_layout()
    return fig


def plot_class_balance(masks: Dict[str, np.ndarray]):
    """Fraction of changed pixels per scene (log axis): shows the class imbalance."""
    names = sorted(masks, key=lambda n: masks[n].mean())
    fractions = [max(masks[n].mean(), 1e-6) for n in names]
    total = sum(int(m.sum()) for m in masks.values()) / sum(m.size for m in masks.values())
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(names)), 4))
    ax.bar(names, fractions)
    ax.set_yscale("log")
    ax.axhline(total, color="r", ls="--", label=f"overall: {total:.2%}")
    ax.set_ylabel("changed pixel fraction")
    ax.set_title("Class imbalance per scene")
    ax.legend()
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right")
    fig.tight_layout()
    return fig


def plot_band_distributions(scene: Scene, band_names: Sequence[str], bins: int = 80):
    """Histogram of every band at T1 vs T2 (reveals radiometric / seasonal shifts)."""
    n = scene.t1.shape[0]
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.2), squeeze=False)
    for i, ax in enumerate(axes[0]):
        ax.hist(scene.t1[i].ravel(), bins=bins, alpha=0.6, label="T1", density=True)
        ax.hist(scene.t2[i].ravel(), bins=bins, alpha=0.6, label="T2", density=True)
        ax.set_title(band_names[i] if i < len(band_names) else f"band {i}")
        ax.legend()
    fig.suptitle(f"{scene.name}: band distributions (normalised values)")
    fig.tight_layout()
    return fig


def plot_sar_scene(
    scene: Scene,
    channel_names: Sequence[str],
    db_min: float = -30.0,
    db_max: float = 0.0,
    max_pixels: int = 2000,
    diff_range_db: float = 10.0,
):
    """Per polarization: T1 (dB) | T2 (dB) | T2 - T1 log-ratio | dB histograms (| GT)."""
    n = scene.t1.shape[0]
    has_gt = scene.mask is not None
    cols = 4 + int(has_gt)
    fig, axes = plt.subplots(n, cols, figsize=(4.2 * cols, 4 * n), squeeze=False)
    for i in range(n):
        t1_db = normalized_to_db(downsample(scene.t1[i], max_pixels), db_min, db_max)
        t2_db = normalized_to_db(downsample(scene.t2[i], max_pixels), db_min, db_max)
        row = axes[i]
        row[0].imshow(t1_db, cmap="gray", vmin=db_min, vmax=db_max); row[0].set_title(f"{channel_names[i]} T1 [dB]")
        row[1].imshow(t2_db, cmap="gray", vmin=db_min, vmax=db_max); row[1].set_title(f"{channel_names[i]} T2 [dB]")
        im = row[2].imshow(t2_db - t1_db, cmap="RdBu_r", vmin=-diff_range_db, vmax=diff_range_db)
        row[2].set_title(f"{channel_names[i]} T2 - T1 [dB]")
        fig.colorbar(im, ax=row[2], fraction=0.046)
        row[3].hist(t1_db.ravel(), bins=100, alpha=0.6, label="T1", density=True)
        row[3].hist(t2_db.ravel(), bins=100, alpha=0.6, label="T2", density=True)
        row[3].set_xlabel("dB"); row[3].legend()
        if has_gt:
            row[4].imshow(downsample(scene.mask, max_pixels), cmap="gray"); row[4].set_title("Ground truth")
        for ax in (row[0], row[1], row[2]) + ((row[4],) if has_gt else ()):
            ax.axis("off")
    fig.suptitle(f"{scene.name}: SAR backscatter")
    fig.tight_layout()
    return fig


def plot_difference_map(diff: np.ndarray, change: Optional[np.ndarray] = None, title: str = "Log-ratio change"):
    """Mean absolute dB difference with an optional thresholded binary map beside it."""
    cols = 2 if change is not None else 1
    fig, axes = plt.subplots(1, cols, figsize=(6.5 * cols, 5.5), squeeze=False)
    im = axes[0, 0].imshow(downsample(diff), cmap="viridis")
    axes[0, 0].set_title(title)
    fig.colorbar(im, ax=axes[0, 0], fraction=0.046)
    if change is not None:
        axes[0, 1].imshow(downsample(change), cmap="gray")
        axes[0, 1].set_title("Thresholded (mean + k*std)")
    for ax in axes.ravel():
        ax.axis("off")
    fig.tight_layout()
    return fig
