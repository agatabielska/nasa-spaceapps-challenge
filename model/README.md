# Change-detection pipeline

The numerical part of [EarthSignal](../README.md), our NASA Space Apps Challenge 2026 entry. It takes NISAR radar acquisitions of one place from before and after an event and produces change masks, pictures, numbers and interactive maps. The web app in [`apps/earthsignal`](../apps/earthsignal/README.md) shows these results.

Everything here is a standard SAR technique. Nothing is trained, so every result can be traced back to a formula and a threshold.

The masks are detections by our methods, not validated damage maps.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10 or newer.

```sh
cd model
uv sync
```

To download data you need a free NASA Earthdata token (urs.earthdata.nasa.gov, profile, Generate Token). Put it in `~/.edl_token` or in the `EDL_TOKEN` environment variable.

Run one event from start to finish:

```sh
uv run python fetch_case.py --only nepal_flood      # once, needs the token
uv run python analyze_case.py --only nepal_flood    # offline, a few seconds
uv run python make_map.py --only nepal_flood        # output/nepal_flood/map.html
uv run python make_map3d.py --only nepal_flood      # output/nepal_flood/map3d.html
```

Results that are already computed are in `output/<case>/`. You can open the HTML pages there without running anything; they need an internet connection for the basemap and terrain.

## How it works

1. **Describe the case.** `cases.json` holds one entry per event: its type, date, bounding box and the names of the NISAR granules to use.
2. **Fetch.** A NISAR granule is 1.5 to 8 GB. We open it over HTTPS and read only the chunks inside the bounding box, usually tens of megabytes. The window is cached in `data/<case>/`, so later runs are offline.
3. **Analyse.** The cached windows become change masks and statistics. Which methods run depends on the event type and on the data the case has.
4. **Present.** The masks are turned into a 2D map, a 3D terrain view with a guided tour, or a time slider.
5. **Check.** Where independent data exists, the result is compared with it.

## Methods

The building blocks are in `change_methods.py`.

| Method | Input | What it measures |
|---|---|---|
| Backscatter | GCOV pair | How much brighter or darker the ground became. The log-ratio of HH and HV between the two dates is expressed as a robust z-score, in units of the scene's own noise, so one threshold works for any scene. |
| Coherence loss | GUNW pair and a quiet reference pair | Where the surface changed so much that the two radar passes no longer match. The event pair is compared with a quiet pair of the same track. |
| Displacement | GUNW pair | How many centimetres the ground moved along the radar line of sight, from the unwrapped phase with the ionosphere screen removed. |

Which of them are used for each event type:

| Type | What we look for |
|---|---|
| Flood | Backscatter change in both directions (water and mud darken, debris and wet soil brighten), plus coherence loss |
| Fire | Backscatter decrease, with HV weighted higher, because losing the canopy removes volume scattering |
| Volcano | Backscatter in both directions, coherence loss (new lava destroys it) and displacement |
| Earthquake | Displacement and coherence loss; backscatter usually shows little |
| Subsidence | A time series of displacement, described below |

### Subsidence time series

Slow sinking above mines is measured from a chain of 12- and 24-day interferograms (`subsidence_series.py`):

- Each pair gives the ground motion in that interval. A moving average of about 5 km is subtracted, which removes atmosphere and orbit errors and keeps mining bowls, which are 0.5 to 2 km wide. Wide regional motion is therefore not measured.
- The intervals are summed into a cumulative subsidence map. Negative values mean sinking.
- A sinking area ("bowl") is accepted only if it sinks in most intervals and a second satellite track, looking from the opposite side, sees sinking in the same place.
- Each bowl gets a curve in time and a simple forecast.

`subsidence_detail.py` repeats the analysis at 20 m instead of 80 m for one neighbourhood. The product ships unwrapped phase only at 80 m, so the 20 m wrapped phase is unwrapped with the 80 m layer as a guide. `focus_area.py` cuts that neighbourhood out of the regional result.

## Cases

Defined in `cases.json`.

| Case | Event | Data |
|---|---|---|
| `nepal_flood` | Rasuwa glacier-collapse flood, Nepal, 26 August 2026 | GCOV pair, GUNW pair and reference pair |
| `etna` | Etna eruption, August 2026 | GCOV pair, GUNW pair and reference pair |
| `spain_fire_v2` | Ávila wildfire near Burgohondo, Spain, 22 July 2026 | GCOV pair |
| `silesia` | Mining subsidence, Upper Silesia, Poland, 18 June to 16 October 2026 | GUNW series on two tracks |
| `krzyzowice` | Krzyżowice, Pniówek and Zofiówka at 20 m detail | GUNW series on two tracks |

## Results

Numbers from the `stats.json` files in `output/`.

| Case | Result |
|---|---|
| `nepal_flood` | Backscatter change over 10.3 km², coherence loss over 15.9 km², 6.0 km² where both agree |
| `etna` | Backscatter change over 3.7 km², coherence loss over 6.2 km², line-of-sight motion up to about 13 cm |
| `spain_fire_v2` | HV backscatter decrease over 108.5 km² |
| `silesia` | 25 of 26 candidate bowls confirmed, 11.1 km² in total, deepest about 71 cm in 120 days |
| `krzyzowice` | 7 confirmed bowls, 3.8 km² |

## Validation and limits

