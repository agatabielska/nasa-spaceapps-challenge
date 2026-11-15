"""Render the saved public metadata manifest into a reviewable planning report."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/"nisar_pair_candidates.json").read_text())
events={e["id"]:e for e in d["events"]}
lines=["# NISAR acquisition candidates", "", "Updated 2026-11-15. Metadata discovery only; no science raster downloaded or inspected.", "",
       "Search: 13 events.json markers plus three sourced event locations; approximately 10 km boxes, ±25 days. 168 returned granule records, 38 catalog-compatible candidate pairs across 14/16 locations. Counts include processing variants and overlapping frames, not independent training examples. No result hit the 250-record limit. This is a bounded search, not an exhaustive worldwide inventory.", "",
       "Full machine-readable IDs, direct HDF5 URLs, bounds, query URLs, versions and footprints checks: [nisar_pair_candidates.json](nisar_pair_candidates.json). Raw responses: catalog/.",
       "", "## Recommended order", "",
       "1. Etna: ~3.05 GB Provisional pair. Low data cost and independently documented eruptive activity; inspect lava-field overlap and quality before choosing. July 23–August 16 spans multiple phases, not a single onset.",
       "2. Burgohondo, Spain: ~3.70 GB Provisional pair around a documented July fire. The July 14 pre-image uses forecast orbit metadata (F) while July 26 uses near-real-time (N): check grid/geolocation quality and seek consistent reprocessing if needed. The box is centered on the town, not a verified burn perimeter.",
       "3. Nepal Shyar Khola/Budhi Gandaki: dual HH/HV ~14.09 GB; quad-pol alternative ~16.64 GB. Independent event sources and optical context exist; terrain, snow, layover and timing make this harder.",
       "4. Mozambique: ~8.22 GB Beta pair, partial frames. NASA documents radar flood observations for these dates. Calibration and valid overlap require QA.",
       "5. Hubbard: NASA's November 26/December 8 pair is ~14.52 GB Beta; glacier motion, snow and terrain confound debris changes. Prefer that contextual pair over automatically ranked dates when the studied deposits match the box.",
       "", "Start with one pair, not all 38. Etna + Burgohondo is ~6.75 GB full products; adding Nepal dual-pol brings this to ~20.84 GB before caches/weights. These are budget proposals, not downloads. Quad-pol is optional and should replace rather than multiply initial experiments.",
       "", "## Event and coordinate provenance", "",
       "All bounding boxes use [west, south, east, north] in WGS84. Each is a proposed search/processing region, not a verified event footprint. Extra decimal places identify a map location, not accuracy of a disaster boundary.",
       "",
       "- Etna: events.json center [15,37.75], consistent with [INGV's volcano location](https://www.ingv.it/etna) near [14.999,37.748]. [INGV activity account](https://ingvvulcani.com/2026/08/22/etna-la-calda-estate-del-2026/) supports the multi-phase interval. August 7 in events.json is contextual, not a verified single onset.",
       "- Burgohondo: proposed town center [-4.785,40.415], consistent with [mapped settlement coordinates](https://es.wikipedia.org/wiki/Burgohondo). [NASA](https://science.nasa.gov/earth/earth-observatory/destructive-fires-char-western-europe/) documents fire observations near Burgohondo on July 22/23 and July 29. This is not proof the entire box burned.",
       "- Nepal Shyar Khola: proposed map-view center [84.94629,28.45767], drawn from the [Copernicus Browser view](https://browser.dataspace.copernicus.eu/?zoom=13&lat=28.45767&lng=84.94629) linked with the [published image metadata](https://commons.wikimedia.org/wiki/File:2026_Budhi_Gandaki_flood_sat_img_before_after.webp). [EU Copernicus event account](https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-the-day/landslide-triggered-flash-flood-sweeps-through-nepals-himalayan-valleys) independently documents October 11 and visible deposits. The view center is not a surveyed failure origin. Original rough exploratory center is superseded.",
       "- Rasuwagadhi: [85.37767854,28.27741433] is a [GeoNames settlement location](https://www.geonames.org/advanced-search.html?country=NP&q=&startRow=250). [Sentinel Asia activation](https://sentinel-asia.org/EO/2026/article20260826NP.html) and [WHO](https://www.who.int/nepal/emergencies/2026-rasuwa-flash-floods) document August 26. The source failure and downstream damage are spatially distinct; do not label a town-centered box as the source landslide. Earlier [85.30,28.28] exploratory box is superseded.",
       "- Mozambique: [33,-24.6] is the original regional marker. [NASA](https://svs.gsfc.nasa.gov/5661) establishes January 5/17 observations, not an exact local flood polygon.",
       "- Hubbard: [-139.8,60.45] is the original regional marker; [NASA](https://science.nasa.gov/earth/earth-observatory/landslide-and-avalanche-debris-litter-hubbard-glacier/) establishes the event and November 26/December 8 imagery, not a verified debris polygon for this box.",
       "- Other original markers are exploratory. Venezuela's linked source concerns phase/displacement: intensity change is not equivalent to displacement. Do not present placeholder dates as confirmed disasters.",
       "", "## All searched locations", "",
       "| Location | Granules | Candidate pairs | First date pair | Full HDF5 GB | Event status |",
       "|---|---:|---:|---|---:|---|"]
for e in d["events"]:
    p=(e.get("pairs") or [None])[0]
    lines.append(f'| {e["id"]} | {e.get("granule_count",0)} | {e.get("pair_count",0)} | '+
                 (f'{p["before_time"][:10]} → {p["after_time"][:10]} | {p["full_h5_bytes"]/1e9:.2f}' if p else 'none under filters | —')+
                 (' | event source exists; AOI unverified |' if e.get("event_verified") else ' | illustrative anchor, event unverified |'))
lines += ["", "Greenland: no compatible bracketing pair under the chosen grouping/window. Japan: zero returned GCOV records in this query. Neither proves no usable NISAR data exists elsewhere or at other dates.",
          "", "## Priority acquisition details", "",
          "Both footprint polygons contain the four search-box corners for the selected pairs below. This preliminary geometry check does not establish complete interior coverage, correct registration, or valid pixels. Prefer actual HDF5 QA and metadata over filename inference. Same-day post candidates are excluded by default; Mozambique is allowed because the January 17 observation is specifically documented. Deduplicate reprocessed versions before downloading."]
for key in ["etna","spain_burgohondo","nepal_shyar_khola","nepal_rasuwagadhi","mozambique","hubbard"]:
    e=events[key]
    pairs=e["pairs"][:2]
    if key=="hubbard":
        pairs=[p for p in e["pairs"] if p["before_time"].startswith("2025-11-26") and p["after_time"].startswith("2025-12-08")][:1]
    lines += ["",f'### {key}',"",f'Proposed bbox: `{[round(v,6) for v in e["bbox_wgs84"]]}`.',""]
    for p in pairs:
        lines += [f'- Track {p["track"]}, frame {p["frame"]}, {p["direction"]}, {"/".join(p["polarizations"])}, {p["collection"]}, {p["full_h5_bytes"]/1e9:.2f} GB.',
                  f'  - Before: [{p["before"]}]({p["before_url"]})',
                  f'  - After: [{p["after"]}]({p["after_url"]})']
lines += ["", "## Access and evaluation", "",
          "Direct HDF5 links require Earthdata authentication. Use the local account only in a backend downloader; never copy credentials into this report or frontend. Prefer one full low-volume pair or supported Harmony layer/AOI extraction; retain masks and provenance. Full HDF5 input is supported in the plan even when the acquisition route provides COG subsets.",
          "", "Existing reference candidates: Sentinel Asia lists Rasuwa optical-derived maps, damage proxies and automatic ALOS-2 flood-proxy shapefiles. These have not been downloaded/validated and are not interchangeable with generic-change ground truth. User is not required to draw labels. Select UCDFormer checkpoints by held-out translation loss and health diagnostics; this is not detection accuracy.",
          "", "No event masks, trained model, raster pixel validity or detection results were verified during catalog planning."]
(ROOT/"NISAR_DATA_CANDIDATES.md").write_text("\n".join(lines)+"\n")
print("Wrote candidate report from",len(events),"locations")
