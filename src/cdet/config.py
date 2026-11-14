"""Typed experiment configuration.

Defaults live in the dataclasses below. Experiment YAML files in ``configs/`` only
list what differs from the defaults, and any value can be overridden on the command
line with dotlist syntax (``optim.lr=0.0003``). Unknown keys raise an error, so typos
are caught early.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from omegaconf import DictConfig, OmegaConf

OSCD_RGB = ["B04", "B03", "B02"]
OSCD_RGBN = ["B04", "B03", "B02", "B08"]  # + near infrared


@dataclass
class NisarConfig:
    """NISAR (SAR) data settings. Files are listed in polarization order."""

    granules: List[str] = field(default_factory=list)  # set in a NISAR YAML config
    raw_dir: str = "data/nisar/raw"
    frequency: str = "A"
    polarizations: List[str] = field(default_factory=lambda: ["HHHH", "HVHV"])
    # Crop window in the product CRS (min_x, min_y, max_x, max_y); None = full scene.
    bbox: Optional[List[float]] = None
    epsg: Optional[int] = None  # override if it cannot be read from the HDF5 file
    # GeoTIFFs produced by scripts/prepare_nisar.py (same order as `polarizations`)
    t1_files: List[str] = field(
        default_factory=lambda: ["data/nisar/T1_HHHH.tif", "data/nisar/T1_HVHV.tif"]
    )
    t2_files: List[str] = field(
        default_factory=lambda: ["data/nisar/T2_HHHH.tif", "data/nisar/T2_HVHV.tif"]
    )
    label_path: Optional[str] = None  # ground-truth mask GeoTIFF; None = unlabeled
    db_min: float = -30.0  # backscatter range mapped to [-1, 1]
    db_max: float = 0.0
    val_fraction: float = 0.2  # bottom rows of the scene are held out (spatial split)
    train_stride: Optional[int] = None  # None = patch_size (no overlap)


@dataclass
class DataConfig:
    name: str = "oscd"  # oscd | nisar
    data_dir: str = "data/oscd"
    bands: List[str] = field(default_factory=lambda: list(OSCD_RGBN))
    scale: float = 5000.0  # optical normalisation: x / scale - 1, clipped to [-1, 1]
    patch_size: int = 96
    batch_size: int = 16
    num_workers: int = 4
    crops_per_city: int = 200  # training samples drawn per city per epoch
    train_sampling: str = "change_positive"  # random | change_positive
    val_positive_only: bool = True  # validation uses only patches that contain change
    augment: bool = True
    val_cities: List[str] = field(
        default_factory=lambda: ["abudhabi", "beihai", "bordeaux", "paris"]
    )
    nisar: NisarConfig = field(default_factory=NisarConfig)


@dataclass
class ModelConfig:
    name: str = "siamese_unet"  # see cdet.models.MODEL_REGISTRY
    base_channels: int = 16


@dataclass
class LossConfig:
    name: str = "bce_dice"  # bce | focal | dice | bce_dice
    bce_weight: float = 0.5  # bce_dice: bce_weight * BCE + (1 - bce_weight) * Dice
    dice_smooth: float = 1.0
    focal_alpha: float = 0.75  # weight of the positive (change) class
    focal_gamma: float = 2.0
    pos_weight: Optional[float] = None  # optional BCE positive-class weight


@dataclass
class OptimConfig:
    lr: float = 1e-4
    weight_decay: float = 1e-4
    scheduler: str = "cosine"  # none | cosine
    t_max: int = 80
    eta_min: float = 1e-6


@dataclass
class TrainerConfig:
    max_epochs: int = 200
    patience: int = 30
    monitor: str = "val/f1"
    monitor_mode: str = "max"
    threshold: float = 0.5  # decision threshold used for logged F1/precision/recall/IoU
    accelerator: str = "auto"
    devices: str = "auto"
    precision: str = "32-true"
    deterministic: bool = True
    gradient_clip_val: Optional[float] = None
    log_every_n_steps: int = 10
    run_test: bool = True  # evaluate best checkpoint on the test split after fitting
    fast_dev_run: bool = False  # smoke test: 1 batch of train/val


@dataclass
class LoggingConfig:
    mode: str = "online"  # online | offline | disabled (disabled = local CSV logs only)
    project: str = "change-detection"
    entity: Optional[str] = None
    # Run naming: an explicit `run_name` wins, otherwise the template is formatted.
    # Available fields: {model} {loss} {dataset} {seed} {experiment} {timestamp}
    run_name: Optional[str] = None
    run_name_template: str = "{model}_{loss}_{dataset}_s{seed}"
    group: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    log_model: bool = True  # upload best checkpoint as a W&B artifact
    save_code: bool = True
    watch: str = "gradients"  # gradients | parameters | all | none
    watch_freq: int = 100
    prediction_log_every_n_epochs: int = 5
    num_prediction_samples: int = 4


@dataclass
class TuneConfig:
    study_name: str = "oscd_siamese"
    n_trials: int = 20
    n_folds: int = 3  # K-fold over *cities*
    max_epochs: int = 30
    patience: int = 10
    storage: Optional[str] = None  # None -> sqlite file in output_dir (resumable)
    run_name_template: str = "{study}_t{trial:03d}_f{fold}"
    lr_min: float = 5e-5
    lr_max: float = 3e-4
    weight_decay_min: float = 1e-6
    weight_decay_max: float = 1e-3
    base_channels_choices: List[int] = field(default_factory=lambda: [16, 32])
    bce_weight_min: float = 0.3
    bce_weight_max: float = 0.7


@dataclass
class Config:
    experiment: str = "oscd"
    seed: int = 42
    output_dir: str = "outputs"
    data: DataConfig = field(default_factory=DataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    loss: LossConfig = field(default_factory=LossConfig)
    optim: OptimConfig = field(default_factory=OptimConfig)
    trainer: TrainerConfig = field(default_factory=TrainerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    tune: TuneConfig = field(default_factory=TuneConfig)


def load_config(config_paths: Sequence[str] = (), overrides: Sequence[str] = ()) -> DictConfig:
    """Build a config: dataclass defaults <- YAML files (in order) <- dotlist overrides."""
    cfg = OmegaConf.structured(Config)
    for path in config_paths:
        cfg = OmegaConf.merge(cfg, OmegaConf.load(path))
    if overrides:
        cfg = OmegaConf.merge(cfg, OmegaConf.from_dotlist(list(overrides)))
    return cfg


def save_config(cfg: DictConfig, path) -> None:
    """Write the fully resolved config next to the run outputs (reproducibility)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(cfg, path, resolve=True)
