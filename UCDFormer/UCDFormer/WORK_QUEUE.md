# Active work queue

## Optional GUNW pre-RF experiment is runnable

Added `--gunw PATH` to single, walkthrough and single-pair batch runners. No-flag settings/data and algorithm behavior are unchanged. The optional loader uses native HH wrapped-grid coherence, validates geometry/temporal overlap, applies the approved full-footprint GCOV/GUNW validity intersection before fitting a robust native incoherence threshold, and aligns evidence using nearest sampling. It never reads phase validity or applies a minimum-coherence rejection. Support can expand only through moderate physical-change, uncertain-label corridors connected to existing seeds; seeds/RF descriptors/VGG remain unchanged. Existing RF vote and morphology gates still apply. Output comparisons reuse the same model/RF and include original final mask, native/aligned binary eligibility and support additions. See `NISAR_RUN_GUIDE.md`. Only synthetic/mocked checks were executed while implementing the flag; no real-data training or inference rerun.

## Current: ratio inputs restored; physical morphology and spatial FCM

Removed the VV experiment flag. Model inputs are HH dB, HV dB and their difference for every supported pair; missing HH/HV is an explicit error. Shared policy v2/morphology (detector v3) uses a 20 m closing radius on physical high/weak masks, then removes components smaller than 1600 m². Changed seeds require measured high-threshold evidence, FCM membership >=0.75, margin >=0.15 and >=30% neighboring confident pixels within 20 m, followed by an 800 m² seed-component minimum. Closed pixels are support, never certain training labels. Weak components connected to changed seeds constrain inference. Final mask closing is restricted to this support and excludes unchanged seeds; final components below 3600 m² are removed. Eight-neighbor connectivity preserves diagonal segments. Closing additions are prohibited near nodata and are recorded separately; they may bypass RF votes and are inferred connections, not verified change. The no-translation comparison receives the same final cleanup. Raw/closed/clean masks and FCM before/after views remain in walkthrough traces and outputs. Synthetic tests verify gaps, speckle, nodata barriers, diagonals and end-to-end seed/support/cleanup relationships. No real-data experiment was run.

## CUDA inference bottleneck removal

Network inference already ran on CUDA, but feature saturation/differences moved every activation chunk to NumPy. Added tensor-device 95th-percentile order statistics, saturation and streamed L2 scoring, sharing post features and pre/post encodings across translated/no-translation results. Encoder passes per tile reduced from six to three; visualization traces reuse those results. Training targets retain their score/mixing map on device. Inference logs actual device/GPU, per-tile times and memory; `inference_performance.json` summarizes the loop. CPU remains used for HDF5/SciPy/FCM/sklearn RF/export/plots. Synthetic RTX 5070 Ti benchmark: 3.040 s reference versus 0.080 s fused CUDA scoring (~38× for scoring only), zero max score difference on the benchmark fixture. No real imagery training/inference was rerun.

## Optional VV channel experiment

Added runtime `--third-channel vv` to the single, walkthrough and batch runners. Default remains the existing log-ratio third channel; VV mode uses measured HH/HV/VV dB with independent per-channel normalization and joint validity. Shared settings and data inputs are unchanged. Metadata-only inspection of downloaded files found VV at both dates only for `nepal_quad`; Etna/Rasuwagadhi and the other current pairs are HH/HV only. Missing VV produces an explicit error, and staged/batch settings checks prevent mode mismatch. Physical baseline/gates still use the first two bands. Only synthetic tests were run; no actual imagery training/inference was performed for this experiment.

## Shared location-independent pipeline (current behavior)

All `configs/*_run.json` files now contain acquisition inputs only. Algorithm settings live in `configs/pipeline.json`, with one policy for every location: physical/VGG fusion 0.7, final minimum area 3600 m² and a 600 m local threshold neighborhood converted using pair spacing. Earlier event-specific configuration snapshots are archived in `old/configs/before_shared_pipeline/`; entries below describe historical experiments rather than current settings. Input fields cannot override processing settings. The batch runner no longer rewrites configs or branches by event name.

Preparation discovers common HH/HV or VV/VH channels, derives normalization and valid coverage, and automatically chooses spatially separated fully measured training/validation crops down to 32 pixels on either axis. Inference sizes follow scene dimensions. Acquisition and processing records are written separately; insufficient support or missing seed classes remain explicit failures. New runs use fresh directories and preserve old outputs. Only synthetic/mocked tests were used for this refactor; no real-data training or inference was executed.

## Rasuwagadhi physical evidence weighting

Added opt-in `physical_fusion_weight` to the refined detector; Rasuwagadhi sets it to 0.7. It blends minmax physical and VGG scores before FCM/membership seed selection and supplies that blend as the final RF descriptor. Default zero preserves Etna's behavior. Physical thresholds, nodata exclusion, RF vote gate, four-neighbor support and area filter are unchanged. This is an unvalidated starting setting, not a claim of improved accuracy or continuity. Batch generation preserves the per-location setting and the user's current bbox. No real-data pipeline run performed.

## Rasuwagadhi focus AOI

