# Shared NISAR pipeline

Every location uses the same processing policy in [configs/pipeline.json](configs/pipeline.json). Files named `configs/*_run.json` are now **data-only inputs**: `study_id`, `before`, `after`, WGS84 `bbox`, and optional descriptive metadata/history. Algorithm overrides inside those files are rejected. Historical mixed configurations are preserved under `old/configs/before_shared_pipeline/`.

## Run one pair with visualizations

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py --config configs/etna_run.json
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py --config configs/nepal_rasuwagadhi_run.json
```

Both commands apply the identical policy and create fresh timestamped folders under `outputs/walkthroughs/`. Open the printed `steps/index.html`. Use `--settings PATH` to select a shared policy for an experiment; that file contains processing settings only. `--max-updates N` is an optional runtime training-budget override. See [the walkthrough](PIPELINE_WALKTHROUGH.md) for all captured maps.

## Morphology and spatially supported FCM

The encoder uses HH dB, HV dB and HH−HV dB. The experimental VV flag has been removed; quad-pol files still use HH/HV and their difference.

The shared processing policy now applies the following steps to every pair:

1. Close the high and low physical-threshold masks with a disk of approximately 20 m radius (rounded up to native pixels). Preserve existing positives and allow additions only where the full closing dependency neighborhood is measured. No additions are permitted within twice the radius of nodata.
2. Remove physical-support components smaller than 1600 m², using eight-neighbor connectivity so diagonal river/lava segments can belong to one component.
3. Require FCM high-cluster membership of at least 0.75, a margin of 0.15 over the other memberships, and at least 30% similarly confident pixels in a 20 m-radius neighborhood. Then intersect with measured high-threshold pixels retained by the cleaned strong support. Remove positive-seed groups smaller than 800 m². Closing-added pixels are never promoted automatically to certain seeds.
4. Keep weak-support components connected to retained changed seeds. Unchanged seeds are excluded from weak support so inferred short gaps remain uncertain rather than being forced unchanged.
5. Apply RF classification and existing vote gating. Close short gaps in the resulting mask only inside seed-connected physical support and outside unchanged seeds/nodata neighborhoods. Such inferred additions need not pass the RF gate and are explicitly recorded.
6. Remove final components smaller than 3600 m² with eight-neighbor connectivity.

FCM class 2 is the highest relative score cluster, not verified change. The raw cluster map remains visible; `fcm_confident_raw`, `fcm_spatially_supported`, cleaned physical masks, `final_closing_added`, and removed/final masks show the actual processing decisions. Saved rasters include raw, closed and final change masks. The no-translation comparison uses the same closing/component policy. These operations can merge unrelated nearby changes or remove small real fragments; they are an experiment, not an accuracy claim. Previously exported masks remain unchanged. Run into a new directory to apply the updated policy.

## Optional GUNW support before RF

The original no-GUNW path is unchanged. Add `--gunw PATH` to `run_pipeline_steps.py` or `run_nisar.py` to enable isolated coherence corroboration before RF. `run_all_locations.py` also accepts it with exactly one selected input pair. The shared settings file and data JSON files are not modified; the selected source path is recorded in the output acquisition snapshot, and optional processing policy is recorded separately. Repeat the flag when using staged train/infer on that run.

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py \
  --config configs/nepal_rasuwagadhi_run.json \
  --gunw data/raw/NISAR_L2_PR_GUNW_028_098_A_016_029_4000_SH_20260819T233918_20260819T233953_20260831T233918_20260831T233952_X05026_N_F_J_001.h5
```

Additional exact GUNW granules can be downloaded with `python3 -u download_gunw.py --granule GRANULE_ID`. The downloader reuses existing files, resumes partial transfers, records ASF metadata, and checks the existing 100 GB data/artifact budget before downloading. It does not run or modify the pipeline.

The optional path reads HH coherence from the native wrapped-interferogram grid (20 m in this product). It checks track/frame/direction, records both product intervals/releases, and requires temporal overlap. If intervals differ, event bracketing remains the caller's responsibility; overlap alone does not verify it. It never uses unwrapped phase, its component exclusions or the 0.3 phase-display cutoff.

