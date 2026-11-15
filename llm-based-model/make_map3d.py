"""
make_map3d.py -- 3D terrain view of one analysed case (open output/<case>/map3d.html in a browser).

  uv run python analyze_case.py --only nepal_flood
  uv run python make_map3d.py --only nepal_flood

The mountains come from public elevation tiles (AWS Terrain Tiles), the basemap from Esri World Imagery; both are
streamed, so nothing heavy is stored. Our own layers (radar before / after, the change masks and the area where
neither method can see) are resampled to Web Mercator and embedded in the HTML as WebP, so the page is ONE file that
works when double-clicked (needs internet for terrain, basemap and MapLibre). In the browser they are cut into
ordinary map tiles on the fly: MapLibre drapes tiled rasters on terrain reliably, single "image" sources it does not.
What is drawn depends on what the case has: two radar methods -> "both agree" / "one method only"; an independent
optical reference (data/<case>/dnbr.npy from validate_case.py) -> hit / radar only / optics only; volcano -> also InSAR motion.
An optional "tour" list in cases.json ([{lon, lat, text, zoom?, pitch?, bearing?, hold?, name?, on?}]) becomes a guided
fly-through; "on" lists the overlay keys visible at that stop, {key} in a text is replaced by the measured number.
"""
import argparse, base64, io, json
from pathlib import Path
import numpy as np
import nisar_io as nio, change_methods as cm

HERE = Path(__file__).parent


def webp(rgba, quality=None):
    from PIL import Image
    buf = io.BytesIO(); im = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype("uint8"), "RGBA")
    im.save(buf, "WEBP", **({"lossless": True} if quality is None else {"quality": quality}))
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def mercator_index(x, y, epsg, max_px):
    """Index arrays that resample a north-up UTM grid onto a grid regular in Web Mercator (so it can be cut into map tiles)."""
    from pyproj import Transformer
    inv = Transformer.from_crs(epsg, 4326, always_xy=True); fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    lon, lat = inv.transform([x[0], x[-1], x[-1], x[0]], [y[0], y[0], y[-1], y[-1]])
    w, s, e, n = min(lon), min(lat), max(lon), max(lat)
    merc = lambda la: np.log(np.tan(np.pi / 4 + np.radians(la) / 2))
    k = max(1.0, max(len(x), len(y)) / max_px); W, H = int(len(x) / k), int(len(y) / k)
    lo, my = np.meshgrid(np.linspace(w, e, W), np.linspace(merc(n), merc(s), H))
    X, Y = fwd.transform(lo, np.degrees(2 * np.arctan(np.exp(my)) - np.pi / 2))
    c = np.rint((X - x[0]) / (x[1] - x[0])).astype(int); r = np.rint((Y - y[0]) / (y[1] - y[0])).astype(int)
    ok = (c >= 0) & (c < len(x)) & (r >= 0) & (r < len(y))
    return np.clip(r, 0, len(y) - 1), np.clip(c, 0, len(x) - 1), ok, [w, s, e, n]


