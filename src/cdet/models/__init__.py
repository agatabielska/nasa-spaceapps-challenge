"""Model zoo. Importing this package registers every architecture below."""
from src.cdet.models.registry import MODEL_REGISTRY, build_model, register_model
from src.cdet.models import early_fusion, siamese_unet  # noqa: F401  (registration side effect)

__all__ = ["MODEL_REGISTRY", "build_model", "register_model"]
