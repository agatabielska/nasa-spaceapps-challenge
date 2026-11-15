# Interpretable SAR before/after displays

Updated 2026-11-15. Primary recommendation: show a temporal color composite and normalized relative-change map, with linear-power change and analytical dB views available as companions. A different display reveals patterns more clearly but does not create new independent measurements or validate a change mask.

## Recommended views

| View | What it helps answer | Interpretation |
|---|---|---|
| Temporal composite | Where did returns strengthen or weaken? | Our assignment is red=post, green/blue=pre. Red indicates increase, cyan decrease, gray similar. These are not disaster classes. |
| Normalized relative change | How large is the proportional change? | `(post-pre)/(post+pre)`, bounded between -1 and 1 for positive power. Colorbar labels use equivalent fold changes. |
| Linear gamma-0 power difference | How much absolute return changed? | Signed `post-pre`, in dimensionless calibrated gamma-0 power. Bright scatterers can dominate; preserve unclipped GeoTIFF values. |
| Per-polarization comparison | Do HH/HV/VH/VV respond differently? | Keep channels separate before fusion; a cross-pol decrease and co-pol increase can coexist. |
| Distribution conditional on a mapped event | Is a localized signal diluted in the whole-scene histogram? | Compare inside/outside independent reference polygons, without declaring outside pixels unchanged. |
| Geographic context | Did the crop cut through the phenomenon? | Show native footprint/valid coverage, regional view and detail box separately. |

For a single polarization, if `R=post/pre`, the normalized difference equals `(R-1)/(R+1)`. Half the original return gives -1/3; double gives +1/3. Four times gives +0.6; one quarter gives -0.6. This is a re-expression of a ratio, not a probability or a calibrated significance score. The current display clips at ±0.6 while exported float rasters retain full values. Very dark signals still make relative changes noise-sensitive; no instrument noise floor has been estimated.

Plain percentage change `100*(post/pre-1)` is familiar but can explode when pre is near zero and treats increases/decreases asymmetrically. It is optional supporting information, not the preferred primary map. A log-ratio/dB difference remains analytically useful. Raw power is not inherently the best-looking display because its dynamic range is highly skewed. The [ASF SAR scale guide](https://hyp3-docs.asf.alaska.edu/hyp3-docs/guides/introduction_to_sar/) describes these tradeoffs. [SAR temporal-composite documentation](https://docs.mcube.terradue.com/services/sar-change/service-specs/) provides a primary service example; its pre-to-red convention is the reverse of ours, so the legend must remain explicit.

## Implemented examples

- [Etna non-dB views](outputs/eda/etna/non_db_changes.png)
- [Corrected Spain non-dB views](outputs/eda/spain_navaluenga_corrected/non_db_changes.png)
- [Spain mapped-burn conditional comparison](outputs/eda/spain_navaluenga_corrected/mapped_burn_comparison.png)
- [Mozambique non-dB views](outputs/eda/mozambique/non_db_changes.png)
- [Mozambique regional/full-frame context](outputs/eda/mozambique_regional/README.md)

`alternative_eda.py` averages 3×3 valid linear-power neighborhoods independently at both dates, then constructs these display products. That covers ~60 m in Etna and ~30 m in the 10 m Mozambique grid; it is a modest visualization sensitivity choice, not a universal physical denoising scale. A future cross-scene filter comparison should specify width in meters. It does not alter existing model inputs/checkpoints. Original no-filter dB figures remain available.

The composite uses square-root power (amplitude) and the same 1st–99th percentile stretch for both timestamps per polarization. Dates are never independently histogram-matched. This is display scaling only; it does not change the numerical scientific outputs. Color changes can also arise from moisture, terrain, registration and speckle. Spatial support, event chronology, source metadata and reference layers remain necessary.