def build(name, case, data, out):
    import matplotlib
    folder = data / name
    if not (folder / "layers.npz").exists(): print(f"[{name}] run analyze_case.py first"); return
    z = np.load(folder / "layers.npz"); x, y = z["x"], z["y"]; epsg = int(z["epsg"]); shape = (len(y), len(x))
    full = mercator_index(x, y, epsg, max(shape)); small = mercator_index(x, y, epsg, 1400)
    px_km2 = (float(x[1] - x[0]) / 1000) ** 2; km2 = lambda m: round(float(m.sum() * px_km2), 1)
    layers, legend, stats = {}, [], {}

    def flat(mask, idx, col):
        r, c, ok, _ = idx; m = mask[r, c] & ok; rgba = np.zeros(m.shape + (4,)); rgba[m] = col; return rgba

    def item(key, mask, col, label, note, on=True, opacity=1.0, idx=full):
        """One switchable overlay + its legend row (drawn in the order the items are added, last on top)."""
        layers[key] = webp(flat(mask, idx, (*col, 1.0)))
        legend.append({"key": key, "color": "#%02x%02x%02x" % tuple(int(v * 255) for v in col), "label": label, "note": note, "on": on, "opacity": opacity})

    masks = [z[k].astype(bool) for k in ("mask_backscatter", "mask_coherence") if k in z.files]
    change = np.any(masks, axis=0) if masks else np.zeros(shape, bool)
    seen = np.zeros(shape, bool)
    for k in ("score_backscatter", "coherence_loss"):
        if k in z.files: seen |= np.isfinite(cm.resample_to(z[k], shape))
    stats.update(any_km2=km2(change), blind_pct=round(float((~seen).mean() * 100)))
    if stats["blind_pct"] >= 1:   # where NEITHER method has a usable signal (layover, radar shadow, water): shown, not left as "no damage"
        item("blind", ~seen, (0.25, 0.55, 1.0), "Radar tu nie widzi", f"strome zbocza i cień radarowy · {stats['blind_pct']}% obszaru. Brak koloru tutaj nie oznacza braku zniszczeń.",
             on=False, opacity=0.6, idx=small)
    if (folder / "dnbr.npy").exists():
        # an independent optical reference exists (Sentinel-2 burn severity, same threshold as validate_case.py): show the comparison itself
        d = cm.match(np.load(folder / "dnbr.npy"), shape); ok = np.isfinite(d); ref = ok & (d > 0.27); m = change & ok; hit = m & ref
        stats.update(ref_km2=km2(ref), hit_km2=km2(hit), radar_only_km2=km2(m & ~ref), ref_only_km2=km2(ref & ~m),
                     recall_pct=round(float(hit.sum() / max(ref.sum(), 1) * 100)), precision_pct=round(float(hit.sum() / max(m.sum(), 1) * 100)))
        item("ref_only", ref & ~m, (0.93, 0.95, 1.0), "Tylko optyka", f"spalone wg Sentinel-2, radar nie wykrył · {stats['ref_only_km2']} km²", opacity=0.6)
        item("radar_only", m & ~ref, (1.0, 0.72, 0.15), "Tylko radar", f"NISAR zgłasza zmianę, optyka nie potwierdza · {stats['radar_only_km2']} km²", opacity=0.9)
        item("hit", hit, (1.0, 0.08, 0.35), "Radar i optyka zgodne", f"NISAR wykrył, Sentinel-2 potwierdza · {stats['hit_km2']} km²")
    elif len(masks) == 2:
        both = z["mask_high_confidence"].astype(bool) if "mask_high_confidence" in z.files else masks[0] & masks[1]
        stats.update(both_km2=km2(both), single_km2=km2(change & ~both))
        item("single", change & ~both, (1.0, 0.72, 0.15), "Zmiana prawdopodobna", f"tylko jedna z metod · {stats['single_km2']} km²", opacity=0.9)
        item("both", both, (1.0, 0.08, 0.35), "Zmiana pewna", f"dwie niezależne metody zgodne · {stats['both_km2']} km²")
    else:
        item("change", change, (1.0, 0.08, 0.35), "Wykryta zmiana", f"jedna metoda radarowa · {stats['any_km2']} km²")
    if case.get("kind") == "volcano" and "displacement_cm" in z.files:
        r, c, ok, _ = small; d = cm.resample_to(z["displacement_cm"], shape)[r, c]
        v = max(2.0, float(np.nanpercentile(np.abs(d), 99))); rgba = matplotlib.colormaps["RdBu_r"](np.clip((d + v) / (2 * v), 0, 1))
        rgba[~(ok & np.isfinite(d)), 3] = 0; layers["disp"] = webp(rgba, quality=85); stats["disp_cm"] = round(v)
        legend.insert(0, {"key": "disp", "color": "linear-gradient(90deg,#2166ac,#f7f7f7,#b2182b)", "label": "Ruch gruntu (InSAR)", "on": False, "opacity": 0.75,
                          "note": f"wzdłuż linii widzenia radaru, skala ±{stats['disp_cm']} cm; czerwony i niebieski to przeciwne kierunki"})
    dates = {}
    for key in ("gcov_before", "gcov_after"):
        if (folder / f"{key}.npz").exists():
            d = cm.to_db(cm.nanfilter(nio.cached(folder / f"{key}.npz", None)["HHHH"], 3))
            lo, hi = np.nanpercentile(d, [2, 98]); r, c, ok, _ = small
            g = np.clip((cm.resample_to(d, shape)[r, c] - lo) / (hi - lo), 0, 1)
            layers[key.replace("gcov_", "radar_")] = webp(np.dstack([np.nan_to_num(g)] * 3 + [(ok & np.isfinite(g)).astype(float)]), quality=82)
        if key in case: t = case[key].split("_")[11]; dates[key] = f"{t[6:8]}.{t[4:6]}.{t[:4]}"
    tour = [dict(t, text=fill(t["text"], stats)) for t in case.get("tour", [])]
    cfg = {"title": case.get("title_pl", case.get("title", name)), "event": case.get("event_date"), "dates": dates, "bbox": full[3], "tour": tour,
           "tour_label": case.get("tour_label", "Przelot z przewodnikiem"), "legend": legend, "layers": layers}
    html = TEMPLATE.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
    dst = out / name / "map3d.html"; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(html, encoding="utf-8")
    print(f"[{name}] {dst}  ({dst.stat().st_size / 1e6:.1f} MB, {len(tour)} tour stops) {stats}")


