"""Custom metrics."""
from typing import Dict

import torch
from torchmetrics import Metric


class ThresholdSweep(Metric):
    """Exact precision / recall / F1 at ``bins`` decision thresholds in one pass.

    Keeps only two histograms of predicted probabilities (positives / negatives), so
    memory is O(bins) regardless of dataset size. A pixel is predicted positive at
    threshold ``k / bins`` iff ``floor(prob * bins) >= k``.
    """

    full_state_update = False

    def __init__(self, bins: int = 100):
        super().__init__()
        self.bins = bins
        self.add_state("pos_hist", default=torch.zeros(bins, dtype=torch.long), dist_reduce_fx="sum")
        self.add_state("neg_hist", default=torch.zeros(bins, dtype=torch.long), dist_reduce_fx="sum")

    def update(self, probs: torch.Tensor, target: torch.Tensor) -> None:
        idx = (probs.detach().reshape(-1).float() * self.bins).long().clamp_(0, self.bins - 1)
        positive = target.detach().reshape(-1) > 0.5
        self.pos_hist += torch.bincount(idx[positive], minlength=self.bins)
        self.neg_hist += torch.bincount(idx[~positive], minlength=self.bins)

    def compute(self) -> Dict[str, torch.Tensor]:
        # tp[k] = positives whose bin index >= k  (reverse cumulative sum)
        tp = self.pos_hist.flip(0).cumsum(0).flip(0).float()
        fp = self.neg_hist.flip(0).cumsum(0).flip(0).float()
        total_pos, total_neg = self.pos_hist.sum().float(), self.neg_hist.sum().float()
        fn, tn = total_pos - tp, total_neg - fp
        precision = tp / (tp + fp).clamp(min=1.0)
        recall = tp / total_pos.clamp(min=1.0)
        f1 = 2.0 * tp / (2.0 * tp + fp + fn).clamp(min=1.0)
        thresholds = torch.arange(self.bins, device=f1.device).float() / self.bins
        best = f1.argmax()
        return {
            "thresholds": thresholds, "precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "best_f1": f1[best], "best_threshold": thresholds[best],
        }
