# NISAR acquisition candidates

Updated 2026-11-15. Metadata discovery only; no science raster downloaded or inspected.

Search: 13 events.json markers plus three sourced event locations; approximately 10 km boxes, ±25 days. 168 returned granule records, 38 catalog-compatible candidate pairs across 14/16 locations. Counts include processing variants and overlapping frames, not independent training examples. No result hit the 250-record limit. This is a bounded search, not an exhaustive worldwide inventory.

Full machine-readable IDs, direct HDF5 URLs, bounds, query URLs, versions and footprints checks: [nisar_pair_candidates.json](nisar_pair_candidates.json). Raw responses: catalog/.

## Recommended order

1. Etna: ~3.05 GB Provisional pair. Low data cost and independently documented eruptive activity; inspect lava-field overlap and quality before choosing. July 23–August 16 spans multiple phases, not a single onset.
2. Burgohondo, Spain: ~3.70 GB Provisional pair around a documented July fire. The July 14 pre-image uses forecast orbit metadata (F) while July 26 uses near-real-time (N): check grid/geolocation quality and seek consistent reprocessing if needed. The box is centered on the town, not a verified burn perimeter.
3. Nepal Shyar Khola/Budhi Gandaki: dual HH/HV ~14.09 GB; quad-pol alternative ~16.64 GB. Independent event sources and optical context exist; terrain, snow, layover and timing make this harder.
4. Mozambique: ~8.22 GB Beta pair, partial frames. NASA documents radar flood observations for these dates. Calibration and valid overlap require QA.
5. Hubbard: NASA's November 26/December 8 pair is ~14.52 GB Beta; glacier motion, snow and terrain confound debris changes. Prefer that contextual pair over automatically ranked dates when the studied deposits match the box.

Start with one pair, not all 38. Etna + Burgohondo is ~6.75 GB full products; adding Nepal dual-pol brings this to ~20.84 GB before caches/weights. These are budget proposals, not downloads. Quad-pol is optional and should replace rather than multiply initial experiments.

## Event and coordinate provenance

All bounding boxes use [west, south, east, north] in WGS84. Each is a proposed search/processing region, not a verified event footprint. Extra decimal places identify a map location, not accuracy of a disaster boundary.

