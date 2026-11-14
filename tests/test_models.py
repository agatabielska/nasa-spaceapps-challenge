import pytest
import torch

from src.cdet.models import MODEL_REGISTRY, build_model
from src.cdet.models.losses import BCEDiceLoss, DiceLoss, FocalLoss


@pytest.mark.parametrize("name", sorted(MODEL_REGISTRY))
@pytest.mark.parametrize("size", [(96, 96), (50, 70)])  # second case is not divisible by 4
def test_model_output_shape(name, size):
    model = build_model(name, in_channels=4, base_channels=8)
    x1, x2 = torch.randn(2, 4, *size), torch.randn(2, 4, *size)
    assert model(x1, x2).shape == (2, 1, *size)


@pytest.mark.parametrize("loss", [FocalLoss(), DiceLoss(), BCEDiceLoss()])
def test_losses_are_finite_and_nonnegative(loss):
    logits, target = torch.randn(2, 1, 16, 16), (torch.rand(2, 1, 16, 16) > 0.9).float()
    value = loss(logits, target)
    assert torch.isfinite(value) and value >= 0


def test_focal_prefers_correct_confident_prediction():
    target = torch.ones(1, 1, 8, 8)
    assert FocalLoss()(torch.full_like(target, 5.0), target) < FocalLoss()(torch.full_like(target, -5.0), target)
