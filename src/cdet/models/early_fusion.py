"""Lightweight early-fusion CNN baseline: both dates are stacked along channels."""
import torch
import torch.nn as nn

from src.cdet.models.blocks import pad_to_multiple
from src.cdet.models.registry import register_model


@register_model("early_fusion")
class EarlyFusionCNN(nn.Module):
    """Concatenate T1 and T2 (2C channels) -> small encoder/decoder -> 1-channel logits."""

    def __init__(self, in_channels: int, base_channels: int = 16):
        super().__init__()
        b = base_channels
        self.network = nn.Sequential(
            nn.Conv2d(2 * in_channels, b, kernel_size=3, padding=1),
            nn.BatchNorm2d(b),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(b, 2 * b, kernel_size=3, padding=1),
            nn.BatchNorm2d(2 * b),
            nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(2 * b, b, kernel_size=3, padding=1),
            nn.BatchNorm2d(b),
            nn.ReLU(inplace=True),
            nn.Conv2d(b, 1, kernel_size=1),
        )

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        h, w = x1.shape[-2:]
        x = pad_to_multiple(torch.cat([x1, x2], dim=1), 2)
        return self.network(x)[..., :h, :w]
