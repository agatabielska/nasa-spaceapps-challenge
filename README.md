# cdet – satellite change detection (OSCD optical + NASA NISAR SAR)

Reproducible research code for bi-temporal change detection: a model zoo, two data
modules (OSCD optical, NISAR SAR), Optuna tuning, full Weights & Biases tracking and
data-understanding plots. Everything is driven by YAML configs plus command-line overrides.

> **Status:** this refactor was written without executing any code. Run `pytest` and a
> `trainer.fast_dev_run=true` smoke test first (see below), and check the assumptions
> listed under *Things to verify*.

## Repository layout

```
configs/                 experiment YAMLs (only differences from defaults) + tuned/ (Optuna output)
scripts/                 thin CLIs: train, tune, evaluate, prepare_nisar, visualize
src/cdet/
  config.py              typed config dataclasses (defaults live here), YAML + CLI merging
  cli.py                 shared argparse plumbing
  logging_utils.py       run naming, W&B/CSV logger, model watching
  baselines.py           label-free SAR log-ratio change detection
  inference.py           load checkpoint, tiled full-scene prediction
  evaluate.py            val-tuned threshold -> test evaluation
  tuning.py              Optuna K-fold (over cities) search
  data/                  base.py, oscd.py, nisar.py, nisar_preprocess.py, transforms.py
  models/                registry.py, blocks.py, early_fusion.py, siamese_unet.py, losses.py,
                         metrics.py, lightning_module.py (one generic LightningModule)
  training/              runner.py (one training run), callbacks.py
  viz/                   eda.py, predictions.py, common.py
tests/                   shape / loss / metric / transform tests
```

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[nisar,dev]"      # or: pip install -r requirements.txt
cp .env.example .env               # Earthdata + W&B credentials
wandb login
pytest -q
```

## Quick start

The OSCD commands below assume the original dataset is extracted under `oscd_data/`,
with the `Onera Satellite Change Detection dataset - Images` and label directories
inside it.

```bash
# smoke test, no W&B account needed (one batch of train/val)
python -m scripts.train -c configs/oscd_siamese_bcedice.yaml logging.mode=disabled trainer.fast_dev_run=true data.data_dir=oscd_data

# real run; the run name is a variable, never hardcoded
python -m scripts.train -c configs/oscd_siamese_bcedice.yaml --run-name sunet_bcedice_nir_v2 data.data_dir=oscd_data
python -m scripts.train -c configs/oscd_siamese_focal.yaml 'logging.run_name_template="{model}_{loss}_lr{timestamp}"' data.data_dir=oscd_data

# any config value can be overridden
python -m scripts.train -c configs/oscd_siamese_bcedice.yaml optim.lr=0.0003 model.base_channels=32 seed=7 data.data_dir=oscd_data

# hyperparameter search, then train with the winner
python -m scripts.tune -c configs/oscd_siamese_bcedice.yaml tune.n_trials=30 tune.study_name=bcedice_v1 data.data_dir=oscd_data
python -m scripts.train -c configs/oscd_siamese_bcedice.yaml -c configs/tuned/bcedice_v1.yaml data.data_dir=oscd_data

# evaluate a checkpoint (threshold chosen on validation, applied to test)
python -m scripts.evaluate -c configs/oscd_siamese_bcedice.yaml --ckpt outputs/oscd/<run>/checkpoints/best-epoch042.ckpt data.data_dir=oscd_data
```

### NISAR workflow

Edit `data.nisar.granules` in the NISAR YAML config you use to select the two
acquisitions. They are sorted by acquisition time before conversion, with the
earliest used as T1 and the latest as T2.

```bash
python -m scripts.prepare_nisar -c configs/nisar_unlabeled.yaml --download --extract \
       "data.nisar.bbox=[699000,6168000,705000,6175000]"
python -m scripts.visualize --plot nisar -c configs/nisar_unlabeled.yaml     # dB maps, log-ratio, histograms
```
Without ground truth, `NISARDataModule` supports prediction and visualisation only; the
log-ratio baseline gives a label-free change map. Once you have labels (or pseudo-labels from
that baseline) aligned to the cropped GeoTIFFs, set `data.nisar.label_path` and train with
`configs/nisar_supervised.yaml`. Train/val are split spatially (top rows / bottom rows) to
avoid leakage between neighbouring patches.

## Experiment tracking (Weights & Biases)

Every run logs: the full resolved config (also saved to `outputs/<experiment>/<run>/config.yaml`),
data statistics (patch counts, change-pixel fraction per split), parameter count, git/code
snapshot, gradient histograms (`logging.watch`), learning rate, and per stage `loss`, `f1`,
`precision`, `recall`, `iou`. Validation and test also log `best_f1` / `best_threshold` from an exact
threshold sweep. Extra panels: fixed validation patches with TP/FP/FN maps (`val/predictions`),
test F1-vs-threshold and precision-recall curves, a confusion-matrix table, and the best
checkpoint as an artifact (`logging.log_model`).

Naming: `--run-name` / `logging.run_name` wins; otherwise `logging.run_name_template` is
formatted with `{model} {loss} {dataset} {seed} {experiment} {timestamp}`. Tuning runs use
`tune.run_name_template` and are grouped per trial (`<study>_trial003`), one run per fold.
`logging.mode=offline|disabled` works without internet / an account.

## Extending

* **New model:** add a file in `src/cdet/models/`, decorate with `@register_model("name")`,
  import it in `models/__init__.py`, run with `model.name=name`. Contract:
  `forward(x1, x2) -> logits [B,1,H,W]`.
* **New loss:** add a class in `models/losses.py`, register it in `LOSSES` and
  `loss_params_from_config`.
* **New dataset:** subclass `BaseChangeDataModule` (batches are dicts with `t1`, `t2`, `mask`),
  add it to `DATAMODULES` in `data/__init__.py`.
* **New config option:** add a field to the dataclass in `config.py` (typos in YAML/CLI then fail loudly).

### Spain wildfire workflow (multi-sensor and explainability)

The temporal pipeline is source-independent: ASF/NISAR, Copernicus/Sentinel or another
downloader only needs to emit a CSV manifest with rows
`date,source,band_file_1.tif,band_file_2.tif,...`. Files must already be co-registered.
Use adjacent acquisitions to increase temporal density:

```bash
python scripts/explain.py -c configs/wildfire_spain.yaml --ckpt outputs/model.ckpt \
  --manifest data/wildfires/spain/sentinel1.csv --method gradient