- Etna: events.json center [15,37.75], consistent with [INGV's volcano location](https://www.ingv.it/etna) near [14.999,37.748]. [INGV activity account](https://ingvvulcani.com/2026/08/22/etna-la-calda-estate-del-2026/) supports the multi-phase interval. August 7 in events.json is contextual, not a verified single onset.
- Burgohondo: proposed town center [-4.785,40.415], consistent with [mapped settlement coordinates](https://es.wikipedia.org/wiki/Burgohondo). [NASA](https://science.nasa.gov/earth/earth-observatory/destructive-fires-char-western-europe/) documents fire observations near Burgohondo on July 22/23 and July 29. This is not proof the entire box burned.
- Nepal Shyar Khola: proposed map-view center [84.94629,28.45767], drawn from the [Copernicus Browser view](https://browser.dataspace.copernicus.eu/?zoom=13&lat=28.45767&lng=84.94629) linked with the [published image metadata](https://commons.wikimedia.org/wiki/File:2026_Budhi_Gandaki_flood_sat_img_before_after.webp). [EU Copernicus event account](https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-the-day/landslide-triggered-flash-flood-sweeps-through-nepals-himalayan-valleys) independently documents October 11 and visible deposits. The view center is not a surveyed failure origin. Original rough exploratory center is superseded.
- Rasuwagadhi: [85.37767854,28.27741433] is a [GeoNames settlement location](https://www.geonames.org/advanced-search.html?country=NP&q=&startRow=250). [Sentinel Asia activation](https://sentinel-asia.org/EO/2026/article20260826NP.html) and [WHO](https://www.who.int/nepal/emergencies/2026-rasuwa-flash-floods) document August 26. The source failure and downstream damage are spatially distinct; do not label a town-centered box as the source landslide. Earlier [85.30,28.28] exploratory box is superseded.
- Mozambique: [33,-24.6] is the original regional marker. [NASA](https://svs.gsfc.nasa.gov/5661) establishes January 5/17 observations, not an exact local flood polygon.
- Hubbard: [-139.8,60.45] is the original regional marker; [NASA](https://science.nasa.gov/earth/earth-observatory/landslide-and-avalanche-debris-litter-hubbard-glacier/) establishes the event and November 26/December 8 imagery, not a verified debris polygon for this box.
- Other original markers are exploratory. Venezuela's linked source concerns phase/displacement: intensity change is not equivalent to displacement. Do not present placeholder dates as confirmed disasters.

## All searched locations

| Location | Granules | Candidate pairs | First date pair | Full HDF5 GB | Event status |
|---|---:|---:|---|---:|---|
| indonesia | 8 | 2 | 2026-09-29 → 2026-10-11 | 11.43 | illustrative anchor, event unverified |
| brazil | 13 | 5 | 2026-08-27 → 2026-09-08 | 3.93 | illustrative anchor, event unverified |
| pakistan | 11 | 2 | 2026-08-16 → 2026-08-28 | 13.31 | illustrative anchor, event unverified |
| spain | 8 | 2 | 2026-08-16 → 2026-08-28 | 3.66 | illustrative anchor, event unverified |
| etna | 6 | 2 | 2026-07-23 → 2026-08-16 | 3.05 | event source exists; AOI unverified |
| canada | 16 | 4 | 2026-07-11 → 2026-07-23 | 8.84 | illustrative anchor, event unverified |
| venezuela | 18 | 3 | 2026-06-22 → 2026-07-04 | 10.30 | event source exists; AOI unverified |
| greenland | 11 | 0 | none under filters | — | illustrative anchor, event unverified |
| iceland | 9 | 2 | 2026-05-14 → 2026-05-26 | 9.40 | illustrative anchor, event unverified |
| japan | 0 | 0 | none under filters | — | illustrative anchor, event unverified |
| australia | 5 | 1 | 2026-02-05 → 2026-02-17 | 3.75 | illustrative anchor, event unverified |
| mozambique | 3 | 1 | 2026-01-05 → 2026-01-17 | 8.22 | event source exists; AOI unverified |
| hubbard | 20 | 5 | 2025-12-03 → 2025-12-15 | 12.18 | event source exists; AOI unverified |
| nepal_shyar_khola | 17 | 3 | 2026-10-06 → 2026-10-18 | 14.09 | event source exists; AOI unverified |
| nepal_rasuwagadhi | 17 | 5 | 2026-08-19 → 2026-08-31 | 14.29 | event source exists; AOI unverified |
| spain_burgohondo | 6 | 1 | 2026-07-14 → 2026-07-26 | 3.70 | event source exists; AOI unverified |

Greenland: no compatible bracketing pair under the chosen grouping/window. Japan: zero returned GCOV records in this query. Neither proves no usable NISAR data exists elsewhere or at other dates.

## Priority acquisition details

Both footprint polygons contain the four search-box corners for the selected pairs below. This preliminary geometry check does not establish complete interior coverage, correct registration, or valid pixels. Prefer actual HDF5 QA and metadata over filename inference. Same-day post candidates are excluded by default; Mozambique is allowed because the January 17 observation is specifically documented. Deduplicate reprocessed versions before downloading.

### etna

Proposed bbox: `[14.943194, 37.705084, 15.056806, 37.794916]`.

- Track 43, frame 21, ASCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 3.05 GB.
  - Before: [NISAR_L2_PR_GCOV_026_043_A_021_2005_DHDH_A_20260723T040829_20260723T040904_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_026_043_A_021_2005_DHDH_A_20260723T040829_20260723T040904_P05023_N_F_J_001/NISAR_L2_PR_GCOV_026_043_A_021_2005_DHDH_A_20260723T040829_20260723T040904_P05023_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_028_043_A_021_2005_DHDH_A_20260816T040828_20260816T040903_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_043_A_021_2005_DHDH_A_20260816T040828_20260816T040903_P05023_N_F_J_001/NISAR_L2_PR_GCOV_028_043_A_021_2005_DHDH_A_20260816T040828_20260816T040903_P05023_N_F_J_001.h5)
- Track 51, frame 69, DESCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 3.06 GB.
  - Before: [NISAR_L2_PR_GCOV_026_051_D_069_2005_DHDH_A_20260723T175503_20260723T175538_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_026_051_D_069_2005_DHDH_A_20260723T175503_20260723T175538_P05023_N_F_J_001/NISAR_L2_PR_GCOV_026_051_D_069_2005_DHDH_A_20260723T175503_20260723T175538_P05023_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_028_051_D_069_2005_DHDH_A_20260816T175502_20260816T175537_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_051_D_069_2005_DHDH_A_20260816T175502_20260816T175537_P05023_N_F_J_001/NISAR_L2_PR_GCOV_028_051_D_069_2005_DHDH_A_20260816T175502_20260816T175537_P05023_N_F_J_001.h5)

### spain_burgohondo

Proposed bbox: `[-4.843993, 40.370084, -4.726007, 40.459916]`.

- Track 87, frame 22, ASCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 3.70 GB.
  - Before: [NISAR_L2_PR_GCOV_025_087_A_022_2005_DHDH_A_20260714T052401_20260714T052434_P05023_F_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_025_087_A_022_2005_DHDH_A_20260714T052401_20260714T052434_P05023_F_F_J_001/NISAR_L2_PR_GCOV_025_087_A_022_2005_DHDH_A_20260714T052401_20260714T052434_P05023_F_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_026_087_A_022_2005_DHDH_A_20260726T052401_20260726T052433_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_026_087_A_022_2005_DHDH_A_20260726T052401_20260726T052433_P05023_N_F_J_001/NISAR_L2_PR_GCOV_026_087_A_022_2005_DHDH_A_20260726T052401_20260726T052433_P05023_N_F_J_001.h5)

### nepal_shyar_khola

Proposed bbox: `[84.895201, 28.412754, 84.997379, 28.502586]`.

- Track 98, frame 16, ASCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 14.09 GB.
  - Before: [NISAR_L2_PR_GCOV_032_098_A_016_4005_DHDH_A_20261006T233918_20261006T233952_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_032_098_A_016_4005_DHDH_A_20261006T233918_20261006T233952_P05023_N_F_J_001/NISAR_L2_PR_GCOV_032_098_A_016_4005_DHDH_A_20261006T233918_20261006T233952_P05023_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_033_098_A_016_4005_DHDH_A_20261018T233918_20261018T233952_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_033_098_A_016_4005_DHDH_A_20261018T233918_20261018T233952_P05023_N_F_J_001/NISAR_L2_PR_GCOV_033_098_A_016_4005_DHDH_A_20261018T233918_20261018T233952_P05023_N_F_J_001.h5)
- Track 48, frame 74, DESCENDING, HH/HV/VH/VV, NISAR_L2_GCOV_PROVISIONAL_V1, 16.64 GB.
  - Before: [NISAR_L2_PR_GCOV_031_048_D_074_2005_QPDH_A_20260921T125811_20260921T125846_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_031_048_D_074_2005_QPDH_A_20260921T125811_20260921T125846_P05023_N_F_J_001/NISAR_L2_PR_GCOV_031_048_D_074_2005_QPDH_A_20260921T125811_20260921T125846_P05023_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_033_048_D_074_2005_QPDH_A_20261015T125812_20261015T125846_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_033_048_D_074_2005_QPDH_A_20261015T125812_20261015T125846_P05023_N_F_J_001/NISAR_L2_PR_GCOV_033_048_D_074_2005_QPDH_A_20261015T125812_20261015T125846_P05023_N_F_J_001.h5)

### nepal_rasuwagadhi

Proposed bbox: `[85.326677, 28.232499, 85.42868, 28.32233]`.

- Track 98, frame 16, ASCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 14.29 GB.
  - Before: [NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_X05026_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_X05026_N_F_J_001/NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_X05026_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_X05026_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_X05026_N_F_J_001/NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_X05026_N_F_J_001.h5)
- Track 98, frame 16, ASCENDING, HH/HV, NISAR_L2_GCOV_PROVISIONAL_V1, 14.29 GB.
  - Before: [NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_P05023_N_F_J_001/NISAR_L2_PR_GCOV_028_098_A_016_4005_DHDH_A_20260819T233918_20260819T233953_P05023_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_P05023_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_P05023_N_F_J_001/NISAR_L2_PR_GCOV_029_098_A_016_4005_DHDH_A_20260831T233918_20260831T233952_P05023_N_F_J_001.h5)

### mozambique

Proposed bbox: `[32.950601, -24.644916, 33.049399, -24.555084]`.

- Track 114, frame 165, ASCENDING, HH/HV, NISAR_L2_GCOV_BETA_V1, 8.22 GB.
  - Before: [NISAR_L2_PR_GCOV_009_114_A_165_4005_DHDH_A_20260105T034232_20260105T034253_X05010_N_P_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_009_114_A_165_4005_DHDH_A_20260105T034232_20260105T034253_X05010_N_P_J_001/NISAR_L2_PR_GCOV_009_114_A_165_4005_DHDH_A_20260105T034232_20260105T034253_X05010_N_P_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_010_114_A_165_4005_DHDH_A_20260117T034232_20260117T034254_X05010_N_P_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_010_114_A_165_4005_DHDH_A_20260117T034232_20260117T034254_X05010_N_P_J_001/NISAR_L2_PR_GCOV_010_114_A_165_4005_DHDH_A_20260117T034232_20260117T034254_X05010_N_P_J_001.h5)

### hubbard

Proposed bbox: `[-139.891073, 60.405084, -139.708927, 60.494916]`.

- Track 63, frame 32, ASCENDING, HH/HV, NISAR_L2_GCOV_BETA_V1, 14.52 GB.
  - Before: [NISAR_L2_PR_GCOV_006_063_A_032_4005_DHDH_A_20251126T133227_20251126T133303_X05009_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_006_063_A_032_4005_DHDH_A_20251126T133227_20251126T133303_X05009_N_F_J_001/NISAR_L2_PR_GCOV_006_063_A_032_4005_DHDH_A_20251126T133227_20251126T133303_X05009_N_F_J_001.h5)
  - After: [NISAR_L2_PR_GCOV_007_063_A_032_4005_DHDH_A_20251208T133228_20251208T133304_X05009_N_F_J_001](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_007_063_A_032_4005_DHDH_A_20251208T133228_20251208T133304_X05009_N_F_J_001/NISAR_L2_PR_GCOV_007_063_A_032_4005_DHDH_A_20251208T133228_20251208T133304_X05009_N_F_J_001.h5)

## Access and evaluation

Direct HDF5 links require Earthdata authentication. Use the local account only in a backend downloader; never copy credentials into this report or frontend. Prefer one full low-volume pair or supported Harmony layer/AOI extraction; retain masks and provenance. Full HDF5 input is supported in the plan even when the acquisition route provides COG subsets.

Existing reference candidates: Sentinel Asia lists Rasuwa optical-derived maps, damage proxies and automatic ALOS-2 flood-proxy shapefiles. These have not been downloaded/validated and are not interchangeable with generic-change ground truth. User is not required to draw labels. Select UCDFormer checkpoints by held-out translation loss and health diagnostics; this is not detection accuracy.

No event masks, trained model, raster pixel validity or detection results were verified during catalog planning.
