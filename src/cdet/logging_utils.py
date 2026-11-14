"""Experiment tracking: run naming, W&B / CSV loggers, model watching."""
from pathlib import Path
from typing import Optional

from omegaconf import DictConfig
from pytorch_lightning.loggers import CSVLogger, Logger, WandbLogger

from src.cdet.utils import timestamp


def resolve_run_name(
    cfg: DictConfig,
    template: Optional[str] = None,
    use_explicit_name: bool = True,
    **extra,
) -> str:
    """Run name = ``logging.run_name`` if set, else the formatted template.

    Template fields: {model} {loss} {dataset} {seed} {experiment} {timestamp} plus any
    keyword passed in ``extra`` (e.g. study / trial / fold during tuning). Nothing is
    hardcoded: change the name with ``--run-name`` or ``logging.run_name_template=...``.
    """
    if use_explicit_name and cfg.logging.run_name:
        return cfg.logging.run_name
    fields = dict(
        model=cfg.model.name, loss=cfg.loss.name, dataset=cfg.data.name, seed=cfg.seed,
        experiment=cfg.experiment, timestamp=timestamp(),
    )
    fields.update(extra)
    return (template or cfg.logging.run_name_template).format(**fields)


def build_logger(
    cfg: DictConfig,
    run_name: str,
    run_dir: Path,
    group: Optional[str] = None,
    job_type: str = "train",
    config: Optional[dict] = None,
) -> Logger:
    """W&B logger (online/offline) or a local CSV logger when ``logging.mode=disabled``."""
    lc = cfg.logging
    if lc.mode == "disabled":
        return CSVLogger(save_dir=str(run_dir), name="csv", version="")
    return WandbLogger(
        project=lc.project, entity=lc.entity, name=run_name, group=group or lc.group,
        job_type=job_type, tags=list(lc.tags), notes=lc.notes, save_dir=str(run_dir),
        log_model=lc.log_model, offline=(lc.mode == "offline"), save_code=lc.save_code,
        config=config,
    )


def watch_model(logger: Logger, module, cfg: DictConfig) -> None:
    """Log gradient / weight histograms to W&B (``logging.watch``)."""
    if isinstance(logger, WandbLogger) and cfg.logging.watch != "none":
        logger.watch(module, log=cfg.logging.watch, log_freq=cfg.logging.watch_freq)


def finish_logger(logger: Logger) -> None:
    """Close the W&B run so the next run (e.g. next Optuna trial) starts clean."""
    if isinstance(logger, WandbLogger):
        import wandb

        wandb.finish()
