"""Segmentation losses for heavily imbalanced change masks (change << no change)."""
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


class FocalLoss(nn.Module):
    """Binary focal loss: alpha_t * (1 - p_t)^gamma * BCE.

    ``alpha`` weights the positive (change) class and ``1 - alpha`` the background, so
    alpha > 0.5 emphasises the rare class. ``gamma`` down-weights easy pixels.
    """

    def __init__(self, alpha: float = 0.75, gamma: float = 2.0):
        super().__init__()
        self.alpha, self.gamma = alpha, gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        targets = targets.view_as(logits).float()
        bce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
        p_t = torch.exp(-bce)
        alpha_t = self.alpha * targets + (1.0 - self.alpha) * (1.0 - targets)
        return (alpha_t * (1.0 - p_t) ** self.gamma * bce).mean()


class DiceLoss(nn.Module):
    """1 - soft Dice computed over the whole batch (not per image)."""

    def __init__(self, smooth: float = 1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        targets = targets.view_as(logits).float()
        probs = torch.sigmoid(logits).reshape(-1)
        t = targets.reshape(-1)
        dice = (2.0 * (probs * t).sum() + self.smooth) / (probs.sum() + t.sum() + self.smooth)
        return 1.0 - dice


class BCEDiceLoss(nn.Module):
    """bce_weight * BCE + (1 - bce_weight) * Dice."""

    def __init__(self, bce_weight: float = 0.5, smooth: float = 1.0, pos_weight: Optional[float] = None):
        super().__init__()
        self.bce_weight = bce_weight
        self.dice = DiceLoss(smooth)
        self.register_buffer(
            "pos_weight", None if pos_weight is None else torch.tensor(float(pos_weight))
        )

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        targets = targets.view_as(logits).float()
        bce = F.binary_cross_entropy_with_logits(logits, targets, pos_weight=self.pos_weight)
        return self.bce_weight * bce + (1.0 - self.bce_weight) * self.dice(logits, targets)


class WeightedBCELoss(nn.Module):
    """Plain BCE with an optional positive-class weight."""

    def __init__(self, pos_weight: Optional[float] = None):
        super().__init__()
        self.register_buffer(
            "pos_weight", None if pos_weight is None else torch.tensor(float(pos_weight))
        )

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return F.binary_cross_entropy_with_logits(
            logits, targets.view_as(logits).float(), pos_weight=self.pos_weight
        )


LOSSES = {"bce": WeightedBCELoss, "focal": FocalLoss, "dice": DiceLoss, "bce_dice": BCEDiceLoss}


def loss_params_from_config(loss_cfg) -> dict:
    """Pick only the config fields relevant to the selected loss."""
    name = loss_cfg.name
    if name == "bce":
        return {"pos_weight": loss_cfg.pos_weight}
    if name == "focal":
        return {"alpha": loss_cfg.focal_alpha, "gamma": loss_cfg.focal_gamma}
    if name == "dice":
        return {"smooth": loss_cfg.dice_smooth}
    if name == "bce_dice":
        return {
            "bce_weight": loss_cfg.bce_weight, "smooth": loss_cfg.dice_smooth,
            "pos_weight": loss_cfg.pos_weight,
        }
    raise KeyError(f"Unknown loss '{name}'. Available: {sorted(LOSSES)}")


def build_loss(name: str, **params) -> nn.Module:
    if name not in LOSSES:
        raise KeyError(f"Unknown loss '{name}'. Available: {sorted(LOSSES)}")
    return LOSSES[name](**params)