Applied bbox `[85.359, 28.2448, 85.3761, 28.2618]` in `configs/nepal_rasuwagadhi_run.json`; the previous bbox is retained as inactive `previous_bbox` with JSON comment metadata. Batch config generation preserves this override. The approximately 1.7 x 1.9 km crop is too small for the current spatial training split (default minimum 448 rows); a larger processing/training extent is still needed for a full run. No change to existing cached pairs, EDA or results. Reader already excludes nonpositive/nonfinite values and product-invalid pixels; it now also explicitly excludes declared `_FillValue`/`missing_value` sentinels, including positive fills. Missing terrain observations remain excluded, not reconstructed. No processing or tests executed for this change.

## Etna component filtering adjustment

Raised Etna's final minimum component area from 1600 to 3600 m² (4 to 9 pixels at 20 m). Four-neighbor connectivity and seed/RF settings are unchanged; other locations retain 1600 m². Area-to-pixel conversion now rounds upward and uses affine pixel area. Saved diagnostics include the effective pixel threshold and removed pixel count; walkthrough traces retain the raw/final/removed masks. No pipeline execution or tests were run for this adjustment, as requested.

## Pipeline walkthrough runner

`run_pipeline_steps.py` prepares/trains/infers in a fresh output directory with optional numeric traces and an offline HTML report, including the current detector and a separately labeled Gaussian adaptive/strict FCM diagnostic comparison. See `PIPELINE_WALKTHROUGH.md`. Only small synthetic tests were executed while implementing this runner; real-data training/inference was explicitly left for the user to run locally.

## Codebase cleanup

Superseded Etna runs, their configurations and one-time diagnostics, original optical experiment scripts/example data, and historical design documents are archived under `old/`. See `old/README.md` and `old/moves.json`. Historical paths below describe their original locations; prepend `old/` for archived artifacts. All EDA, raw NISAR data, pretrained weights, active pipeline code, and latest per-location outputs remain available. The default single-run config and batch template now use `configs/etna_run.json`. Existing location checkpoints predate NISAR mean/std standardization and need fresh runs in new output directories to adopt it.

## Latest normalization change

Replaced fixed ImageNet input mean/std for new runs with pair-specific NISAR statistics, independently for HH dB, HV dB and their difference, fitted after percentile scaling on both dates' training support. Statistics are persisted in pair metadata and checkpoints; inference rejects incompatible checkpoints. Existing results are preserved. A fresh prepare/train/infer run in a new output directory is required to produce results using this change.

Updated 2026-11-15. Original scope: download Etna, implement/run UCDFormer, continue a bounded background shortlist download, and generate per-polarization before/after EDA as files arrive. User subsequently requested Spain correction and an Etna refinement pass.

## 1. Spain verification and replacement EDA — completed first correction

- User reported no convincing fire signal in the initial Spain EDA.
- Retrieved official Copernicus EMS activation EMSR900 metadata, Piedralaves observed-event polygons, and EFFIS season fire polygons. Original town box is a weak proxy for a burn footprint; EFFIS overlap is about 16%, versus 83% for proposed Navaluenga south box `[-4.70,40.29,-4.58,40.38]`.
- Preserved the original report and generated corrected-AOI July 14/26 EDA to isolate coordinate changes from date changes.
- Downloading July 2/August 19 same-track/frame/CRID products with matching near-real-time orbit class; July 26 was during the fire interval. July 14 remains an additional existing pre image with forecast orbit metadata.
- Completed: July 2/August 19 products downloaded; corrected late-post EDA generated under outputs/eda/spain_navaluenga_corrected. Independent CEMS August 5 optical-derived burn polygons overlaid; conditional distributions and old/new box map exported. CEMS mapped-burn fraction is ~10.7% in the original box and ~55% in the corrected box (different mapping detail from the coarse EFFIS ~16%/~83%). All are reference-product estimates, not generic-change truth. Non-dB temporal composites, relative fold-change maps and linear-power change maps added.

## 2. Etna false-positive/refinement investigation — first diagnostics executed; investigation open

User observation: first model mask appears too extensive. Distinguish AOI extent from predicted changed fraction; do not shrink the output to a desired appearance.

First pass executed in refine_etna.py: preserved v1, exported nine threshold/filter/gate comparisons under outputs/etna/refinement. On common supported pixels the RF marks ~12.13%, while strict/adaptive seeds cover ~0.068%; physical 3×3 local-threshold variants cover ~0.54% (k=3) / ~0.21% (k=4), and RF intersected with physical local support covers ~0.24%. These sizes are not an accuracy ranking. A separately labeled conservative candidate is exported for review, not selected as final. Full registration/terrain checks, true edge/noise preservation validation, and any filtered model re-adaptation remain pending.

