"""Classical, label-free change detection for SAR (useful when no ground truth exists)."""
from typing import Tuple

import numpy as np


def log_ratio_change(t1_db: np.ndarray, t2_db: np.ndarray, k: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """Log-ratio operator: mean over polarizations of |dB(T2) - dB(T1)|, thresholded.

    Args:
        t1_db, t2_db: [C, H, W] backscatter in dB.
        k: pixels more than ``k`` standard deviations above the mean difference are "change".
    Returns:
        (difference image [H, W], boolean change mask [H, W])
    """
    diff = np.nanmean(np.abs(t2_db - t1_db), axis=0)
    threshold = np.nanmean(diff) + k * np.nanstd(diff)
    return diff, diff > threshold
