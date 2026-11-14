"""Evaluate a checkpoint with a threshold chosen on validation data (not on test)."""
import json
from pathlib import Path

import pytorch_lightning as pl
from omegaconf import DictConfig, OmegaConf

from src.cdet.config import save_config
from src.cdet.data import build_datamodule
from src.cdet.logging_utils import build_logger, finish_logger
from src.cdet.models.lightning_module import ChangeDetectionModule
from src.cdet.utils import set_seed


def evaluate_checkpoint(cfg: DictConfig, ckpt_path: str, run_name: str) -> dict:
    """1) sweep thresholds on the validation cities, 2) test once at the best val threshold.

    Selecting the threshold on the test set would leak information, so the test metrics are
    reported at the validation-optimal threshold only (``test/best_f1`` is the oracle value,
    shown for reference).
    """
    set_seed(cfg.seed)
    run_dir = Path(cfg.output_dir) / cfg.experiment / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    save_config(cfg, run_dir / "config.yaml")

    datamodule = build_datamodule(cfg.data)
    module = ChangeDetectionModule.load_from_checkpoint(ckpt_path)
    logger = build_logger(
        cfg, run_name, run_dir, job_type="eval",
        config=OmegaConf.to_container(cfg, resolve=True),
    )
    trainer = pl.Trainer(
        accelerator=cfg.trainer.accelerator, devices=cfg.trainer.devices, logger=logger,
        enable_checkpointing=False, default_root_dir=str(run_dir),
    )
    try:
        trainer.validate(module, datamodule=datamodule)
        threshold = float(trainer.callback_metrics["val/best_threshold"])
        module.set_threshold(threshold)
        logger.log_hyperparams({"eval_checkpoint": str(ckpt_path), "eval_threshold": threshold})
        test = trainer.test(module, datamodule=datamodule)
    finally:
        finish_logger(logger)

    results = {"checkpoint": str(ckpt_path), "threshold": threshold, "test": test}
    (run_dir / "eval_results.json").write_text(json.dumps(results, indent=2))
    return results