1. Diagnose registration, scene-wide/polarization-specific shifts, terrain patterns, native speckle and confidence-seed geography.
2. Compare raw vs modest mask-aware linear-power filtering before log transform; preserve unfiltered ablation.
3. Export the existing Gaussian adaptive-only mask, strict FCM/adaptive agreement mask, and final RF mask separately. Existing adaptive threshold only chooses seeds; RF can expand the final map substantially. Quantify that expansion and inspect sparse positives (first run had 160 confident positives).
4. Test a robust local relative threshold, e.g. `score > local_median + k*1.4826*local_MAD`, at a small number of physically specified window sizes. Add a physical absolute dB-change floor where the score is physical dB; do not apply a dB floor to a VGG score with unrelated units. For VGG scores, derive any floor from a declared null/stable comparison or retain it as an uncalibrated score parameter.
5. Guard against near-zero local variability, invalid boundaries and rare/no-change scenes. A relative threshold can overreact in quiet regions and miss spatially extensive real change; it is not automatically superior.
6. Compare physical-band differences, no-translation features and translated features; test capped RF expansion or a score-support gate as explicitly named variants, not silent changes to original UCDFormer semantics.
7. Save sensitivity figures, raw/cleaned masks and limitations. Select conservatively from evidence; without independent labels, do not claim improved accuracy from a smaller mask. Revisit unsupported tile coverage separately.

## 3. Background datasets and EDA — completed

Workers and persistent logs: `outputs/jobs/workers.json`, `outputs/jobs/downloads.log`, `outputs/jobs/eda.log`. Original raw shortlist ~74.51 GB; Spain correction keeps expanded queue below 80 GB. User ceiling is 100 GB including derived data; avoid unbounded additional downloads.

EDA watcher builds reports per completed pair. Check `outputs/eda/README.md` and `outputs/eda/status.json`. Original Etna training/inference completed; see `outputs/etna/README.md` for the selected checkpoint and limitations.

Completion verified: 16 full HDF5 files, 78,165,049,344 bytes (~78.17 GB), no partial files; original queue zero failures plus two successful Spain replacements. EDA has no pending/error entries, including quad-pol.

## Latest: requested Etna rerun and preferred result — completed

User likes outputs/etna/refinement/conservative_candidate/mask.png. Preserved it unchanged: 560 flagged pixels, 0.224 km². outputs/etna/preferred_result.json records visual preference, not validated accuracy. An in-folder README explains its transparent-red display, scientific GeoTIFF and original v1 pseudo-label context.

Separate outputs/etna_v2 run completed with consistent 3×3 masked linear-power preprocessing before adaptation; new physical/feature seed agreement; temporal RF descriptors; connected weak physical support and vote gate. Early stop 600 updates; best update 100; held-out translation objective 2.7843→1.7698 (not accuracy). New seeds: 761 changed, 12,389 unchanged, 222,626 uncertain. Final: 2,437 pixels, 0.9748 km², 1.034% of support. Preferred mask was not replaced.

outputs/etna_v2/result_comparison.png compares original/preferred/rerun results; pseudo_labels_review.png explicitly separates new training seeds from the final mask. Eight automated checks pass. Actual-run checks confirm unchanged seed retention, support/vote-gated uncertain positives, and explicit nodata. Independent accuracy and further registration/terrain evaluation remain scientific follow-ups.

## 4. Mozambique spatial coverage — completed wider views

User clarified the geographic boundary is cut off; no later-date/recession download requested. Added a ~50 km regional comparison and complete ~330×320 km downloaded-frame context under outputs/eda/mozambique_regional, keeping the original small crop. The full context explicitly outlines the original and regional crops and shows valid sampled acquisition coverage. Display decimation is nearest-sample 16× (~160 m), not a quantitative flood-area map. Floods can still extend beyond acquisition coverage. January 17 remains during-flood, not flood recession/end. Non-dB views also added for the original Mozambique crop.

## 5. More informative non-dB views — completed initial examples

Researched ASF scale guidance and SAR temporal-color products. Recommended primary display: temporal red/cyan composite plus bounded normalized difference `(post-pre)/(post+pre)` with fold-change tick labels, alongside linear gamma-0 power difference. A ratio/log-ratio re-expression does not create new independent information; absolute power and spatial/reference context complement it. Raw power has high dynamic range and plain percentage change is unstable near zero. Initial examples: Etna, corrected Spain, original Mozambique. Existing dB diagnostics retained for technical inspection. Three-pixel linear-power averaging is explicitly EDA-only; model inputs/checkpoints unchanged. More examples can be generated with alternative_eda.py.


## Output geometry and all-location model runs (2026-11-15)
- WGS84 previews now preserve native pixel dimensions/aspect with an explicit non-square degree grid and updated affine/bounds. Refreshed legacy previews without altering native masks.
- Inference no longer discards a full 256-square tile for isolated nodata: nearest valid context is used only for network input, invalid outputs plus an 8-pixel heuristic guard remain excluded, feature saturation fits only valid pixels. This is context imputation, not recovered measurements.
- Fully valid 128-square training crops are allowed when terrain masks prevent 256-square training. A 64-pixel spatial moat and training-only scaling are retained.
- `run_all_locations.py` runs seven selected pairs serially, corrected Spain replacing the exploratory town pair. Status: `outputs/runs/status.json`; per-case `console.log` and `run.jsonl`.
- `organize_outputs.py` creates `outputs/results/` and embeds PNG galleries with descriptions through `embed_output_images.py`. Existing Etna preferred result is retained.
