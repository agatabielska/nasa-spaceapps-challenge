<h1 align="center">EarthSignal — Dancing with the SARs</h1>

<p align="center">
  Our entry for the <b>NASA Space Apps Challenge 2026</b>, challenge <b>"Dancing with the SARs"</b>, by team <b>Blue Trust</b>.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white">
  <img alt="NumPy" src="https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white">
  <img alt="SciPy" src="https://img.shields.io/badge/SciPy-8CAAE6?logo=scipy&logoColor=white">
  <img alt="PyTorch" src="https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white">
  <img alt="scikit-learn" src="https://img.shields.io/badge/scikit--learn-F7931E?logo=scikitlearn&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB">
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white">
  <img alt="Vite" src="https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white">
  <img alt="MapLibre" src="https://img.shields.io/badge/MapLibre-396CB2?logo=maplibre&logoColor=white">
  <img alt="Node.js" src="https://img.shields.io/badge/Node.js-339933?logo=nodedotjs&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white">
  <img alt="LM Studio" src="https://img.shields.io/badge/LM%20Studio-local%20LLM-6E56CF">
  <img alt="NASA NISAR" src="https://img.shields.io/badge/NASA-NISAR-0B3D91?logo=nasa&logoColor=white">
</p>

**What it is.** EarthSignal is a complete application that opens NISAR radar data to everyone. It is made for everyday users and for scientists without a technical background alike. You explore the Earth on a 3D globe and open an analysis of an event: a guided 3D tour over real terrain, before-and-after comparisons, charts and a plain-language summary. It is not limited to two dates: acquisitions from many dates can be compared, so you can follow how a place changes over months on a time slider. It covers different kinds of disasters, from floods, wildfires and eruptions to ground slowly sinking above mines.

**Where it is going.** Today the app presents four case studies we prepared ourselves, including a study of mining subsidence in Silesia, Poland. Our goal is that anyone can pick any part of the Earth and create such a study on their own, and discover changes that nobody has described yet.

**Why.** Radar sees through cloud, smoke and darkness, which is exactly when optical satellites fail and when a disaster is happening. NISAR's L-band data is new and freely available, but hard to read. We turn it into maps and numbers that a non-specialist can follow.

The coloured areas in our outputs are detections by our methods, not validated damage maps.

## Quick start

### The app

Requires Node.js 22.18 or newer.

```sh
cd apps/earthsignal
npm ci
cp .env.example .env.local
npm run dev
```

Open http://127.0.0.1:5173/ for the landing page, `/explore` for the globe and `/show` for the 30-second presentation. The Orbit chat assistant needs a local LM Studio model; without it the rest of the app works and Orbit shows as offline. Details: [apps/earthsignal/README.md](apps/earthsignal/README.md).

### The change-detection pipeline

