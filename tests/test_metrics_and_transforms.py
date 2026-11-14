import numpy as np
import torch

from src.cdet.data.transforms import augment_flips_rot, normalized_to_db, sar_to_normalized_db
from src.cdet.models.metrics import ThresholdSweep


def test_threshold_sweep_matches_direct_computation():
    torch.manual_seed(0)
    bins = 20
    probs, target = torch.rand(4, 1, 16, 16), (torch.rand(4, 1, 16, 16) > 0.8).float()
    sweep = ThresholdSweep(bins)
    sweep.update(probs, target)
    result = sweep.compute()
    idx = (probs * bins).long().clamp(max=bins - 1)
    for k in (0, 5, 10, 19):
        pred = idx >= k
        tp = (pred & (target > 0.5)).sum().item()
        fp = (pred & (target <= 0.5)).sum().item()
        fn = ((~pred) & (target > 0.5)).sum().item()
        assert result["tp"][k].item() == tp
        assert abs(result["f1"][k].item() - 2 * tp / max(2 * tp + fp + fn, 1)) < 1e-6


def test_augmentation_is_applied_identically_to_all_arrays():
    rng = np.random.default_rng(1)
    a = np.random.rand(3, 8, 8).astype(np.float32)
    out_a, out_b = augment_flips_rot(rng, a, a.copy())
    assert np.array_equal(out_a, out_b)


def test_sar_db_roundtrip():
    power = np.array([[1e-3, 1e-2, 1e-1]], dtype=np.float32)  # -30, -20, -10 dB
    db = normalized_to_db(sar_to_normalized_db(power))
    assert np.allclose(db, [[-30.0, -20.0, -10.0]], atol=1e-3)
