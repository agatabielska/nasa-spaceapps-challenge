"""Single entry point that trains one model from a config (used by train.py and tuning)."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import pytorch_lightning as pl
from omegaconf import DictConfig, OmegaConf
from pytorch_lightning.callbacks import EarlyStopping, LearningRateMonitor, ModelCheckpoint
from pytorch_lightning.loggers import WandbLogger

from src.cdet.config import save_config
from src.cdet.data import build_datamodule
from src.cdet.logging_utils import build_logger, finish_logger, watch_model
from src.cdet.models.lightning_module import ChangeDetectionModule
from src.cdet.training.callbacks import BestMetric, PredictionLogger
from src.cdet.utils import count_parameters, set_seed


@dataclass
class TrainResult:
    run_name: str
    run_dir: Path
    best_score: float  # best value of trainer.monitor on the validation set
    best_ckpt_path: str
    test_metrics: List[dict] = field(default_factory=list)


def build_callbacks(cfg: DictConfig, run_dir: Path, with_wandb: bool):
    """Checkpointing, early stopping, best-metric tracking and W&B-only callbacks."""
    tc = cfg.trainer
    best = BestMetric(tc.monitor, tc.monitor_mode)
    checkpoint = ModelCheckpoint(
        dirpath=str(run_dir / "checkpoints"), monitor=tc.monitor, mode=tc.monitor_mode,
        save_top_k=1, filename="best-epoch{epoch:03d}", auto_insert_metric_name=False,
    )
    callbacks = [
        checkpoint,
        EarlyStopping(monitor=tc.monitor, mode=tc.monitor_mode, patience=tc.patience),
        best,
        LearningRateMonitor(logging_interval="epoch"),
    ]
    if with_wandb:
        callbacks.append(
            PredictionLogger(cfg.logging.prediction_log_every_n_epochs, cfg.logging.num_prediction_samples)
        )
    return callbacks, checkpoint, best


def run_training(
    cfg: DictConfig,
    *,
    run_name: str,
    train_cities: Optional[Sequence[str]] = None,
    val_cities: Optional[Sequence[str]] = None,
    group: Optional[str] = None,
    job_type: str = "train",
    extra_config: Optional[dict] = None,
) -> TrainResult:
    """Train one model end to end and (optionally) test the best checkpoint.

    Everything that identifies the run (resolved config, seed, data stats, parameter count,
    git/code snapshot via W&B) is logged, so any run can be reproduced from its W&B page.
    """
    set_seed(cfg.seed)
    run_dir = Path(cfg.output_dir) / cfg.experiment / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    save_config(cfg, run_dir / "config.yaml")

    datamodule = build_datamodule(cfg.data, train_cities=train_cities, val_cities=val_cities)
    datamodule.setup("fit")
    module = ChangeDetectionModule.from_config(cfg, in_channels=datamodule.num_channels)

    full_config = OmegaConf.to_container(cfg, resolve=True)
    if extra_config:
        full_config["extra"] = extra_config
    logger = build_logger(cfg, run_name, run_dir, group=group, job_type=job_type, config=full_config)
    logger.log_hyperparams({
        "data_stats": datamodule.describe(),
        "n_parameters": count_parameters(module),
        "run_name": run_name,
    })
    watch_model(logger, module, cfg)

    callbacks, checkpoint, best = build_callbacks(cfg, run_dir, isinstance(logger, WandbLogger))
    tc = cfg.trainer
    trainer = pl.Trainer(
        max_epochs=tc.max_epochs, accelerator=tc.accelerator, devices=tc.devices,
        precision=tc.precision, deterministic=tc.deterministic,
        gradient_clip_val=tc.gradient_clip_val, log_every_n_steps=tc.log_every_n_steps,
        fast_dev_run=tc.fast_dev_run, logger=logger, callbacks=callbacks,
        default_root_dir=str(run_dir),
    )

    test_metrics: List[dict] = []
    try:
        trainer.fit(module, datamodule=datamodule)
        if tc.run_test and datamodule.has_test and not tc.fast_dev_run:
            test_metrics = trainer.test(module, datamodule=datamodule, ckpt_path="best")
    finally:
        finish_logger(logger)

    return TrainResult(
        run_name=run_name, run_dir=run_dir,
        best_score=best.best if best.best is not None else float("nan"),
        best_ckpt_path=checkpoint.best_model_path, test_metrics=test_metrics,
    )
