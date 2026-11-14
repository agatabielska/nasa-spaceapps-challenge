"""Model registry: add an architecture with ``@register_model("name")`` and select it
from a config with ``model.name=name``. No other file needs to change.

Contract: ``forward(x1, x2) -> logits`` with x1, x2 shaped [B, C, H, W] and
logits shaped [B, 1, H, W].
"""
from typing import Callable, Dict

import torch.nn as nn

MODEL_REGISTRY: Dict[str, Callable[..., nn.Module]] = {}


def register_model(name: str):
    """Class decorator that adds a model to the registry under ``name``."""

    def decorator(cls):
        if name in MODEL_REGISTRY:
            raise KeyError(f"Model '{name}' is already registered.")
        MODEL_REGISTRY[name] = cls
        return cls

    return decorator


def build_model(name: str, in_channels: int, base_channels: int, **kwargs) -> nn.Module:
    """Instantiate a registered model. ``in_channels`` = channels per acquisition date."""
    if name not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model '{name}'. Available: {sorted(MODEL_REGISTRY)}")
    return MODEL_REGISTRY[name](in_channels=in_channels, base_channels=base_channels, **kwargs)
