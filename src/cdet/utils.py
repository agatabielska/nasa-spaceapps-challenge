"""Small helpers shared across the package."""
import time

import pytorch_lightning as pl
import torch.nn as nn


def set_seed(seed: int) -> None:
    """Seed python, numpy, torch and dataloader workers."""
    pl.seed_everything(seed, workers=True)


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def count_parameters(model: nn.Module) -> int:
    """Number of trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