- **Wildfire against optical data.** `validate_case.py` scores the fire mask against a Sentinel-2 burn map (dNBR) and compares method variants. The best variant (HV, 15 by 15 filter) reaches an IoU of about 0.30, with precision 0.59 and recall 0.37. The fire mask is a rough indication, not a burn-area product.
- **Two methods on one event.** For Nepal, backscatter and coherence overlap well (IoU 0.30). For Etna they barely overlap (IoU 0.03): they react to different surfaces, so the 3D view shows "both agree" and "one method only" separately.
- **Subsidence against a second track.** One of 26 candidates was rejected because the second track did not see it.
- **Subsidence against mining maps.** `gis_check.py` compares the bowls with official mining-area polygons from the Polish Geological Institute. All 25 confirmed bowls lie inside coal mining areas, which cover 23% of the region; about 6 would be expected by chance. The polygons are licence boundaries, not the tunnels.
- **Forecast.** In a backtest that hid the last 36 days, the median error of the forecast was 28%. Treat it as a trend, not a prediction.
- **Noise.** The subsidence noise level is about 1.1 cm; a bowl must sink more than 5.4 cm to be considered.
- **Optical comparison.** `compare_optical.py` puts a Sentinel-2 scene on the grid of a NISAR window, so both pictures show exactly the same area.

## Scripts

| Script | Purpose |
|---|---|
| `nisar_io.py` | Reads small windows of GCOV and GUNW granules from ASF without a full download |
| `fetch_case.py` | Downloads the windows listed in `cases.json` into `data/<case>/` |
| `fetch_series.py` | Downloads a chain of GUNW pairs for a time-series case; `--check` for the second track, `--wrapped` for the 20 m layers |
| `change_methods.py` | Speckle filter, log-ratio, robust z-score, coherence loss, displacement, mask clean-up |
| `analyze_case.py` | Masks, pictures and `stats.json` for one event |
| `subsidence_series.py` | Regional subsidence map, bowls and their curves |
| `subsidence_detail.py` | The same at 20 m for one neighbourhood |
| `focus_area.py` | Cuts one neighbourhood out of a regional subsidence result |
| `gis_check.py` | Compares bowls with official mining-area polygons |
| `validate_case.py` | Scores the fire mask against Sentinel-2 and compares method variants |
| `compare_optical.py` | Sentinel-2 and NISAR picture pairs on the same grid |
| `make_map.py` | Interactive 2D map with switchable layers |
| `make_map3d.py` | 3D terrain view with a guided tour; `--lang en` for the English version |
| `make_timeline.py` | Time-slider page for subsidence |

The first version of the wildfire analysis is kept as well: `nisar_before_after.py` (searches ASF for a pair from a bounding box and a date in `events.json`), `validate_fire.py` and `check_location.py`. Its results are in `output/spain_fire/`. New work should use `cases.json` and the scripts above.

Scripts that use Sentinel-2 need the extra dependency group: `uv run --group validate python validate_case.py --only spain_fire_v2`.

### Full subsidence run

```sh
uv run python fetch_series.py --only silesia
uv run python fetch_series.py --only silesia --check
uv run python subsidence_series.py --only silesia
uv run python gis_check.py --only silesia
uv run python make_timeline.py --only silesia

uv run python fetch_series.py --only krzyzowice --wrapped
uv run python subsidence_detail.py --only krzyzowice
uv run python focus_area.py --only krzyzowice --source silesia
uv run python make_timeline.py --only krzyzowice
```

## Outputs

Each case writes to `output/<case>/`.

| File | Contents |
|---|---|
| `BEFORE.jpg`, `AFTER.jpg` | Radar composites of the two dates; not natural-colour photographs |
| `CHANGE_overlay.jpg`, `SUMMARY.jpg` | The change mask on the radar image, and an overview figure |
| `mask_*.png`, `bounds.json` | Transparent map layers and their corner coordinates |
| `stats.json` | Areas, thresholds, noise levels and the granules used |
| `map.html`, `map3d.html`, `map3d_en.html` | Interactive 2D map and 3D tours |
| `timeline.html` | Time slider (subsidence cases) |
| `gis_check.json`, `validation_methods.json` | Results of the independent checks |

Some figures of the subsidence cases have Polish file names: `MAPA_osiadania.jpg` (subsidence map), `MAPA_obszary_gornicze.jpg` (mining areas), `WYKRES_niecki.jpg` (bowl curves), `DETAL_20m.jpg` and `ODSTEPY_20m.jpg` (20 m detail and intervals).

Downloaded windows and large numeric layers go to `data/<case>/`, which is not tracked in git.

## Adding a case

1. Find the granules for your area in [ASF Vertex](https://search.asf.alaska.edu/): a GCOV pair around the event, and for coherence and displacement a GUNW pair across the event plus a quiet reference pair of the same track and frame.
2. Add an entry to `cases.json` with `kind`, `title`, `event_date`, `bbox` (west, south, east, north) and the granule names (`gcov_before`, `gcov_after`, `gunw`, `gunw_ref`).
3. Run `fetch_case.py`, `analyze_case.py` and the map scripts with `--only <your case>`.
4. Optionally add a `tour` list to the entry to get a guided fly-through in the 3D view.

## Data and credits

- NISAR L2 GCOV and GUNW products from NASA and ISRO, accessed through the Alaska Satellite Facility.
- Sentinel-2 imagery (Copernicus) through Microsoft Planetary Computer.
- Mining-area polygons from the MIDAS database of the Polish Geological Institute (PIG-PIB).
- Basemap and terrain in the map pages: Esri World Imagery and AWS Terrain Tiles.
