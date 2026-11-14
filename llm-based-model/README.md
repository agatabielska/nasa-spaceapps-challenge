# LLM-Based Model

This folder contains a small event-based wildfire/change-detection pipeline. It combines:

- NISAR L2 GCOV radar backscatter from ASF/Earthdata.
- Sentinel-2 optical imagery from Microsoft's Planetary Computer.
- Optional NASA FIRMS fire hotspots.
- NumPy, Rasterio, PyProj, Matplotlib, and Leaflet-based visualisation.

The main example is the `spain_fire` event.

## Folder contents

### Python programs

- `nisar_before_after.py`
  - Searches ASF for NISAR GCOV scenes.
  - Selects a before/after pair using the same track, frame, direction, and configuration.
  - Reads the requested polarisation over the event bounding box.
  - Converts backscatter to decibels and creates before/after/change images.
  - Writes the georeferenced NISAR difference data used by the other scripts.

- `validate_fire.py`
  - Queries Sentinel-2 L2A scenes from the Planetary Computer STAC API.
  - Builds cloud-masked Sentinel-2 NBR mosaics from B8A and B12.
  - Calculates dNBR and treats pixels above the burn threshold as optical burn predictions.
  - Compares the Sentinel-2 prediction with the NISAR change map.
  - Optionally compares both datasets with FIRMS hotspots.
  - Writes validation metrics and a comparison figure.

- `check_location.py`
  - Downloads Sentinel-2 bands B04, B03, B02, B8A, and B12 for before and after windows.
  - Creates true-colour and SWIR composites.
  - Smooths and overlays the NISAR decrease mask.
  - Optionally plots FIRMS hotspots.
  - Writes a static figure and an interactive Leaflet map.

### Configuration and dependencies

- `events.json`
  - Defines event names, longitude/latitude bounding boxes, event dates, search windows, and preferred polarisations.
  - Includes the `venezuela`, `nepal`, and `spain_fire` examples.

- `pyproject.toml`
  - Defines the project and its Python dependencies.
  - The `validate` dependency group contains Rasterio, `pystac-client`, and `planetary-computer`.
  - The project requires Python 3.10 or newer.

- `uv.lock`
  - Locks the resolved Python dependency versions for reproducible `uv` environments.

### Example event output

`output/spain_fire/` contains generated data for the Spain wildfire example:

- `BEFORE.png`, `AFTER.png`: NISAR before/after backscatter images.
- `DIFF_after_minus_before.png`: NISAR after-minus-before change in dB.
- `CHANGE_overlay.png`: NISAR decrease highlighted in red.
- `diff_db.npy`: numeric NISAR difference array.
- `grid.json`: projection, pixel size, origin, and array shape for `diff_db.npy`.
- `meta.json`: event, scene, polarisation, processing, and summary metadata.
- `VALIDATION.png`: Sentinel-2/NISAR validation figure.
- `validation.json`: validation metrics.
- `SATELLITE_CHECK.png`: Sentinel-2 and NISAR location-check figure.
- `map.html`: interactive map with satellite imagery and overlays.
- downloaded `.h5` files: local NISAR source scenes when full-download mode was used.

Generated files should normally be treated as outputs rather than source code. The `.h5` files can be very large.

## End-to-end pipeline

### 1. Define an event

An event has a bounding box in `[west, south, east, north]` order, an event date, and a search window. For example, `events.json` defines:

```json
{
  "spain_fire": {
    "bbox": [-5.05, 40.3, -4.5, 40.6],
    "date": "2026-07-22",
    "window_days": 45,
    "pol": "HVHV",
    "after_from": "2026-08-10"
  }
}
```

### 2. Search for NISAR scenes

`nisar_before_after.py` sends the bounding box and date range to ASF Search. It filters for NISAR GCOV products and groups scenes by:

1. Configuration.
2. Relative-orbit track.
3. Frame.
4. Acquisition direction.

It chooses the closest usable scene before the event and the closest scene after the event. Scene footprint coverage is preferred when available.

### 3. Authenticate and read NISAR data

For streaming mode, set an Earthdata token:

```powershell
$env:EDL_TOKEN = "your-earthdata-token"
```

The script then reads only the needed area from the remote HDF5 files. Without a token, it uses Earthdata credentials and can download complete `.h5` files.

The selected HDF5 grid is:

```text
/science/LSAR/GCOV/grids/frequencyA
```

