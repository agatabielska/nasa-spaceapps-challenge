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
--lang en builds map3d_en.html from "tour_en" (stops may carry a "title" shown as the caption headline).
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


# All text of the page, per language. Python uses the legend entries, the rest goes to the browser as C.t.
TEXT = {
 "pl": dict(lang="pl", blind=("Radar tu nie widzi", "strome zbocza i cień radarowy · {blind_pct}% obszaru. Brak koloru tutaj nie oznacza braku zniszczeń."),
    ref_only=("Tylko optyka", "spalone wg Sentinel-2, radar nie wykrył · {ref_only_km2} km²"),
    radar_only=("Tylko radar", "NISAR zgłasza zmianę, optyka nie potwierdza · {radar_only_km2} km²"),
    hit=("Radar i optyka zgodne", "NISAR wykrył, Sentinel-2 potwierdza · {hit_km2} km²"),
    single=("Zmiana prawdopodobna", "tylko jedna z metod · {single_km2} km²"), both=("Zmiana pewna", "dwie niezależne metody zgodne · {both_km2} km²"),
    change=("Wykryta zmiana", "jedna metoda radarowa · {any_km2} km²"),
    disp=("Ruch gruntu (InSAR)", "wzdłuż linii widzenia radaru, skala ±{disp_cm} cm; czerwony i niebieski to przeciwne kierunki"),
    tour_label="Przelot z przewodnikiem", end="■ Zakończ przelot", event="Zdarzenie", before="radar przed", after="po", base="Podkład", found="Co wykrył NISAR",
    sat="Zdjęcie", rb="Radar przed", ra="Radar po", prev="Wstecz", next="Dalej", play="Odtwarzaj", pause="Pauza",
    n_sat="Archiwalne zdjęcie optyczne (nie z dnia zdarzenia), dla orientacji w terenie.",
    n_rb="Obraz radarowy NISAR sprzed zdarzenia. Jasne = silne odbicie.", n_ra="Obraz radarowy NISAR po zdarzeniu. Przełączaj „przed/po”, żeby zobaczyć zmianę.",
    src="NISAR L2 GCOV/GUNW (NASA/ISRO, ASF DAAC) · zdjęcie: Esri World Imagery · teren: AWS Terrain Tiles"),
 "en": dict(lang="en", blind=("Radar cannot see here", "steep slopes and radar shadow · {blind_pct}% of the area. No colour here does not mean no damage."),
    ref_only=("Optical only", "burnt according to Sentinel-2, missed by radar · {ref_only_km2} km²"),
    radar_only=("Radar only", "NISAR reports a change, optical imagery does not confirm it · {radar_only_km2} km²"),
    hit=("Radar and optical agree", "detected by NISAR, confirmed by Sentinel-2 · {hit_km2} km²"),
    single=("One method only", "a weaker signal, shown separately · {single_km2} km²"), both=("Both methods agree", "two independent radar methods · {both_km2} km²"),
    change=("Detected change", "one radar method · {any_km2} km²"),
    disp=("Ground motion (InSAR)", "along the radar line of sight, scale ±{disp_cm} cm; red and blue are opposite directions"),
    tour_label="Guided tour", end="■ End tour", event="Event", before="radar before", after="after", base="Base layer", found="What NISAR detected",
    sat="Photo", rb="Radar before", ra="Radar after", prev="Back", next="Next", play="Play", pause="Pause",
    n_sat="Archive optical image (not from the day of the event), for orientation.",
    n_rb="NISAR radar image before the event. Bright = strong echo.", n_ra="NISAR radar image after the event. Switch before/after to see the change.",
    src="NISAR L2 GCOV/GUNW (NASA/ISRO, ASF DAAC) · imagery: Esri World Imagery · terrain: AWS Terrain Tiles"),
}


