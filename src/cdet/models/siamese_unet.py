"""Siamese U-Net: a shared encoder processes both dates, features are fused in the decoder."""
from typing import Tuple

import torch
import torch.nn as nn

from src.cdet.models.blocks import DoubleConv, pad_to_multiple
from src.cdet.models.registry import register_model


@register_model("siamese_unet")
class SiameseUNet(nn.Module):
    """Two-level Siamese U-Net.

    Args:
        fusion: "concat" concatenates the features of both dates (default);
                "diff" uses |f(T1) - f(T2)| (FC-Siam-diff style) and has fewer parameters.
    """

    def __init__(self, in_channels: int, base_channels: int = 16, fusion: str = "concat"):
        super().__init__()
        if fusion not in {"concat", "diff"}:
            raise ValueError(f"fusion must be 'concat' or 'diff', got {fusion!r}")
        self.fusion = fusion
        b = base_channels
        k = 2 if fusion == "concat" else 1  # number of feature maps entering each fusion point

        # Shared (Siamese) encoder
        self.enc1 = DoubleConv(in_channels, b)
        self.enc2 = DoubleConv(b, 2 * b)
        self.pool = nn.MaxPool2d(2)

        self.bottleneck = DoubleConv(k * 2 * b, 8 * b)

        self.upconv2 = nn.ConvTranspose2d(8 * b, 4 * b, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(4 * b + k * 2 * b, 4 * b)
        self.upconv1 = nn.ConvTranspose2d(4 * b, 2 * b, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(2 * b + k * b, 2 * b)
        self.out_conv = nn.Conv2d(2 * b, 1, kernel_size=1)

    def _encode(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        skip1 = self.enc1(x)
        skip2 = self.enc2(self.pool(skip1))
        return self.pool(skip2), skip1, skip2

    def _fuse(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        if self.fusion == "concat":
            return torch.cat([a, b], dim=1)
        return torch.abs(a - b)

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        h, w = x1.shape[-2:]
        x1, x2 = pad_to_multiple(x1, 4), pad_to_multiple(x2, 4)
        f1, s1_1, s2_1 = self._encode(x1)
        f2, s1_2, s2_2 = self._encode(x2)

        x = self.bottleneck(self._fuse(f1, f2))
        x = self.dec2(torch.cat([self.upconv2(x), self._fuse(s2_1, s2_2)], dim=1))
        x = self.dec1(torch.cat([self.upconv1(x), self._fuse(s1_1, s1_2)], dim=1))
        return self.out_conv(x)[..., :h, :w]


@register_model("siamese_unet_diff")
class SiameseUNetDiff(SiameseUNet):
    """Siamese U-Net with absolute-difference fusion."""

    def __init__(self, in_channels: int, base_channels: int = 16):
        super().__init__(in_channels, base_channels, fusion="diff")