The requested polarisation, such as `HVHV`, is cropped to the event bounding box, converted to dB, and optionally block-averaged to reduce image size and speckle.

### 4. Create the NISAR change map

The radar difference is calculated as:

```python
before_db = 10 * log10(before_backscatter)
after_db = 10 * log10(after_backscatter)
diff_db = after_db - before_db
```

By default, a decrease of `-2 dB` or less is highlighted as a possible change. The script saves `diff_db.npy` and `grid.json`, allowing later scripts to use the exact same georeferenced grid.

Run the NISAR stage for the configured Spain event:

```powershell
uv sync
uv run python nisar_before_after.py `
  --events events.json `
  --only spain_fire
```

To search without downloading or processing scenes:

```powershell
uv run python nisar_before_after.py `
  --events events.json `
  --only spain_fire `
  --dry-run
```

### 5. Query Sentinel-2 through the Planetary Computer API

`validate_fire.py` and `check_location.py` open the public Planetary Computer STAC API:

```python
catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)
```

They search the `sentinel-2-l2a` collection using:

- The event bounding box.
- A before or after date interval.
- A maximum cloud-cover filter.

The returned assets are read with Rasterio and reprojected to the NISAR grid. Sentinel-2 L2A reflectance is scaled using the baseline offset used by the scripts:

```python
reflectance = (digital_number - 1000) / 10000
```

Clouds, shadows, snow, saturated pixels, and invalid pixels are removed using the Scene Classification Layer (`SCL`).

### 6. Produce the Sentinel-2 burn prediction

For validation, Sentinel-2 uses the Normalized Burn Ratio:

```python
nbr = (B8A - B12) / (B8A + B12 + 1e-9)
```

The before and after mosaics are combined into dNBR:

```python
dnbr = nbr_before - nbr_after
burn_prediction = dnbr > 0.27
```

The `0.27` threshold is the default moderate-low burn threshold and can be changed with `--dnbr` in `validate_fire.py`.

### 7. Compare NISAR and Sentinel-2

For every pixel valid in both datasets:

- NISAR prediction: `diff_db <= -2.0`.
- Sentinel-2 burn prediction: `dnbr > 0.27`.

`validate_fire.py` calculates:

- True positives, false positives, false negatives, and true negatives.
- Precision, recall, F1, and IoU.
- AUC.
- Spearman correlation between radar change and optical dNBR.

Run validation:

```powershell
uv run --group validate python validate_fire.py `
  --event output/spain_fire
```

Optional FIRMS comparison:

```powershell
uv run --group validate python validate_fire.py `
  --event output/spain_fire `
  --firms firms_viirs.csv
```

### 8. Put the detection on satellite imagery

`check_location.py` uses the same event metadata and NISAR grid, but retrieves additional Sentinel-2 bands:

- `B04`, `B03`, `B02`: true colour.
- `B8A`, `B12`: SWIR burn composite.

It creates:

1. Sentinel-2 true colour before.
2. Sentinel-2 true colour after.
3. Sentinel-2 SWIR after.
4. Sentinel-2 after with the NISAR decrease outline and optional FIRMS points.

It then reprojects the layers to WGS84 and embeds them as base64 PNG layers in `map.html`. The map provides Esri satellite and OpenStreetMap basemaps, layer controls, opacity control, and coordinate readout.

Run the location check:

```powershell
uv run --group validate python check_location.py `
  --event output/spain_fire
```

With FIRMS hotspots:

```powershell
uv run --group validate python check_location.py `
  --event output/spain_fire `
  --firms firms_viirs.csv
```

Open the generated map in a browser:

```powershell
Start-Process output\spain_fire\map.html
```

The map requires internet access for the Leaflet library and basemap tiles.

## Full command sequence

From this folder:

```powershell
uv sync

# Search, download/read, and process NISAR
uv run python nisar_before_after.py `
  --events events.json `
  --only spain_fire

# Compare NISAR with Sentinel-2 dNBR
uv run --group validate python validate_fire.py `
  --event output/spain_fire

# Create georeferenced Sentinel-2/NISAR location outputs
uv run --group validate python check_location.py `
  --event output/spain_fire
```

The stages are independent after the NISAR stage: `validate_fire.py` and `check_location.py` both consume `diff_db.npy`, `grid.json`, and `meta.json` from the event output directory.
