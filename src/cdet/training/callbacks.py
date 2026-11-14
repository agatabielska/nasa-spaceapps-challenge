"""Custom Lightning callbacks."""
from typing import Optional

import matplotlib.pyplot as plt
import pytorch_lightning as pl
import torch
from pytorch_lightning.loggers import WandbLogger
from torch.utils.data import default_collate

from src.cdet.viz.common import compute_limits, fig_to_array
from src.cdet.viz.predictions import plot_prediction


class BestMetric(pl.Callback):
    """Track the best value of a monitored metric (also works without checkpointing)."""

    def __init__(self, monitor: str, mode: str = "max"):
        self.monitor, self.mode = monitor, mode
        self.best: Optional[float] = None

    def on_validation_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        if trainer.sanity_checking:
            return
        value = trainer.callback_metrics.get(self.monitor)
        if value is None:
            return
        value = float(value)
        better = self.best is None or (value > self.best if self.mode == "max" else value < self.best)
        if better:
            self.best = value


class PredictionLogger(pl.Callback):
    """Every N epochs log the same fixed validation patches with predictions to W&B.

    Panels: T1 | T2 | ground truth | P(change) | TP/FP/FN map. Watching these evolve is the
    fastest way to spot label problems, empty-mask validation sets or collapsed predictions.
    """

    def __init__(self, every_n_epochs: int = 5, num_samples: int = 4):
        self.every_n_epochs = every_n_epochs
        self.num_samples = num_samples
        self._batch: Optional[dict] = None

    def _fixed_batch(self, trainer: pl.Trainer) -> dict:
        if self._batch is None:
            loaders = trainer.val_dataloaders
            loader = loaders[0] if isinstance(loaders, (list, tuple)) else loaders
            dataset = loader.dataset
            n = min(self.num_samples, len(dataset))
            idxs = torch.linspace(0, len(dataset) - 1, n).long().tolist()  # spread over the set
            self._batch = default_collate([dataset[i] for i in idxs])
        return self._batch

    def on_validation_epoch_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        if trainer.sanity_checking or not trainer.is_global_zero:
            return
        if not isinstance(trainer.logger, WandbLogger):
            return
        if trainer.current_epoch % self.every_n_epochs != 0:
            return

        batch = self._fixed_batch(trainer)
        with torch.no_grad():
            probs = torch.sigmoid(
                pl_module(batch["t1"].to(pl_module.device), batch["t2"].to(pl_module.device))
            ).cpu().numpy()[:, 0]
        threshold = float(pl_module.hparams.threshold)

        images, captions = [], []
        for i in range(probs.shape[0]):
            t1, t2 = batch["t1"][i].numpy(), batch["t2"][i].numpy()
            fig = plot_prediction(
                t1, t2, probs[i], threshold, gt=batch["mask"][i, 0].numpy(),
                limits=compute_limits([t1, t2]),
            )
            images.append(fig_to_array(fig))
            plt.close(fig)
            captions.append(f"epoch {trainer.current_epoch} sample {i}")
        trainer.logger.log_image(
            key="val/predictions", images=images, caption=captions, step=trainer.global_step
        )
