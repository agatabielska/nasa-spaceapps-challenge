"""Run a trained model on full scenes (tiled) and load checkpoints."""
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from src.cdet.models.lightning_module import ChangeDetectionModule


def load_module(ckpt_path: str, device: Optional[str] = None) -> ChangeDetectionModule:
    """Load a trained module (hyperparameters are stored inside the checkpoint)."""
    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    module = ChangeDetectionModule.load_from_checkpoint(ckpt_path, map_location=device)
    return module.to(device).eval()


@torch.no_grad()
def predict_scene(module: ChangeDetectionModule, t1: np.ndarray, t2: np.ndarray, tile: int = 256) -> np.ndarray:
    """Change probabilities [H, W] for a full [C, H, W] image pair, processed in tiles.

    Tiles do not overlap (simple, memory-safe); for seamless maps add overlap + blending.
    """
    device = module.device
    c, h, w = t1.shape
    pad_h, pad_w = (-h) % tile, (-w) % tile
    x1 = F.pad(torch.from_numpy(np.array(t1, dtype=np.float32))[None], (0, pad_w, 0, pad_h), mode="reflect")
    x2 = F.pad(torch.from_numpy(np.array(t2, dtype=np.float32))[None], (0, pad_w, 0, pad_h), mode="reflect")
    out = torch.zeros(1, 1, h + pad_h, w + pad_w)
    for y in range(0, h + pad_h, tile):
        for x in range(0, w + pad_w, tile):
            a = x1[..., y:y + tile, x:x + tile].to(device)
            b = x2[..., y:y + tile, x:x + tile].to(device)
            out[..., y:y + tile, x:x + tile] = torch.sigmoid(module(a, b)).cpu()
    return out[0, 0, :h, :w].numpy()