Before calculating scores or fitting the threshold, native GUNW validity is intersected with raw common HH/HV GCOV validity at both dates. Every coarse GUNW footprint must have complete GCOV coverage, including explicit exclusion outside that coverage. Valid measured zero/low coherence remains available; NaN holes never become incoherence=1. Threshold fitting uses only the surviving native samples, before nearest-sample alignment to the GCOV grid. Resampling does not create independent 10 m information.

The experimental incoherence threshold is `max(0.5, median + 1.4826 * max(MAD, 0.001))`, fitted to `1−coherence` on native valid support. It is a robust heuristic, not a calibrated probability or measured pre-event coherence loss. A qualifying GUNW pixel can add weak physical candidates only where physical change exceeds 75% of the local low threshold and the existing seed label is uncertain. Only components connected to existing changed seeds become RF prediction support. Seeds, RF descriptors/vote threshold and VGG training are unchanged; final morphology still applies. Coherence alone cannot declare change. This first experiment expands support and may improve continuity; it is not a noise-removal guarantee. Outside valid GUNW coverage the original GCOV path remains available.

New outputs:

- `gunw_metadata.json`: provenance, compatibility, fitted threshold and masking policy.
- `gunw_native_masked.npz`, `gunw_native_valid_binary.png`: masked native coherence and approved eligibility rule; white included, black excluded.
- `gunw_valid_binary.png`: eligibility after additionally intersecting the existing model's valid coverage/guard. It can exclude more than the native eligibility image for that reason.
- `gunw_comparison.png`: original versus optional result, extra physical support and final differences, using the same model/RF.
- `change_mask_without_gunw.tif`: original result with matching final cleanup, derived using the same RF votes.
- Aligned `gunw_*.tif` layers and step-03 traces showing threshold, eligibility, candidates and added support.

Use a fresh run; existing experiments are preserved. Omitting `--gunw` disables all of these changes. Missing/invalid/mismatched GUNW raises a clear error when the flag is requested rather than silently changing mode.

## Add another city

Create a JSON input containing only the selected data:

```json
{
  "study_id": "my_city",
  "before": "data/raw/before.h5",
  "after": "data/raw/after.h5",
  "bbox": [85.359, 28.2448, 85.3761, 28.2618]
}
```

The example coordinates illustrate the schema, not an arbitrary city's location. Paths are relative to the project root, or absolute. No event-specific architecture, thresholds, weights or patch sizes belong in this file. The pipeline needs compatible local GCOV acquisitions and downloaded pretrained weights; it does not discover or download arbitrary city acquisitions.

## What is computed from each pair

- Common frequency-A HH/HV polarization channels, required at both dates. Extra quad-pol channels remain available for EDA but are not added to the three-channel encoder input. Missing compatible channels cause an explicit error.
- Common geocoded grid, valid measurements and declared fill-value exclusion.
- Shared per-channel percentile bounds and NISAR mean/std, fitted on both dates' training spatial support.
- Spatial training/validation windows: prefer original 256/128 crops where usable, then try fully valid 128, 64, or 32-pixel crops, with a 64-pixel moat, searching either axis. Invalid observations never become training targets. A scene with insufficient measured support is rejected.
- Inference patch size from scene dimensions, capped at 256 and divisible by eight; half-patch overlap. Tiny scenes below the model minimum are rejected.
- Local threshold neighborhood from a common 600 m target width converted to an odd pixel count using native spacing.
- Physical change, VGG scores, FCM centers/memberships, physical local thresholds, pseudo-labels and fitted RF.
- Component-filter pixel count from the common physical-area setting and native affine pixel area.

There are no city-name branches. The shared policy currently uses 3×3 linear-power filtering, a 70% physical / 30% VGG evidence blend, an RF positive-vote threshold of 0.8 and a 3600 m² final minimum component area. These are common algorithm choices, not learned optimal settings. This changes future Etna runs as well as future Rasuwagadhi runs. Existing results were not regenerated. Generic execution does not establish generic detection accuracy.

