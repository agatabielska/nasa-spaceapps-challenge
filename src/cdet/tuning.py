"""Hyperparameter search with Optuna: K-fold cross-validation over cities, one W&B run per fold."""
import copy
import random
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import optuna
from omegaconf import DictConfig, OmegaConf

from src.cdet.data.oscd import TRAIN_CITIES
from src.cdet.logging_utils import resolve_run_name
from src.cdet.training.runner import run_training


def city_folds(cities: Sequence[str], n_folds: int, seed: int) -> List[Tuple[List[str], List[str]]]:
    """Shuffle cities and split them into ``n_folds`` (train_cities, val_cities) pairs."""
    cities = list(cities)
    random.Random(seed).shuffle(cities)
    chunks = [cities[i::n_folds] for i in range(n_folds)]
    return [
        ([c for j, chunk in enumerate(chunks) if j != i for c in chunk], chunks[i])
        for i in range(n_folds)
    ]


def make_objective(base_cfg: DictConfig):
    """Build the Optuna objective. The score is the mean over folds of the BEST val metric."""
    tc = base_cfg.tune

    def objective(trial: optuna.Trial) -> float:
        cfg = copy.deepcopy(base_cfg)
        cfg.optim.lr = trial.suggest_float("learning_rate", tc.lr_min, tc.lr_max, log=True)
        cfg.optim.weight_decay = trial.suggest_float(
            "weight_decay", tc.weight_decay_min, tc.weight_decay_max, log=True
        )
        cfg.model.base_channels = trial.suggest_categorical("base_channels", list(tc.base_channels_choices))
        if cfg.loss.name == "bce_dice":
            cfg.loss.bce_weight = trial.suggest_float("bce_weight", tc.bce_weight_min, tc.bce_weight_max)
        cfg.trainer.max_epochs = tc.max_epochs
        cfg.trainer.patience = tc.patience
        cfg.trainer.run_test = False  # never touch the test set while tuning
        cfg.logging.log_model = False  # do not upload a checkpoint for every fold

        scores = []
        for fold, (train_cities, val_cities) in enumerate(city_folds(TRAIN_CITIES, tc.n_folds, cfg.seed)):
            run_name = resolve_run_name(
                cfg, template=tc.run_name_template,
                use_explicit_name=False, study=tc.study_name, trial=trial.number, fold=fold,
            )
            result = run_training(
                cfg, run_name=run_name, train_cities=train_cities, val_cities=val_cities,
                group=f"{tc.study_name}_trial{trial.number:03d}", job_type="tune",
                extra_config={"trial": trial.number, "fold": fold, "params": trial.params,
                              "val_cities": val_cities},
            )
            scores.append(0.0 if np.isnan(result.best_score) else result.best_score)
            trial.report(float(np.mean(scores)), step=fold)
            if trial.should_prune():
                raise optuna.TrialPruned()
        return float(np.mean(scores))

    return objective


def run_study(cfg: DictConfig) -> optuna.Study:
    """Run (or resume) the study and write the best parameters to ``configs/tuned/<study>.yaml``."""
    tc = cfg.tune
    storage = tc.storage
    if storage is None:
        db_dir = Path(cfg.output_dir) / "optuna"
        db_dir.mkdir(parents=True, exist_ok=True)
        storage = f"sqlite:///{db_dir / (tc.study_name + '.db')}"  # resumable & reproducible
    study = optuna.create_study(
        study_name=tc.study_name, storage=storage, load_if_exists=True, direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=cfg.seed),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=3),
    )
    study.optimize(make_objective(cfg), n_trials=tc.n_trials)

    best = study.best_trial
    tuned = {
        "optim": {"lr": best.params["learning_rate"], "weight_decay": best.params["weight_decay"]},
        "model": {"base_channels": best.params["base_channels"]},
    }
    if "bce_weight" in best.params:
        tuned["loss"] = {"bce_weight": best.params["bce_weight"]}
    out = Path("configs/tuned") / f"{tc.study_name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(OmegaConf.create(tuned), out)
    print(f"Best CV score {best.value:.4f}; parameters written to {out}")
    return study
