# NISAR change detection

Pair-specific UCDFormer adaptation for NISAR GCOV SAR imagery. All locations use one shared processing policy. Inputs contain only acquisition paths and AOI; common polarization channels, geometry and NISAR normalization statistics are derived during preparation. Outputs describe observable change; independent detection accuracy has not been established.

- [Run guide](NISAR_RUN_GUIDE.md): setup, preprocessing, training and inference.
- [Step-by-step visual runner](PIPELINE_WALKTHROUGH.md): run `run_pipeline_steps.py` locally to inspect preprocessing, VGG, FCM, adaptive thresholds, seed agreement and RF decisions.
- [EDA](outputs/eda/README.md): all before/after exploration reports, retained unchanged.
- [Latest saved location results](outputs/results/README.md): images and comparisons.
- [Work queue](WORK_QUEUE.md): remaining work and experiment history.
- [Archived experiments](old/README.md): original optical code and superseded Etna runs, including the preferred conservative mask.

## Active files

| Path | Purpose |
|---|---|
| `nisar/` | Reader, preprocessing, model, detection, review and exports |
| `UCDFormer/networks.py` | Original network definitions used by the active model |
| `run_nisar.py`, `configs/*_run.json` | Single-location pipeline and data-only inputs |
| `configs/pipeline.json` | Shared algorithm policy for every pair |
| `run_all_locations.py` | Generic serial runs over input files |
| `make_eda.py`, `alternative_eda.py`, `spain_reference_eda.py`, `mozambique_context.py` | EDA generation |
| `download*.py`, `background_nisar.py`, `planning/` | Data acquisition, provenance and catalog discovery |
| `organize_outputs.py`, `embed_output_images.py`, `refresh_run_reviews.py`, `validate_outputs.py` | Result galleries and checks |
| `data/`, `weights/` | Retained raw inputs, manifests and pretrained weights |
| `tests/`, `requirements-nisar.txt` | Tests and runtime dependencies |

Saved location results predate the current shared policy and were not regenerated. New runs create isolated output folders. The batch runner never rewrites input files or chooses behavior by city name. Processing and fitted values are recorded in run outputs; see the run guide for the input schema and supported-data requirements.

```bash
python3 -m unittest discover -s tests -v
```

Use the host interpreter documented in the run guide. GPU training requires host CUDA access.