def build(name, case, data, out, lang="pl"):
    import matplotlib; L = TEXT[lang]
    folder = data / name
    if not (folder / "layers.npz").exists(): print(f"[{name}] run analyze_case.py first"); return
    z = np.load(folder / "layers.npz"); x, y = z["x"], z["y"]; epsg = int(z["epsg"]); shape = (len(y), len(x))
    full = mercator_index(x, y, epsg, max(shape)); small = mercator_index(x, y, epsg, 1400)
    px_km2 = (float(x[1] - x[0]) / 1000) ** 2; km2 = lambda m: round(float(m.sum() * px_km2), 1)
    layers, legend, stats = {}, [], {}

    def flat(mask, idx, col):
        r, c, ok, _ = idx; m = mask[r, c] & ok; rgba = np.zeros(m.shape + (4,)); rgba[m] = col; return rgba

    def item(key, mask, col, on=True, opacity=1.0, idx=full):
        """One switchable overlay + its legend row (drawn in the order the items are added, last on top)."""
        layers[key] = webp(flat(mask, idx, (*col, 1.0)))
        legend.append({"key": key, "color": "#%02x%02x%02x" % tuple(int(v * 255) for v in col), "label": L[key][0], "note": fill(L[key][1], stats, lang), "on": on, "opacity": opacity})

    masks = [z[k].astype(bool) for k in ("mask_backscatter", "mask_coherence") if k in z.files]
    change = np.any(masks, axis=0) if masks else np.zeros(shape, bool)
    seen = np.zeros(shape, bool)
    for k in ("score_backscatter", "coherence_loss"):
        if k in z.files: seen |= np.isfinite(cm.resample_to(z[k], shape))
    stats.update(any_km2=km2(change), blind_pct=round(float((~seen).mean() * 100)))
    if stats["blind_pct"] >= 1:   # where NEITHER method has a usable signal (layover, radar shadow, water): shown, not left as "no damage"
        item("blind", ~seen, (0.25, 0.55, 1.0), on=False, opacity=0.6, idx=small)
    if (folder / "dnbr.npy").exists():
        # an independent optical reference exists (Sentinel-2 burn severity, same threshold as validate_case.py): show the comparison itself
        d = cm.match(np.load(folder / "dnbr.npy"), shape); ok = np.isfinite(d); ref = ok & (d > 0.27); m = change & ok; hit = m & ref
        stats.update(ref_km2=km2(ref), hit_km2=km2(hit), radar_only_km2=km2(m & ~ref), ref_only_km2=km2(ref & ~m),
                     recall_pct=round(float(hit.sum() / max(ref.sum(), 1) * 100)), precision_pct=round(float(hit.sum() / max(m.sum(), 1) * 100)))
        item("ref_only", ref & ~m, (0.93, 0.95, 1.0), opacity=0.6)
        item("radar_only", m & ~ref, (1.0, 0.72, 0.15), opacity=0.9)
        item("hit", hit, (1.0, 0.08, 0.35))
    elif len(masks) == 2:
        both = z["mask_high_confidence"].astype(bool) if "mask_high_confidence" in z.files else masks[0] & masks[1]
        stats.update(both_km2=km2(both), single_km2=km2(change & ~both))
        item("single", change & ~both, (1.0, 0.72, 0.15), opacity=0.9)
        item("both", both, (1.0, 0.08, 0.35))
    else:
        item("change", change, (1.0, 0.08, 0.35))
    if case.get("kind") == "volcano" and "displacement_cm" in z.files:
        r, c, ok, _ = small; d = cm.resample_to(z["displacement_cm"], shape)[r, c]
        v = max(2.0, float(np.nanpercentile(np.abs(d), 99))); rgba = matplotlib.colormaps["RdBu_r"](np.clip((d + v) / (2 * v), 0, 1))
        rgba[~(ok & np.isfinite(d)), 3] = 0; layers["disp"] = webp(rgba, quality=85); stats["disp_cm"] = round(v)
        legend.insert(0, {"key": "disp", "color": "linear-gradient(90deg,#2166ac,#f7f7f7,#b2182b)", "label": L["disp"][0], "on": False, "opacity": 0.75,
                          "note": fill(L["disp"][1], stats, lang)})
    dates = {}
    for key in ("gcov_before", "gcov_after"):
        if (folder / f"{key}.npz").exists():
            d = cm.to_db(cm.nanfilter(nio.cached(folder / f"{key}.npz", None)["HHHH"], 3))
            lo, hi = np.nanpercentile(d, [2, 98]); r, c, ok, _ = small
            g = np.clip((cm.resample_to(d, shape)[r, c] - lo) / (hi - lo), 0, 1)
            layers[key.replace("gcov_", "radar_")] = webp(np.dstack([np.nan_to_num(g)] * 3 + [(ok & np.isfinite(g)).astype(float)]), quality=82)
        if key in case: t = case[key].split("_")[11]; dates[key] = f"{t[6:8]}.{t[4:6]}.{t[:4]}"
    en = lang == "en"   # English is the language of the base fields; Polish ones carry the _pl suffix ("tour" itself is Polish)
    tour = [dict(t, text=fill(t["text"], stats, lang)) for t in case.get("tour_en" if en else "tour", [])]
    title = case.get("title_en", case.get("title", name)) if en else case.get("title_pl", case.get("title", name))
    cfg = {"title": title, "event": case.get("event_date"), "dates": dates, "bbox": full[3], "tour": tour,
           "t": {k: v for k, v in L.items() if isinstance(v, str)} | {"tour_label": case.get("tour_label_en" if en else "tour_label", L["tour_label"])},
           "legend": legend, "layers": layers}
    html = TEMPLATE.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
    dst = out / name / ("map3d_en.html" if en else "map3d.html"); dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(html, encoding="utf-8")
    print(f"[{name}] {dst}  ({dst.stat().st_size / 1e6:.1f} MB, {len(tour)} tour stops) {stats}")


