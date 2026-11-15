# mozambique: before/after NISAR EDA

Before: **2026-01-05 03:42:32 UTC**. After: **2026-01-17 03:42:32 UTC**.

Event context: [NASA-documented pre/during observation dates; flood onset not fixed here](https://svs.gsfc.nasa.gov/5661).

NASA compares January 5 and January 17. Flooding developed over a longer rainfall interval: January 5 is the comparison image, not proven entirely pre-flood. January 17 is a during-flood acquisition; Beta calibration caveats apply.

Proposed bbox `[west,south,east,north]`: `[32.950600775417264, -24.644915558749553, 33.049399224582736, -24.55508444125045]`. Common valid pixels: 100.00%. Frequency A; EPSG:32736.

These are measured polarization-intensity comparisons, not RGB photographs or validated event masks. Each polarization uses exactly the same dB display limits at both dates. Red signed differences mean stronger post-event returns; blue means weaker. Both signs can represent change.

![Acquisition timeline](timeline.png)

![Per-polarization comparisons](polarization_changes.png)

![Distribution comparisons](distributions.png)

![Sensitivity to small speckle filter](speckle_sensitivity.png)

The filtered figure averages 3×3 linear-power neighborhoods before taking logarithms; it is an EDA sensitivity check, not a hidden change to model inputs.

Statistics and chronology checks: [eda.json](eda.json). No accuracy metric or calibrated change probability is inferred from these figures.

## Non-dB companion views

![Temporal composite, normalized relative change and linear-power difference](non_db_changes.png)

These use a 3×3 mean of linear power before comparison; model inputs and prior results are unchanged. Relative-map ticks show fold change: ½× means half the pre-image return; 2× means twice. The score is bounded, not a probability. Very dark pixels remain susceptible to relative-change noise. Linear-change GeoTIFFs retain the full unclipped values. Red/cyan are explicitly assigned and must not be interpreted as fire/flood labels.

[Numerical display metadata](non_db_metadata.json). Method rationale: [ASF SAR scale guide](https://hyp3-docs.asf.alaska.edu/hyp3-docs/guides/introduction_to_sar/) and [ESA-supported SAR temporal-composite service](https://docs.mcube.terradue.com/services/sar-change/service-specs/). Our red/cyan assignment is post/pre, and is the reverse of services that assign pre-image to red.