# Directly from the two configured NISAR HDF5 granules. CROMA weights are downloaded
# into outputs/foundation_models/ on first run:
pip install -e ".[nisar,foundation]"
python scripts/explain.py -c configs/nisar_unlabeled.yaml --nisar --model croma
```

CROMA uses only the configured two related NISAR SAR bands (`HHHH`, `HVHV`).
Inference uses overlapping 120 px local areas, weighted toward each area's centre to
reduce border artefacts. The default GPU batch is 64; lower it with `--batch-size 16`
if CUDA memory is insufficient. Increase overlap with `--tile-stride 64` if tile
boundaries remain visible. Independent temporal pairs can run in parallel; each
`--workers N` process loads its own model onto the selected device, for example:

```bash
python scripts/explain.py -c configs/nisar_unlabeled.yaml --nisar --model croma \
  --workers 31
```

Each worker holds a full model copy, so reduce `--workers` if GPU memory is insufficient.

`LocalRasterProvider` can be replaced without changing models. The example config
documents NISAR L-band (HHHH/HVHV), Sentinel-1 C-band (VV/VH), and Sentinel-2 optical
bands. `gradient` creates per-channel and combined pixel attribution maps; `occlusion`
is slower but model-agnostic. Attribution shows which pixels drove a detected change,
not fire-probability ground truth.

## Reproducibility

Seeds set for python/numpy/torch/workers (`seed`), `trainer.deterministic=true`, per-worker RNG
for crops, fixed city splits, resolved config saved per run, Optuna study stored in SQLite with a
seeded sampler, and `pip freeze > requirements.lock.txt` recommended after the first working install.
If a CUDA op raises under `deterministic=true`, set `trainer.deterministic=false` and note it in the run.

## What changed relative to the notebooks (bugs fixed)

| Issue in notebooks | Fix |
|---|---|
| `F_ALPHA=0.75,` (trailing comma -> tuple) | config floats; alpha is validated by types |
| "Focal" run actually instantiated the BCE `SiameseUNet` | model and loss are chosen independently (`model.name`, `loss.name`) |
| Focal alpha applied to both classes (no class weighting effect) | alpha_t = alpha for change, 1-alpha for background |
| CV objective never passed fold cities to the datamodule | `OSCDDataModule(train_cities=..., val_cities=...)` |
| Optuna returned the *last-epoch* val F1 | `BestMetric` callback -> best val F1 per fold |
| `wandb.finsh()` typo, `SARDataModule` undefined | `finish_logger`, one datamodule registry |
| Threshold was an Optuna hyperparameter although it only affects the metric | not searched; exact threshold sweep on val, applied to test |
| Global `np.random` in dataloader workers (duplicate crops) | per-worker `Generator` seeded from `torch.initial_seed()` |
| Hardcoded run names, `ckpt_path="best"` on a stale trainer | name template/`--run-name`; evaluate loads an explicit checkpoint |
| Notebook listed the later NISAR granule first | granules are sorted by acquisition time (T1 = earliest) |
| Class imbalance discovered late | `visualize.py --plot oscd-balance`, change fraction logged per split |

Old notebook experiments -> configs: `EarlyFusionCNN` = `oscd_early_fusion.yaml`; `SUNet_bce` =
`oscd_siamese_bce.yaml`; `SUNet_FOCAL-a0.75g2` = `oscd_siamese_focal.yaml`; `SUNetBCEDICE` / paper =
`oscd_siamese_bcedice.yaml`. The Optuna runs = `scripts/tune.py`.

## Things to verify (not executed)

1. NISAR GCOV HDF5 paths/attributes in `data/nisar_preprocess.py` (`h5ls -r file.h5`), especially the EPSG
   lookup; override with `data.nisar.epsg=...` if needed.
2. `asf_search` download call (`product.download(path=..., session=...)`) against your installed version.
3. OSCD folder layout and label encoding (`<city>-cm.tif` background=1/change=2, or `cm.png`).
4. Lightning / W&B API details for your installed versions (`WandbLogger.log_image`, `watch`, `log_model`).
5. `trainer.deterministic=true` with your CUDA ops.

## Suggested next steps

Overlapping-tile blending in `predict_scene`; more models (UNet++, transformer-based, SAR-specific
speckle filtering); weak labels for NISAR from the log-ratio baseline; GitHub Actions running `pytest`
and a `fast_dev_run` on synthetic data.