Requires [uv](https://docs.astral.sh/uv/) and a NASA Earthdata token in `~/.edl_token` or the `EDL_TOKEN` environment variable.

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

## Reproducibility

Seeds set for python/numpy/torch/workers (`seed`), `trainer.deterministic=true`, per-worker RNG
for crops, fixed city splits, resolved config saved per run, Optuna study stored in SQLite with a
seeded sampler, and `pip freeze > requirements.lock.txt` recommended after the first working install.
If a CUDA op raises under `deterministic=true`, set `trainer.deterministic=false` and note it in the run.

## Repository layout

| Folder | Contents |
|---|---|
| `apps/earthsignal/` | The web app: landing page, 3D globe explorer, event analyses, Orbit assistant |
| `model/` | Numerical change detection on NISAR GCOV and GUNW products, plus map and timeline generators |
| `UCDFormer/` | UCDFormer, an unsupervised deep-learning change-detection model, adapted to NISAR |
| `EDA/` | Exploratory analysis of NISAR data for the Ávila wildfire |

## The app (`apps/earthsignal/`)

A React, TypeScript and MapLibre frontend with a small local Node.js API and a SQLite event catalog. No hosted database or cloud API key is needed.

- **Landing page (`/`).** A scroll-driven 3D camera journey that introduces the challenge and the event types, with an autopilot for presenting.
- **Explorer (`/explore`).** A 3D globe with one marker per event, filters by event type and date, and search. Four events have a finished analysis: the Etna eruption, the Ávila wildfire, the Rasuwa flood in Nepal and mining subsidence in Poland. The remaining catalog entries are shown as "Coming soon".
- **Full analysis.** A tabbed view with a guided 3D tour (or a time slider for Silesia), figures, and a short summary. The files come from the pipeline in `model/`.
- **Orbit.** A chat assistant that runs on a local LM Studio model and searches the catalog through typed tools; it cannot run arbitrary SQL or code.
- **`/show`.** A standalone 30-second presentation.
- **`/about`.** The team page.

## The change-detection pipeline (`model/`)

Standard SAR techniques, kept simple and measurable. No training is involved.

**Methods** (`change_methods.py`, `analyze_case.py`):

- **Backscatter.** Log-ratio of HH and HV between two dates, expressed as a robust z-score in units of the scene's own noise, then thresholded and cleaned up. Used for floods, lava and burn scars.
- **Coherence loss.** Interferometric coherence across the event compared with a quiet reference pair of the same track.
- **Displacement.** Unwrapped interferometric phase converted to line-of-sight ground motion in centimetres.

**Cases** (`cases.json`):

| Case | Type | Data |
|---|---|---|
| `nepal_flood` | Rasuwa glacier-collapse flood, Nepal, 26 August 2026 | GCOV pair, GUNW pair and reference |
| `etna` | Etna eruption, August 2026 | GCOV pair, GUNW pair and reference |
| `spain_fire_v2` | Ávila wildfire near Burgohondo, Spain, 22 July 2026 | GCOV pair |
| `silesia` | Mining subsidence, Upper Silesia, Poland, June to October 2026 | GUNW series on two tracks |
| `krzyzowice` | Krzyżowice, Pniówek and Zofiówka at 20 m detail | GUNW series on two tracks |

**Subsidence time series** (`subsidence_series.py`, `subsidence_detail.py`). A chain of 12- and 24-day interferograms is summed into a cumulative subsidence map. A sinking area ("bowl") is kept only if it sinks steadily and a second satellite track sees it too. In Upper Silesia, 25 of 26 candidates were confirmed, covering 11.1 km². `gis_check.py` compares the bowls with official mining-area polygons from the Polish Geological Institute.

**Validation.** `validate_case.py` scores the wildfire mask against an independent optical burn map (Sentinel-2 dNBR) and compares method variants; the best variant reaches an IoU of about 0.30, so the fire mask is a rough indication, not a burn-area product. `compare_optical.py` builds picture pairs of what Sentinel-2 and NISAR saw on the same grid.

**Outputs** (`make_map.py`, `make_map3d.py`, `make_timeline.py`). An interactive Leaflet map, a 3D terrain view with a guided tour, and a time-slider page. Each is written to `output/<case>/`; the 3D and timeline pages are single HTML files that need an internet connection for the basemap and terrain.

**Data access** (`nisar_io.py`, `fetch_case.py`, `fetch_series.py`). A NISAR granule is 1.5 to 8 GB. We open it over HTTPS and read only the chunks inside the bounding box, then cache the window in `model/data/` (not tracked in git).

## UCDFormer (`UCDFormer/`)

An adaptation of UCDFormer, an unsupervised change-detection model, to NISAR GCOV imagery. It uses HH, HV and their difference in dB, combines translation features with physical change thresholds, and trains a random forest on pseudo-labels derived from the pair itself. All locations share one processing policy (`configs/pipeline.json`); the per-location files only name the acquisitions and the area.

The saved Etna result is in `UCDFormer/UCDFormer/final/`. Accuracy has not been independently validated. Start with [UCDFormer/UCDFormer/README.md](UCDFormer/UCDFormer/README.md) and the [pipeline walkthrough](UCDFormer/UCDFormer/PIPELINE_WALKTHROUGH.md).

## EDA (`EDA/`)

`data_analysis.ipynb` explores NISAR L-band data for the Ávila wildfire near Burgohondo: file structure, cropping to the area of interest, data quality, HH and HV backscatter patterns, change between the two dates, and smoothing to bring out the affected area.

## Data and credits

- NISAR L2 GCOV and GUNW products from NASA and ISRO, accessed through the Alaska Satellite Facility.
- Sentinel-2 imagery (Copernicus) through Microsoft Planetary Computer, used for validation and comparison.
- Mining-area polygons from the MIDAS database of the Polish Geological Institute (PIG-PIB).
- Basemap and terrain in the map pages: Esri World Imagery and AWS Terrain Tiles.

## Team Blue Trust

- Agata Bielska
- Michał Leszczyński
- Maria Musiał
- Oliwier Necelman
- Jakub Radziejewski
- Martyna Stasiak