## Batch execution

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_all_locations.py --visualize-steps
```

This reads all `configs/*_run.json` files without modifying them and creates a fresh `outputs/batches/<timestamp>/` directory containing per-pair runs and `status.json`. Select any subset/new cities with `--inputs FILE1 FILE2`. To reuse completed compatible runs, pass `--resume --output-root PATH`. Incomplete or incompatible output folders are preserved and reported; choose a new root to rerun them. The batch runner performs serial GPU processing and does not publish anything.

## Preparation and staged execution

```bash
python3 run_nisar.py --config configs/etna_run.json --stage prepare --output outputs/my_new_run
python3 run_nisar.py --config configs/etna_run.json --stage train --output outputs/my_new_run
python3 run_nisar.py --config configs/etna_run.json --stage infer --output outputs/my_new_run
```

Use the host interpreter above when the default interpreter lacks dependencies. Training/inference require the selected prepared output folder, matching input and shared settings. Preparation refuses existing artifacts. Input or settings changes require a fresh experiment. Inference also verifies checkpoint normalization. Training starts afresh rather than silently resuming.

## Separate input and run records

- Input JSON: acquisition paths, AOI and descriptive metadata only.
- `input.json`: exact input snapshot for the run.
- `acquisition_metadata.json`: discovered source metadata for both images and requested bounds.
- `pipeline_settings.json`: shared processing policy snapshot.
- `preprocessing.json`: fitted statistics, valid coverage, alignment and chosen spatial split.
- `derived_settings.json`: chosen inference size, local window and polarization channels.
- `effective_config.json`: combined execution record, including runtime overrides and derived values; generated output, never an input data model.
- `pair_metadata.json`: compatibility assembly for existing visualization/export helpers; primary acquisition and preprocessing records above remain separated.
- `pair.npz`: cached processed arrays; training/inference do not reopen HDF5 for every patch.
- Checkpoints, `training_summary.json`, `study.json`, masks, scores and diagnostics: processing results.

Nodata remains excluded. Nearest-valid values provide inference context only; they are not recovered observations. FCM memberships/RF votes are uncalibrated; pseudo-labels are not ground truth. If a seed class is absent, the refined detector reports failure rather than silently manufacturing training examples. A fully automatic runner can identify an unsupported pair; it cannot guarantee a scientifically valid mask for every pair.

## EDA and previous results

All [EDA](outputs/eda/README.md), raw files, pretrained weights and saved results remain available. The catalog at [outputs/results](outputs/results/README.md) describes previous runs; new batch/walkthrough folders have their own reports and logs. The application has not been integrated or published.

## CUDA and inference performance

The default `--device cuda` runs the encoder, translator, decoder, feature interpolation, valid-only minimum/95th-percentile saturation, and L2 scores on CUDA. The main inference loop encodes pre, post and translated images once each, shares post features between the two scores, and transfers only completed score maps to CPU. Opt-in first-tile visualizations copy small selected activation traces; they no longer repeat network passes. Training-target mixing also stays on the tensor device. Mixed precision is not enabled; percentile/saturation arithmetic remains float64 to match the reference calculation.

`run.jsonl` includes `inference_device` (actual model device and GPU name), per-tile scoring/trace timings and peak CUDA memory, plus a tile-loop summary. `inference_performance.json` records the elapsed tile time. Default CUDA execution fails explicitly if CUDA is unavailable; `--device cpu` is an explicit fallback.

HDF5 reads, grid reprojection, SciPy physical filtering/connected components, NumPy FCM, scikit-learn random forests, file exports and plotting remain on CPU. These libraries' current implementations are CPU-based; converting masks or RF inputs to CUDA would not accelerate those calls. GPU scoring removes the major feature-transfer/NumPy bottleneck without replacing those algorithms or adding GPU-specific dependencies.

A synthetic host-GPU check on RTX 5070 Ti used 256×256 tiles and 960 feature channels. Two reference CPU scores took 3.040 s; the fused CUDA scores had a 0.080 s median across three warm iterations (~38× feature-scoring speedup), with zero maximum absolute score difference on that fixture. This excludes network time, preprocessing, classification, plotting and real imagery. It is not an end-to-end runtime claim. Synthetic CUDA equivalence checks passed; no real-data experiment was rerun.

## Verification

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 -m unittest discover -s tests -v
```

Tests use synthetic arrays, temporary HDF5 files, random network tensors and mocked execution boundaries. They do not run actual imagery adaptation or download data.
