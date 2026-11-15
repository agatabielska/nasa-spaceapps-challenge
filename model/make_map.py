"""
make_map.py -- interactive Leaflet map of one analysed case (open output/<case>/map.html in a browser).

  uv run python analyze_case.py --only nepal_flood
  uv run python make_map.py --only nepal_flood

Layers (switchable, with an opacity slider): radar before / after, HH and HV change, coherence loss,
ground displacement and the change masks, on top of an Esri satellite or OpenStreetMap basemap.
Every layer is resampled from the UTM grid of the product to a lon/lat grid so it sits correctly on the map.
The PNGs are written to output/<case>/map/ and referenced by relative path (needs internet for the basemap).
"""
import argparse, json
from pathlib import Path
import numpy as np
import nisar_io as nio, change_methods as cm

HERE = Path(__file__).parent
MASK_COL = {"mask_high_confidence": ("Change: BOTH methods (high confidence)", (0.85, 0.10, 0.75)),
            "mask_backscatter": ("Change: backscatter method", (1.0, 0.55, 0.0)),
            "mask_coherence": ("Change: coherence method", (0.0, 0.75, 1.0))}


def lonlat_index(x, y, epsg, max_px=1200):
    """Index arrays that resample a north-up UTM grid (x, y) onto a regular lon/lat grid."""
    from pyproj import Transformer
    inv = Transformer.from_crs(epsg, 4326, always_xy=True); fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    lon, lat = inv.transform([x[0], x[-1], x[-1], x[0]], [y[0], y[0], y[-1], y[-1]])
    w, s, e, n = min(lon), min(lat), max(lon), max(lat)
    k = max(1.0, max(len(x), len(y)) / max_px); W, H = int(len(x) / k), int(len(y) / k)
    lo, la = np.meshgrid(np.linspace(w, e, W), np.linspace(n, s, H))
    X, Y = fwd.transform(lo, la)
    c = np.rint((X - x[0]) / (x[1] - x[0])).astype(int); r = np.rint((Y - y[0]) / (y[1] - y[0])).astype(int)
    ok = (c >= 0) & (c < len(x)) & (r >= 0) & (r < len(y))
    return np.clip(r, 0, len(y) - 1), np.clip(c, 0, len(x) - 1), ok, [[s, w], [n, e]]


def build(name, case, data, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    folder, dst = data / name, out / name / "map"
    if not (folder / "layers.npz").exists(): print(f"[{name}] run analyze_case.py first"); return
    dst.mkdir(parents=True, exist_ok=True)
    z = np.load(folder / "layers.npz"); x, y = z["x"], z["y"]
    r, c, ok, bounds = lonlat_index(x, y, int(z["epsg"]))
    layers, default = [], []

    def add(label, rgba, on=False):
        f = f"{len(layers):02d}.png"; rgba = rgba.copy(); rgba[~ok, 3] = 0
        plt.imsave(dst / f, rgba); layers.append([label, f"map/{f}"])
        if on: default.append(label)

    def scalar(a, cmap, vmin, vmax):
        a = cm.resample_to(a, (len(y), len(x)))[r, c]
        rgba = matplotlib.colormaps[cmap](np.clip((a - vmin) / (vmax - vmin), 0, 1)); rgba[~np.isfinite(a), 3] = 0
        return rgba

    for key, label in (("gcov_before", "Radar BEFORE (HH)"), ("gcov_after", "Radar AFTER (HH)")):
        if (folder / f"{key}.npz").exists():
            d = cm.to_db(cm.nanfilter(nio.cached(folder / f"{key}.npz", None)["HHHH"], 3))
            add(label, scalar(d, "gray", *np.nanpercentile(d, [2, 98])), on=key.endswith("after"))
    for key, label, cmap, lim in (("diff_hh_db", "HH change, dB (blue = darker, red = brighter)", "RdBu_r", (-5, 5)),
                                  ("diff_hv_db", "HV change, dB (blue = darker, red = brighter)", "RdBu_r", (-5, 5)),
                                  ("coherence_loss", "Coherence loss (bright = signal destroyed)", "magma", (0, 0.6)),
                                  ("displacement_cm", "Ground displacement, cm in line of sight", "RdBu_r", None)):
        if key in z.files:
            a = z[key]
            if lim is None:
                v = max(2.0, float(np.nanpercentile(np.abs(a), 99))); lim = (-v, v); label += f" (colour scale +/-{v:.0f} cm)"
            add(label, scalar(a, cmap, *lim))
    for key, (label, col) in MASK_COL.items():
        if key in z.files:
            m = z[key].astype(bool)[r, c]; rgba = np.zeros(m.shape + (4,)); rgba[m] = (*col, 1.0)
            add(label, rgba, on=True)
    b = case["bbox"]
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{case.get('title', name)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#map{{height:100%;margin:0}}.ctl{{position:absolute;z-index:1000;bottom:24px;left:12px;background:#fff;padding:6px 10px;border-radius:6px;font:13px sans-serif;max-width:340px}}</style></head>
<body><div id="map"></div><div class="ctl"><b>{case.get('title', name)}</b><br>event {case.get('event_date')}<br>
Overlay opacity <input id="op" type="range" min="0" max="1" step="0.05" value="0.8"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const B={json.dumps(bounds)}, BBOX={json.dumps(b)}, LAYERS={json.dumps(layers)}, DEFAULT={json.dumps(default)};
const sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxZoom:18,attribution:'Tiles &copy; Esri'}});
const osm=L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}});
const map=L.map('map',{{layers:[sat]}}).fitBounds(B);
const over={{}}; LAYERS.forEach(([k,src],i)=>{{over[k]=L.imageOverlay(src,B,{{opacity:0.8,zIndex:10+i}}); if(DEFAULT.includes(k)) over[k].addTo(map);}});
L.control.layers({{'Esri satellite (basemap)':sat,'OpenStreetMap (names/roads)':osm}},over,{{collapsed:false}}).addTo(map);
L.rectangle([[BBOX[1],BBOX[0]],[BBOX[3],BBOX[2]]],{{color:'#ffff00',weight:1,fill:false}}).addTo(map);
document.getElementById('op').oninput=e=>Object.values(over).forEach(l=>l.setOpacity(+e.target.value));
map.on('click',e=>L.popup().setLatLng(e.latlng).setContent(e.latlng.lat.toFixed(5)+', '+e.latlng.lng.toFixed(5)).openOn(map));
</script></body></html>"""
    (out / name / "map.html").write_text(html)
    size = sum(f.stat().st_size for f in dst.iterdir()) / 1e6
    print(f"[{name}] {out / name / 'map.html'}  ({len(layers)} layers, {size:.1f} MB of PNG)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output"))
    A = p.parse_args()
    for n, c in json.loads(Path(A.cases).read_text()).items():
        if A.only and n != A.only: continue
        build(n, c, Path(A.data), Path(A.out))