def fill(text, stats, lang="pl"):
    """Captions and legend notes may quote measured numbers as {key} (keys of the stats dict), so they never go stale."""
    for k, v in stats.items(): text = text.replace("{" + k + "}", str(v).replace(".", ",") if lang == "pl" else str(v))
    return text


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>NISAR 3D</title>
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
/* tour caption: the story, so it is the largest and brightest text on the page */
#cap{position:absolute;z-index:6;left:50%;bottom:30px;transform:translateX(-50%);width:min(760px,calc(100vw - 32px));box-sizing:border-box;
  background:rgba(6,13,24,.96);border:1px solid #7fe0d8;border-radius:16px;padding:16px 20px 14px;display:none;box-shadow:0 12px 40px rgba(0,0,0,.6)}
#cap .step{color:#7fe0d8;font-weight:700;font-size:12.5px;letter-spacing:.1em;text-transform:uppercase}
#cap h3{margin:2px 0 6px;font-size:23px;line-height:1.2;color:#fff}
#cap p{margin:0;font-size:18.5px;line-height:1.45;color:#f1f5fa}
#cap .bar{display:flex;gap:5px;margin:13px 0 10px}#cap .bar i{flex:1;height:4px;border-radius:2px;background:#27405c}#cap .bar i.done{background:#7fe0d8}
#cap .nav{display:flex;gap:8px;justify-content:space-between}
#cap .nav button{font:inherit;font-size:14px;font-weight:600;color:#e8edf4;background:#15243a;border:1px solid #2b415c;border-radius:8px;padding:8px 16px;cursor:pointer}
#cap .nav button:disabled{opacity:.35;cursor:default}#cap .nav button.main{background:#7fe0d8;color:#06202a;border-color:#7fe0d8;min-width:110px}
.place{background:rgba(11,20,32,.85);border:1px solid #7fe0d8;color:#fff;border-radius:6px;padding:2px 7px;font-size:12.5px;white-space:nowrap}
.src{position:absolute;z-index:4;right:8px;bottom:22px;font-size:10.5px;color:#aeb9c7;text-shadow:0 0 3px #000}
@media (max-width:640px){.panel{width:auto;right:14px;max-height:40vh;overflow:auto}#cap{bottom:12px;padding:12px 14px}#cap h3{font-size:18px}#cap p{font-size:15.5px}}
</style></head>
<body><div id="map"></div>
<div class="panel">
  <h1 id="title"></h1><div class="sub" id="sub"></div>
  <h2 id="h_base"></h2>
  <div class="seg" id="base"><button data-b="sat" class="on"></button><button data-b="radar_before"></button><button data-b="radar_after"></button></div>
  <small id="basenote"></small>
  <h2 id="h_found"></h2>
  <div id="legend"></div>
  <button id="tour"></button>
</div>
<div id="cap"><div class="step" id="c_step"></div><h3 id="c_title"></h3><p id="c_text"></p><div class="bar" id="c_bar"></div>
  <div class="nav"><button id="c_prev"></button><button id="c_play" class="main"></button><button id="c_next"></button></div></div>
<div class="src" id="src"></div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const C = __CFG__, W = C.t, D = C.dates, $ = id => document.getElementById(id), PLAY = '▶ ' + W.tour_label, HALT = W.end;
document.documentElement.lang = W.lang; $('title').textContent = C.title; document.title = C.title + ' · NISAR 3D'; $('tour').textContent = PLAY;
$('sub').textContent = W.event + ': ' + C.event + ' · ' + W.before + ': ' + (D.gcov_before || '?') + ', ' + W.after + ': ' + (D.gcov_after || '?');
$('h_base').textContent = W.base; $('h_found').textContent = W.found; $('src').textContent = W.src;
for (const [b, k] of [['sat', 'sat'], ['radar_before', 'rb'], ['radar_after', 'ra']]) document.querySelector('[data-b=' + b + ']').textContent = W[k];
$('c_prev').textContent = '◀ ' + W.prev; $('c_next').textContent = W.next + ' ▶';
for (const L of [...C.legend].reverse()) { const row = document.createElement('label'); row.className = 'row';
  row.innerHTML = '<input type="checkbox" data-l="' + L.key + '"' + (L.on ? ' checked' : '') + '><span class="sw" style="background:' + L.color + '"></span><span>' + L.label + '<small>' + L.note + '</small></span>';
  $('legend').append(row); }
const NOTE = {sat: W.n_sat, radar_before: W.n_rb, radar_after: W.n_ra};
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

// guided tour: the camera looks along the direction of travel (towards the next stop). It plays by itself,
// and the viewer can pause it or step back and forth; dragging the map pauses it.
const T = C.tour; let idx = -1, playing = false, timer = 0, token = 0;
const bearing = (a, b) => (Math.atan2((b.lon - a.lon) * Math.cos(a.lat * Math.PI / 180), b.lat - a.lat) * 180 / Math.PI + 360) % 360;
function render() {
  const on = idx >= 0; $('cap').style.display = on ? 'block' : 'none'; $('tour').textContent = on ? HALT : PLAY; if (!on) return;
  const t = T[idx]; $('c_step').textContent = (idx + 1) + ' / ' + T.length; $('c_title').textContent = t.title || t.name || ''; $('c_title').style.display = t.title || t.name ? '' : 'none';
  $('c_text').textContent = t.text; $('c_bar').innerHTML = T.map((_, i) => '<i' + (i <= idx ? ' class="done"' : '') + '></i>').join('');
  $('c_prev').disabled = idx === 0; $('c_next').disabled = idx === T.length - 1; $('c_play').textContent = playing ? '❚❚ ' + W.pause : '▶ ' + W.play;
}
async function go(i, auto) {
  const me = ++token; clearTimeout(timer); const first = idx < 0; idx = i; const t = T[i]; if (t.on) show(t.on); render();
  const b = t.bearing ?? (i + 1 < T.length ? bearing(t, T[i + 1]) : bearing(T[i - 1], t));
  map.flyTo({center: [t.lon, t.lat], zoom: t.zoom ?? 12.4, pitch: t.pitch ?? 58, bearing: b, padding: PAD, duration: first ? 3500 : auto ? 6500 : 2800, essential: true, curve: 1});
  await new Promise(r => map.once('moveend', r)); if (me !== token || !playing) return;
  timer = setTimeout(() => { if (me !== token) return; if (idx + 1 < T.length) go(idx + 1, true); else { playing = false; render(); } }, t.hold ?? Math.max(4000, t.text.length * 55));
}
function pause() { playing = false; token++; clearTimeout(timer); map.stop(); render(); }
function play() { playing = true; go(idx >= 0 && idx < T.length - 1 ? idx : 0, true); }
function end() { pause(); idx = -1; render(); }
if (T.length < 2) $('tour').remove(); else {
  $('tour').onclick = () => idx < 0 ? play() : end(); $('c_play').onclick = () => playing ? pause() : play();
  $('c_prev').onclick = () => { playing = false; go(idx - 1, false); }; $('c_next').onclick = () => { playing = false; go(idx + 1, false); };
  map.on('dragstart', () => { if (playing) pause(); });
  if (new URLSearchParams(location.search).has('tour')) map.once('idle', play);   // ?tour starts it at once (used when embedded)
}
</script></body></html>"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output"))
    p.add_argument("--lang", default="pl", choices=list(TEXT))
    A = p.parse_args()
    for n, c in json.loads(Path(A.cases).read_text()).items():
        if A.only and n != A.only: continue
        build(n, c, Path(A.data), Path(A.out), A.lang)
