"""One generic LightningModule for every architecture / loss combination."""
from typing import Any, Dict, Optional

import pytorch_lightning as pl
import torch
from omegaconf import DictConfig
from pytorch_lightning.loggers import WandbLogger
from torchmetrics import MetricCollection
from torchmetrics.classification import (
    BinaryF1Score, BinaryJaccardIndex, BinaryPrecision, BinaryRecall,
)

from src.cdet.models.losses import build_loss, loss_params_from_config
from src.cdet.models.metrics import ThresholdSweep
from src.cdet.models.registry import build_model


class ChangeDetectionModule(pl.LightningModule):
    """Training / evaluation logic shared by all models.

    Logged per stage (train/, val/, test/): loss, f1, precision, recall, iou at the fixed
    ``threshold``. Val and test also log ``best_f1`` / ``best_threshold`` from an exact
    threshold sweep (use the val threshold when reporting test, see ``cdet.evaluate``).
    On test, W&B additionally gets an F1-vs-threshold curve, a precision-recall curve
    and a confusion-matrix table.
    """

    def __init__(
        self,
        model_name: str,
        in_channels: int,
        base_channels: int = 16,
        loss_name: str = "bce_dice",
        loss_params: Optional[Dict[str, Any]] = None,
        lr: float = 1e-4,
        weight_decay: float = 1e-4,
        scheduler: str = "cosine",
        t_max: int = 80,
        eta_min: float = 1e-6,
        threshold: float = 0.5,
        sweep_bins: int = 100,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.net = build_model(model_name, in_channels, base_channels)
        self.loss_fn = build_loss(loss_name, **(loss_params or {}))
        self._build_metrics(threshold)
        self.val_sweep = ThresholdSweep(sweep_bins)
        self.test_sweep = ThresholdSweep(sweep_bins)

    # -- construction ---------------------------------------------------------------
    @classmethod
    def from_config(cls, cfg: DictConfig, in_channels: int) -> "ChangeDetectionModule":
        """Build from the experiment config; ``in_channels`` comes from the datamodule."""
        return cls(
            model_name=cfg.model.name,
            in_channels=in_channels,
            base_channels=cfg.model.base_channels,
            loss_name=cfg.loss.name,
            loss_params=loss_params_from_config(cfg.loss),
            lr=cfg.optim.lr,
            weight_decay=cfg.optim.weight_decay,
            scheduler=cfg.optim.scheduler,
            t_max=cfg.optim.t_max,
            eta_min=cfg.optim.eta_min,
            threshold=cfg.trainer.threshold,
        )

    def _build_metrics(self, threshold: float) -> None:
        base = MetricCollection({
            "f1": BinaryF1Score(threshold=threshold),
            "precision": BinaryPrecision(threshold=threshold),
            "recall": BinaryRecall(threshold=threshold),
            "iou": BinaryJaccardIndex(threshold=threshold),
        })
        self.train_metrics = base.clone(prefix="train/")
        self.val_metrics = base.clone(prefix="val/")
        self.test_metrics = base.clone(prefix="test/")

    def set_threshold(self, threshold: float) -> None:
        """Change the decision threshold of the logged metrics (e.g. to the val-tuned one)."""
        self.hparams.threshold = float(threshold)
        self._build_metrics(float(threshold))
        self.to(self.device)

    # -- forward / steps ------------------------------------------------------------
    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        return self.net(x1, x2)

    def _shared_step(self, batch: dict, stage: str) -> torch.Tensor:
        x1, x2, y = batch["t1"], batch["t2"], batch["mask"]
        logits = self(x1, x2)
        loss = self.loss_fn(logits, y)
        probs = torch.sigmoid(logits).detach()

        metrics = getattr(self, f"{stage}_metrics")
        metrics(probs, y.int())
        batch_size = x1.shape[0]
        self.log_dict(metrics, on_step=False, on_epoch=True, batch_size=batch_size)
        self.log(
            f"{stage}/loss", loss, on_step=(stage == "train"), on_epoch=True,
            prog_bar=True, batch_size=batch_size,
        )
        if stage == "val":
            self.val_sweep.update(probs, y)
        elif stage == "test":
            self.test_sweep.update(probs, y)
        return loss

    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "train")

    def validation_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "val")

    def test_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        return self._shared_step(batch, "test")

    def predict_step(self, batch: dict, batch_idx: int, dataloader_idx: int = 0) -> torch.Tensor:
        """Change probabilities [B, 1, H, W]; works for unlabeled batches."""
        return torch.sigmoid(self(batch["t1"], batch["t2"]))

    # -- epoch-end hooks ------------------------------------------------------------
    def _log_sweep(self, sweep: ThresholdSweep, stage: str) -> Dict[str, torch.Tensor]:
        result = sweep.compute()
        self.log(f"{stage}/best_f1", result["best_f1"])
        self.log(f"{stage}/best_threshold", result["best_threshold"])
        sweep.reset()
        return result

    def on_validation_epoch_end(self) -> None:
        self._log_sweep(self.val_sweep, "val")

    def on_test_epoch_end(self) -> None:
        result = self._log_sweep(self.test_sweep, "test")
        self._log_wandb_test_curves(result)

    def _log_wandb_test_curves(self, result: Dict[str, torch.Tensor]) -> None:
        """Push threshold curves and a confusion matrix to W&B (no-op for other loggers)."""
        if not isinstance(self.logger, WandbLogger) or not self.trainer.is_global_zero:
            return
        import wandb

        r = {k: v.detach().cpu() for k, v in result.items()}
        rows = list(zip(
            r["thresholds"].tolist(), r["precision"].tolist(), r["recall"].tolist(), r["f1"].tolist()
        ))
        table = wandb.Table(columns=["threshold", "precision", "recall", "f1"], data=rows)
        k = min(int(round(float(self.hparams.threshold) * self.hparams.sweep_bins)),
                self.hparams.sweep_bins - 1)
        cm = wandb.Table(
            columns=["", "predicted: no change", "predicted: change"],
            data=[
                ["true: no change", int(r["tn"][k]), int(r["fp"][k])],
                ["true: change", int(r["fn"][k]), int(r["tp"][k])],
            ],
        )
        self.logger.experiment.log({
            "test/f1_vs_threshold": wandb.plot.line(table, "threshold", "f1", title="Test F1 vs threshold"),
            "test/precision_recall_curve": wandb.plot.line(
                table, "recall", "precision", title="Test precision-recall"
            ),
            "test/confusion_matrix": cm,
        })

    # -- optimisation ---------------------------------------------------------------
    def configure_optimizers(self):
        optimizer = torch.optim.Adam(
            self.parameters(), lr=self.hparams.lr, weight_decay=self.hparams.weight_decay
        )
        if self.hparams.scheduler == "none":
            return optimizer
        if self.hparams.scheduler == "cosine":
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=self.hparams.t_max, eta_min=self.hparams.eta_min
            )
            return {"optimizer": optimizer, "lr_scheduler": {"scheduler": scheduler, "interval": "epoch"}}
        raise ValueError(f"Unknown scheduler '{self.hparams.scheduler}'")
