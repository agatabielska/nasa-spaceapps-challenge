"""Model-agnostic pixel attribution for change maps."""
from typing import Dict, Optional, Tuple

import numpy as np
import torch


def _target(logits: torch.Tensor, target: Optional[torch.Tensor]) -> torch.Tensor:
    if target is None:
        return torch.sigmoid(logits).mean()
    return (torch.sigmoid(logits) * target).sum() / target.sum().clamp_min(1.0)


def gradient_saliency(
    module: torch.nn.Module,
    t1: np.ndarray,
    t2: np.ndarray,
    target: Optional[np.ndarray] = None,
) -> Dict[str, np.ndarray]:
    """Return input-gradient maps for each acquisition and channel.

    The output contains ``t1``, ``t2`` and ``combined`` maps in [C,H,W]/[H,W].
    A target mask can focus attribution on known or baseline-detected fire pixels.
    """
    device = next(module.parameters()).device
    a = torch.tensor(t1, dtype=torch.float32, device=device).unsqueeze(0).requires_grad_()
    b = torch.tensor(t2, dtype=torch.float32, device=device).unsqueeze(0).requires_grad_()
    y = None if target is None else torch.tensor(target, dtype=torch.float32, device=device)[None, None]
    module.zero_grad(set_to_none=True)
    score = _target(module(a, b), y)
    score.backward()
    s1, s2 = a.grad.detach().abs()[0].cpu().numpy(), b.grad.detach().abs()[0].cpu().numpy()
    combined = np.sqrt((s1 ** 2 + s2 ** 2).sum(axis=0))
    return {"t1": s1, "t2": s2, "combined": combined, "score": np.asarray(float(score.detach().cpu()))}


@torch.no_grad()
def occlusion_saliency(
    module: torch.nn.Module,
    t1: np.ndarray,
    t2: np.ndarray,
    patch_size: int = 16,
    stride: int = 8,
    fill_value: float = 0.0,
) -> np.ndarray:
    """Estimate pixel importance by occluding patches in both dates."""
    device = next(module.parameters()).device
    a = torch.tensor(t1, dtype=torch.float32, device=device)[None]
    b = torch.tensor(t2, dtype=torch.float32, device=device)[None]
    baseline = torch.sigmoid(module(a, b)).mean()
    _, h, w = t1.shape
    result = torch.zeros((h, w), device=device)
    counts = torch.zeros((h, w), device=device)
    for y in range(0, h, stride):
        for x in range(0, w, stride):
            y2, x2 = min(y + patch_size, h), min(x + patch_size, w)
            aa, bb = a.clone(), b.clone()
            aa[..., y:y2, x:x2] = fill_value
            bb[..., y:y2, x:x2] = fill_value
            drop = (baseline - torch.sigmoid(module(aa, bb)).mean()).clamp_min(0)
            result[y:y2, x:x2] += drop
            counts[y:y2, x:x2] += 1
    return (result / counts.clamp_min(1)).cpu().numpy()
