# Step-by-step pipeline visualizations

Run from this project directory with the existing host environment:

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py --config configs/etna_run.json
```

This performs fresh preparation, training and inference on the configured local images, using NISAR-derived standardization. It creates a new timestamped folder under `outputs/walkthroughs/` and prints the path to `steps/index.html`. Open that file in your browser; no web server is required. It uses existing downloaded inputs and weights, with no download or publication step. Other locations use the corresponding `configs/*_run.json` file.

The input is HH dB, HV dB and their difference; the VV experiment is removed. Reports now additionally show physical high/weak masks before closing, after closing and after component removal; FCM confidence before/after neighborhood filtering; final closing additions and component removals. See [the morphology policy](NISAR_RUN_GUIDE.md#morphology-and-spatially-supported-fcm).

Add `--gunw PATH` for optional pre-RF coherence support. See [the GUNW command and policy](NISAR_RUN_GUIDE.md#optional-gunw-support-before-rf). The report includes binary native/aligned GUNW eligibility, valid-only incoherence, fitted threshold, added physical corridors and results with/without GUNW from the same model/RF. The no-flag workflow is unchanged; phase-quality masks never gate coherence.

You can choose a new output directory and optionally shorten training:

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py --config configs/etna_run.json --output outputs/walkthroughs/etna_inspection --max-updates 100
```

Omit `--max-updates` to retain the configuration's training budget and early stopping. A shorter run changes the trained model. GPU access is required by default; `--device cpu` is available but can be slow. The runner refuses nonempty output directories to preserve existing experiments. It does not resume training.

## What is captured

1. **Physical baseline:** absolute dB changes for each polarization, fused scaled score, global Otsu threshold and binary result.
2. **Preprocessing:** common-grid selected co/cross-pol power before/after, validity, filtered power, dB channels and log polarization ratio, percentile-scaled channels, training support, NISAR z-score channels and value distributions. Both dates use shared per-channel scaling and normalization. The raw-power trace is already cropped and grid-aligned; it is not the complete original HDF5 raster. Configuration and pair metadata disclose reprojection and filter settings.
3. **Training:** first training patch's normalized inputs, initial VGG difference/mixing weight, mixed style target and content-feature summary. Training/validation loss curves show the actual translation objectives, not detection accuracy.
4. **VGG and translation:** one representative inference patch, normalized inputs, raw VGG activation summaries and first four activation channels from each encoder block, translated output, first three channels after score-specific feature saturation, and the translated patch score. Exact patch coordinates are saved in the NPZ. Complete feature tensors and every training iteration are intentionally not dumped because of their size.
5. **Whole-scene inference:** overlap-weight accumulation, input validity, guard exclusion, final supported area, blended translated score and no-translation score.
6. **FCM:** center trajectories, low/middle/high clusters, each fuzzy membership, high/low binary clusters. FCM uses three scalar clusters, fuzzifier 2, a seeded sample capped at 50,000 values, and up to 100 iterations.
7. **Gaussian adaptive binary threshold:** masked Gaussian local mean, threshold `2 × local mean`, raw binary map, small-component removal, and strict FCM/adaptive seed agreement. For the default refined detector, these are explicitly labeled `comparison_strict_*` diagnostic views.
8. **Current refined detector:** per-polarization normalized physical change `(post−pre)/(post+pre)`, fused absolute physical score, high/low local threshold surfaces, binary strong/weak physical support, physical/FCM seed agreement before/after component removal, unchanged/changed/uncertain seeds, weak components connected to changed seeds, RF votes, vote threshold, feature importance and gated mask. The high/low thresholds use a local residual MAD proxy plus configured floors; they are not significance tests.
9. **Final cleanup and comparisons:** mask before area filtering, removed pixels, final mask and existing baseline/no-translation overview figures.

The chosen `pseudo_method` controls the actual result. The strict legacy detector uses the Gaussian/FCM seed rule and its own RF/fallback behavior; the refined method uses physical/FCM membership seeds and physical/vote gates. The report does not silently substitute the comparison detector. If a seed class is absent, the refined method still fails rather than inventing training examples; the partial report retains available diagnostics.

## Files and interpretation

Every pair uses [the same shared policy](configs/pipeline.json). Data-only `configs/*_run.json` files contain no algorithm settings. FCM uses the shared 70% physical / 30% VGG evidence blend; the common final minimum component area is 3600 m². These are global choices, not event-specific settings or validated optimal parameters. Geometry, polarization selection and fitted statistics are derived from the selected images. See [the run guide](NISAR_RUN_GUIDE.md) for automatic sizing and separate acquisition/processing records.

- `steps/index.html`: offline visual report with explanations and saved configuration/statistics.
- `steps/0*.npz`: exact numeric intermediate arrays, retaining original numeric values rather than display clipping.
- `steps/*.png`: maps, distributions and curves; continuous maps use display percentile limits. Paired before/after channel maps share their display limits. Gray indicates unsupported data where a support mask is available.
- `steps/manifest.json`: array names, dimensions, valid numeric counts and ranges.
- `steps/detection_details.json`: detector parameters, seed counts and RF feature names in importance-index order.
- `pipeline.log` and `run.jsonl`: live console output and structured progress/failures.
- Standard scientific rasters, checkpoint and final images remain in the run folder.

Z-score distributions over the full valid area need not have zero mean/unit variance: fitting uses training support only. FCM memberships and RF votes are not calibrated probabilities. Pseudo-labels are not ground truth. This runner reveals algorithm behavior; it does not establish detection accuracy.

Rebuild only the report without running any processing:

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 run_pipeline_steps.py --report-only outputs/walkthroughs/etna_inspection
```

If a run fails, the runner attempts to render whatever traces were saved and returns the pipeline's failure code. Check logs for completion; a partial report does not mean the experiment succeeded. Visualizations consume additional storage and rendering time, especially on large areas.

## Small checks

```bash
/home/marysia/Downloads/sar-change-detection/.venv/bin/python3 -m unittest discover -s tests -v
```

The walkthrough tests use small synthetic arrays, mocked input loading for preprocessing, small RF fits and temporary report folders. They check passive tracing, exact threshold/seed/gate relationships, feature saturation, HTML/image output and refusal to overwrite prior runs. They do not execute real-data training or load pretrained weights.