def fill(text, stats):
    """Tour captions may quote measured numbers as {key} (keys of the stats dict), so they never go stale."""
    for k, v in stats.items(): text = text.replace("{" + k + "}", str(v).replace(".", ","))
    return text


TEMPLATE = r"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>NISAR 3D</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<style>
html,body,#map{height:100%;margin:0;background:#0b1420}
body{font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#e8edf4}
.panel{position:absolute;z-index:5;top:14px;left:14px;width:310px;max-width:calc(100vw - 28px);box-sizing:border-box;background:rgba(11,20,32,.9);
  border:1px solid #24364c;border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px)}
h1{font-size:17px;margin:0 0 2px;line-height:1.25}.sub{color:#9aa9bb;font-size:12.5px;margin-bottom:10px}
h2{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7fe0d8;margin:12px 0 6px}
.seg{display:flex;gap:4px}.seg button{flex:1;padding:7px 4px;font:inherit;font-size:12.5px;color:#cfd8e3;background:#15243a;border:1px solid #2b415c;border-radius:8px;cursor:pointer}
.seg button.on{background:#7fe0d8;color:#06202a;border-color:#7fe0d8;font-weight:600}
label.row{display:flex;align-items:flex-start;gap:8px;margin:5px 0;cursor:pointer}label.row input{margin-top:3px}
.sw{flex:none;width:14px;height:14px;border-radius:3px;margin-top:2px}
small{color:#9aa9bb;display:block;font-size:11.5px}
#tour{width:100%;margin-top:12px;padding:10px;font:inherit;font-weight:600;color:#06202a;background:#ffb37a;border:0;border-radius:8px;cursor:pointer}
#cap{position:absolute;z-index:5;left:50%;bottom:34px;transform:translateX(-50%);width:min(640px,calc(100vw - 32px));box-sizing:border-box;
  background:rgba(11,20,32,.92);border:1px solid #24364c;border-radius:12px;padding:12px 16px;font-size:16px;text-align:center;display:none}
#cap b{color:#7fe0d8;font-weight:600;font-size:12px;letter-spacing:.06em;display:block;margin-bottom:2px}
.place{background:rgba(11,20,32,.85);border:1px solid #7fe0d8;color:#fff;border-radius:6px;padding:2px 7px;font-size:12.5px;white-space:nowrap}
.src{position:absolute;z-index:4;right:8px;bottom:22px;font-size:10.5px;color:#aeb9c7;text-shadow:0 0 3px #000}
@media (max-width:640px){.panel{width:auto;right:14px;max-height:46vh;overflow:auto}#cap{font-size:14px}}
</style></head>
<body><div id="map"></div>
<div class="panel">
  <h1 id="title"></h1><div class="sub" id="sub"></div>
  <h2>Podkład</h2>
  <div class="seg" id="base"><button data-b="sat" class="on">Zdjęcie</button><button data-b="radar_before">Radar przed</button><button data-b="radar_after">Radar po</button></div>
  <small id="basenote"></small>
  <h2>Co wykrył NISAR</h2>
  <div id="legend"></div>
  <button id="tour"></button>
</div>
<div id="cap"></div>
<div class="src">NISAR L2 GCOV/GUNW (NASA/ISRO, ASF DAAC) · zdjęcie: Esri World Imagery · teren: AWS Terrain Tiles</div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const C = __CFG__, D = C.dates, $ = id => document.getElementById(id), PLAY = '▶ ' + C.tour_label, HALT = '■ Zatrzymaj przelot';
$('title').textContent = C.title; document.title = C.title + ' · NISAR 3D'; $('tour').textContent = PLAY;
$('sub').textContent = 'Zdarzenie: ' + C.event + ' · radar przed: ' + (D.gcov_before || '?') + ', po: ' + (D.gcov_after || '?');
for (const L of [...C.legend].reverse()) { const row = document.createElement('label'); row.className = 'row';
  row.innerHTML = '<input type="checkbox" data-l="' + L.key + '"' + (L.on ? ' checked' : '') + '><span class="sw" style="background:' + L.color + '"></span><span>' + L.label + '<small>' + L.note + '</small></span>';
  $('legend').append(row); }
const NOTE = {sat: 'Archiwalne zdjęcie optyczne (nie z dnia zdarzenia), dla orientacji w terenie.',
  radar_before: 'Obraz radarowy NISAR sprzed zdarzenia. Jasne = silne odbicie.', radar_after: 'Obraz radarowy NISAR po zdarzeniu. Przełączaj „przed/po”, żeby zobaczyć zmianę.'};
// our embedded pictures are served as XYZ tiles through a custom protocol (ovl://<layer>/z/x/y)
const [BW, BS, BE, BN] = C.bbox, my = la => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
const IMG = {}; for (const k in C.layers) IMG[k] = new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = C.layers[k]; });
maplibregl.addProtocol('ovl', async p => {
  const [k, z, x, y] = p.url.slice(6).split('/'), im = await IMG[k], n = 2 ** z, cv = document.createElement('canvas'); cv.width = cv.height = 256;
  const fx = v => (v / n * 360 - 180 - BW) / (BE - BW) * im.width, fy = v => (my(BN) - Math.PI * (1 - 2 * v / n)) / (my(BN) - my(BS)) * im.height;
  const x0 = fx(+x), x1 = fx(+x + 1), y0 = fy(+y), y1 = fy(+y + 1), sx0 = Math.max(0, x0), sx1 = Math.min(im.width, x1), sy0 = Math.max(0, y0), sy1 = Math.min(im.height, y1);
  if (sx1 > sx0 && sy1 > sy0) { const ctx = cv.getContext('2d'), q = 256 / (x1 - x0), u = 256 / (y1 - y0); ctx.imageSmoothingEnabled = SMOOTH(k);
    ctx.drawImage(im, sx0, sy0, sx1 - sx0, sy1 - sy0, (sx0 - x0) * q, (sy0 - y0) * u, (sx1 - sx0) * q, (sy1 - sy0) * u); }
  return {data: await (await new Promise(r => cv.toBlob(r, 'image/png'))).arrayBuffer()};
});
const img = k => ({type: 'raster', tiles: ['ovl://' + k + '/{z}/{x}/{y}'], tileSize: 256, minzoom: 8, maxzoom: 14, bounds: C.bbox});
const WIDE = innerWidth > 900, PAD = {left: WIDE ? 330 : 0, top: 0, right: 0, bottom: WIDE ? 0 : 60};
const style = {version: 8, sources: {
    sat: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 17},
    dem: {type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 13, encoding: 'terrarium'}},
  layers: [{id: 'sat', type: 'raster', source: 'sat'}],
  sky: {'sky-color': '#5d8fc4', 'horizon-color': '#c9d9ea', 'fog-color': '#c9d9ea', 'sky-horizon-blend': 0.6, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.2}};
const SMOOTH = k => k.startsWith('radar') || k === 'disp';
for (const L of [{key: 'radar_before'}, {key: 'radar_after'}, ...C.legend]) if (C.layers[L.key]) {
  style.sources[L.key] = img(L.key);
  style.layers.push({id: L.key, type: 'raster', source: L.key, paint: {'raster-opacity': L.opacity ?? 1, 'raster-fade-duration': 0,
    'raster-resampling': SMOOTH(L.key) ? 'linear' : 'nearest'}, layout: {visibility: L.on ? 'visible' : 'none'}});
}
const map = new maplibregl.Map({container: 'map', style, bounds: [[BW, BS], [BE, BN]], fitBoundsOptions: {padding: 20}, pitch: 55, bearing: 20, maxPitch: 80, attributionControl: false});
map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), 'top-right');
map.on('load', () => { map.setTerrain({source: 'dem', exaggeration: 1.3}); window.READY = true; });
const vis = (k, on) => map.getLayer(k) && map.setLayoutProperty(k, 'visibility', on ? 'visible' : 'none');
function base(b) {
  document.querySelectorAll('#base button').forEach(x => x.classList.toggle('on', x.dataset.b === b));
  vis('radar_before', b === 'radar_before'); vis('radar_after', b === 'radar_after'); $('basenote').textContent = NOTE[b];
}
document.querySelectorAll('#base button').forEach(x => { if (x.dataset.b !== 'sat' && !C.layers[x.dataset.b]) x.remove(); else x.onclick = () => base(x.dataset.b); });
$('basenote').textContent = NOTE.sat;
const boxes = [...document.querySelectorAll('input[data-l]')]; boxes.forEach(x => x.onchange = () => vis(x.dataset.l, x.checked));
const show = keys => boxes.forEach(x => { x.checked = keys.includes(x.dataset.l); vis(x.dataset.l, x.checked); });
C.tour.filter(t => t.name).forEach(t => { const el = document.createElement('div'); el.className = 'place'; el.textContent = t.name;
  new maplibregl.Marker({element: el, anchor: 'bottom', offset: [0, -14]}).setLngLat([t.lon, t.lat]).addTo(map); });

// guided fly-through: the camera looks along the direction of travel (towards the next stop)
const T = C.tour; let run = 0;
const bearing = (a, b) => (Math.atan2((b.lon - a.lon) * Math.cos(a.lat * Math.PI / 180), b.lat - a.lat) * 180 / Math.PI + 360) % 360;
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function tour() {
  const me = ++run, cap = $('cap'); $('tour').textContent = HALT; cap.style.display = 'block';
  for (let i = 0; i < T.length && me === run; i++) {
    const t = T[i], b = t.bearing ?? (i + 1 < T.length ? bearing(t, T[i + 1]) : bearing(T[i - 1], t));
    cap.innerHTML = '<b>' + (i + 1) + ' / ' + T.length + '</b>' + t.text; if (t.on) show(t.on);
    map.flyTo({center: [t.lon, t.lat], zoom: t.zoom ?? 12.4, pitch: t.pitch ?? 58, bearing: b, padding: PAD, duration: i ? 6500 : 3500, essential: true, curve: 1});
    await new Promise(r => map.once('moveend', r)); if (me !== run) return;
    await sleep(t.hold ?? 3500);
  }
  if (me === run) stop();
}
function stop() { run++; map.stop(); $('tour').textContent = PLAY; $('cap').style.display = 'none'; }
if (T.length < 2) $('tour').remove(); else $('tour').onclick = () => $('tour').textContent === HALT ? stop() : tour();
map.on('dragstart', () => { if ($('tour') && $('tour').textContent === HALT) stop(); });
</script></body></html>"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output"))
    A = p.parse_args()
    for n, c in json.loads(Path(A.cases).read_text()).items():
        if A.only and n != A.only: continue
        build(n, c, Path(A.data), Path(A.out))
