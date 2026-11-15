"""
make_timeline.py -- time-slider view of a slow process (open output/<case>/timeline.html in a browser).

  uv run python subsidence_series.py --only silesia
  uv run python make_timeline.py --only silesia

One picture of cumulative subsidence per acquisition date is embedded in the page (WebP, transparent outside the
confirmed bowls). The slider / play button fades between them, so the bowls can be watched growing. Clicking a
bowl opens its sinking curve from both satellite tracks. The page is ONE file that works when double-clicked
(needs internet for the Esri basemap and MapLibre). Same look and data contract as the other map pages:
dates[], frames[] (data URLs), image corners, bowls[{lon, lat, near, curve_cm[], check_curve_cm[], ...}].
"""
import argparse, json
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
import change_methods as cm
from make_map3d import mercator_index, webp

HERE = Path(__file__).parent
MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"]


def pl_date(s):
    y, m, d = s.split("-"); return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def build(name, case, data, out, up=None, vmax=55.0, show_from_cm=2.0):
    import matplotlib
    folder = data / name
    if not (folder / "subsidence_layers.npz").exists(): print(f"[{name}] run subsidence_series.py first"); return
    z = np.load(folder / "subsidence_layers.npz"); stats = json.loads((out / name / "stats.json").read_text())
    x, y, epsg = z["x"], z["y"], int(z["epsg"]); cum = z["cumulative_cm"]; dates = [str(d) for d in z["dates"]]
    check_dates = [str(d) for d in z["check_dates"]]
    up = up or (4 if abs(float(x[1] - x[0])) > 40 else 2)
    nm = len(dates)                                  # number of MEASURED dates; everything after is projection
    fut = [d for d in (stats["bowls"][0]["forecast"]["dates"][1:] if stats["bowls"] and stats["bowls"][0].get("forecast") else [])]
    # per-pixel projection, same rule as the curves: straight line through the last 4 measurements, sinking only
    full = np.concatenate([np.zeros((1,) + cum.shape[1:], "float32"), np.nan_to_num(cum, nan=0.0)])
    tt = np.array([(np.datetime64(d) - np.datetime64(dates[0])).astype(int) for d in dates], float)
    k4 = slice(nm - 4, nm); tc = tt[k4] - tt[k4].mean()
    slope = np.minimum((tc[:, None, None] * (full[k4] - full[k4].mean(0))).sum(0) / (tc ** 2).sum(), 0.0)      # cm/day, <= 0
    fut_days = [float((np.datetime64(d) - np.datetime64(dates[-1])).astype(int)) for d in fut]
    cum_all = [None] + [cum[i] for i in range(cum.shape[0])] + [cum[-1] + slope * dd for dd in fut_days]
    dates = dates + fut
    events = []
    for ev in case.get("events", []):              # an event appears at the first slider stop on/after its (possibly approximate) date
        stop = next((i for i, d in enumerate(dates) if ev.get("date") and d >= ev["date"]), len(dates) - 1)
        events.append({**ev, "stop": stop})
    # finer grid, so the 80 m pixels become smooth blobs instead of squares
    xf = np.linspace(x[0], x[-1], len(x) * up); yf = np.linspace(y[0], y[-1], len(y) * up)
    r, c, ok, (w, s, e, n) = mercator_index(xf, yf, epsg, max(len(xf), len(yf)))
    near = ndi.binary_dilation(z["confirmed"], iterations=4 if up == 4 else 14)              # only confirmed bowls (and their rim) are drawn
    cmap = matplotlib.colormaps["inferno"]; frames = []; per_date = []
    zoom = lambda a: ndi.zoom(np.nan_to_num(a, nan=0.0), up, order=1)
    nearf = zoom(near.astype("float32")) > 0.5
    px_km2 = (float(x[1] - x[0]) / 1000) ** 2
    for t in range(len(dates)):
        sink = np.zeros(cum.shape[1:], "float32") if t == 0 else -cm.nanfilter(cum_all[t], 3 if up == 4 else 7)
        sf = zoom(np.where(near, sink, 0.0))
        rgba = cmap(np.clip(sf / vmax, 0, 1) * 0.92 + 0.08)
        rgba[..., 3] = np.clip((sf - show_from_cm) / 3.0, 0, 1) * nearf * 0.95        # soft edge, fully visible from ~5 cm
        frames.append(webp(np.where(ok[..., None], rgba[r, c], 0.0), quality=85))
        inside = np.where(z["confirmed"], sink, np.nan)
        per_date.append({"max_cm": round(float(np.nanmax(inside)), 1) if t else 0.0,
                         "area_km2": round(float((inside >= 5).sum() * px_km2), 1) if t else 0.0})
    bowls = [{"lon": b["lon"], "lat": b["lat"], "near": b["near"], "area_km2": b["area_km2"], "max_cm": b["max_sink_cm"],
              "rate": b["rate_cm_per_month"], "check_rate": b.get("check_rate_cm_per_month"),
              "curve": b["curve_cm"], "fc": b.get("forecast")} for b in stats["bowls"]]
    gis = json.loads((out / name / "gis_check.json").read_text()) if (out / name / "gis_check.json").exists() else None
    if gis:
        for b, g in zip(bowls, gis["per_bowl"]): b["mine"] = g["deposit"]; b["og"] = g["mining_area"]
    cfg = {"fc": stats.get("forecast"), "gis": None if not gis else {"outlines": gis["outlines"], "inside": gis["bowls_inside"], "n": gis["bowls"], "cover": round(gis["share_of_box_covered"] * 100)},
           "events": events, "title": case.get("title_pl", case.get("title", name)), "nm": nm, "sub": f"NISAR, pasmo L · {nm - 1} kolejnych pomiarów · {pl_date(dates[0])} – {pl_date(dates[nm - 1])}" + (f" · prognoza do {pl_date(dates[-1])}" if fut else ""),
           "dates": dates, "labels": [pl_date(d) for d in dates], "check_dates": check_dates, "frames": frames, "per_date": per_date,
           "coords": [[w, n], [e, n], [e, s], [w, s]], "bbox": [w, s, e, n], "bowls": bowls, "vmax": vmax,
           "confirmed": stats["confirmed"], "candidates": stats["candidates"]}
    html = TEMPLATE.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
    path = out / name / "timeline.html"; path.write_text(html, encoding="utf-8")
    print(f"[{name}] {path}  ({len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB)")
    print("   per date:", [(d[5:] + ("*" if i >= nm else ""), p["max_cm"], p["area_km2"]) for i, (d, p) in enumerate(zip(dates, per_date))], "(* = projection)")


TEMPLATE = r"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Osiadanie terenu w czasie</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<style>
html,body,#map{height:100%;margin:0;background:#0b1420}
body{font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#e8edf4}
.panel{position:absolute;z-index:5;left:14px;top:14px;width:310px;background:rgba(11,20,32,.93);border:1px solid #24364c;border-radius:14px;padding:14px 16px}
h1{font-size:17px;margin:0 0 2px;line-height:1.25}.sub{color:#9aa9bb;font-size:12.5px;margin-bottom:10px}
h2{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7fe0d8;margin:12px 0 6px}
.kpi{display:flex;gap:8px}.kpi div{flex:1;background:#15243a;border:1px solid #2b415c;border-radius:10px;padding:8px 10px}
.kpi b{display:block;font-size:22px;line-height:1.1;color:#ffb37a;font-variant-numeric:tabular-nums}.kpi span{font-size:11.5px;color:#9aa9bb}
.bar{height:10px;border-radius:5px;background:linear-gradient(90deg,#1b0c41,#781c6d,#ed6925,#fcffa4)}
.scale{display:flex;justify-content:space-between;font-size:11.5px;color:#9aa9bb;margin-top:3px}
small{color:#9aa9bb;display:block;font-size:11.5px;margin-top:8px}
#time{position:absolute;z-index:5;left:50%;bottom:22px;transform:translateX(-50%);width:min(760px,92vw);box-sizing:border-box;
  background:rgba(11,20,32,.93);border:1px solid #24364c;border-radius:14px;padding:12px 16px 10px}
#row{display:flex;align-items:center;gap:12px}
#play{width:40px;height:40px;flex:none;border:0;border-radius:50%;background:#7fe0d8;color:#06202a;font-size:16px;font-weight:700;cursor:pointer}
#date{font-size:19px;font-weight:650;min-width:210px}#day{color:#9aa9bb;font-size:12.5px}
input[type=range]{width:100%;accent-color:#7fe0d8;margin:8px 0 0}
#ticks{display:flex;justify-content:space-between;font-size:10.5px;color:#7f8ea3;margin-top:2px}#ticks .f{color:#b79cff}#ticks .e{color:#ff8a8a;font-weight:700}
#badge{display:none;margin-left:10px;padding:2px 9px;border-radius:20px;background:#b79cff;color:#1a0f3a;font-size:11.5px;font-weight:700;letter-spacing:.06em;vertical-align:middle}
body.fut .kpi b{color:#b79cff}body.fut #play{background:#b79cff}body.fut input[type=range]{accent-color:#b79cff}
#chart{position:absolute;z-index:5;right:14px;top:14px;width:360px;background:rgba(11,20,32,.95);border:1px solid #24364c;border-radius:14px;padding:12px 14px;display:none}
#chart h3{margin:0;font-size:15px}#chart .x{position:absolute;right:10px;top:8px;cursor:pointer;color:#9aa9bb;font-size:18px;border:0;background:none}
#chart p{margin:2px 0 6px;color:#9aa9bb;font-size:12.5px}.lg{font-size:11.5px;color:#cfd8e3}.lg i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 5px 0 10px}
.boom{width:26px;height:26px;position:relative;cursor:pointer}
.boom:before,.boom:after,.boom i{content:"";position:absolute;inset:0;border-radius:50%;border:2px solid #ff4d4d;animation:boom 1.6s ease-out infinite}
.boom:after{animation-delay:.5s}.boom i{animation-delay:1s}
.boom b{position:absolute;inset:7px;border-radius:50%;background:#ff4d4d;box-shadow:0 0 12px 4px rgba(255,77,77,.8)}
@keyframes boom{0%{transform:scale(.4);opacity:1}100%{transform:scale(4.2);opacity:0}}
#ev{position:absolute;z-index:6;left:50%;bottom:150px;transform:translateX(-50%);width:min(560px,90vw);box-sizing:border-box;background:rgba(40,12,16,.95);border:1px solid #ff4d4d;border-radius:12px;padding:10px 14px;display:none}
#ev b{color:#ff8a8a;display:block;font-size:15px}#ev span{font-size:12.5px;color:#f1d5d5}
.src{position:absolute;z-index:4;right:8px;bottom:6px;font-size:10.5px;color:#aeb9c7;text-shadow:0 0 3px #000}
@media (max-width:760px){.panel{width:auto;right:14px}#chart{left:14px;right:14px;width:auto;top:auto;bottom:150px}#date{min-width:0;font-size:16px}}
</style></head><body>
<div id="map"></div>
<div class="panel"><h1 id="title"></h1><div class="sub" id="sub"></div>
  <div class="kpi"><div><b id="kmax">0</b><span>cm, najgłębsza niecka</span></div><div><b id="karea">0</b><span>km² opadło o ponad 5 cm</span></div></div>
  <h2>Osiadanie od pierwszego pomiaru</h2><div class="bar"></div><div class="scale"><span>5 cm</span><span id="vmax"></span></div>
  <small id="note"></small><label id="gisrow" style="display:none;margin-top:10px;font-size:12.5px;cursor:pointer"><input type="checkbox" id="gis" checked> Granice obszarów górniczych (PIG-PIB)</label><small id="gisnote"></small><button id="all" style="margin-top:10px;width:100%;padding:8px;font:inherit;font-size:12.5px;color:#cfd8e3;background:#15243a;border:1px solid #2b415c;border-radius:8px;cursor:pointer">Pokaż cały obszar</button></div>
<div id="chart"><button class="x" onclick="closeChart()">×</button><h3 id="ctitle"></h3><p id="csub"></p><svg id="svg" viewBox="0 0 332 190" width="100%"></svg>
  <div class="lg"><i style="background:#ff7a59"></i>pomiar NISAR<i style="background:#b79cff"></i>prognoza przy obecnym tempie</div><small id="fcnote" style="margin-top:4px"></small></div>
<div id="ev"><b id="evt"></b><span id="evn"></span></div>
<div id="time"><div id="row"><button id="play" title="Odtwórz">▶</button><div><div><span id="date" style="display:inline-block;min-width:0"></span><span id="badge">PROGNOZA</span></div><div id="day"></div></div></div>
  <input id="sl" type="range" min="0" step="1" value="0"><div id="ticks"></div></div>
<div class="src">Dane: NISAR L2 GUNW (NASA/ISRO, ASF DAAC) · podkład: Esri World Imagery</div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const C = __CFG__, N = C.dates.length, $ = id => document.getElementById(id);
const NM = C.nm, STOPS = N, fr = i => i;
$('title').textContent = C.title; $('sub').textContent = C.sub; $('vmax').textContent = C.vmax + ' cm i więcej';
if (C.fc) $('fcnote').textContent = 'Prognoza do ' + C.fc.until.slice(8) + '.' + C.fc.until.slice(5, 7) + ' zakłada stałe tempo z ostatnich 5 tygodni. W teście na ukrytych pomiarach myliła się przeciętnie o ' + C.fc.backtest.median_abs_error_pct + '%, stąd szeroki pas.';
$('note').textContent = 'Pokazano ' + C.confirmed + ' niecek: tylko te, które widzi też drugi, niezależny przelot satelity. Ruch w linii widzenia radaru. Kliknij kółko, żeby przybliżyć nieckę i zobaczyć jej krzywą.';
const style = {version: 8, glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf', sources: {
    sat: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 17},
    lab: {type: 'raster', tiles: ['https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 15}},
  layers: [{id: 'bg', type: 'background', paint: {'background-color': '#0b1420'}},
           {id: 'sat', type: 'raster', source: 'sat', paint: {'raster-brightness-max': 0.5, 'raster-saturation': -0.55}}]};
const [BW, BS, BE, BN] = C.bbox;
const map = new maplibregl.Map({container: 'map', style, bounds: [[BW, BS], [BE, BN]], fitBoundsOptions: {padding: {top: 20, bottom: 130, left: 330, right: 20}}, attributionControl: false});
map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
let cur = 0, timer = null, sel = null;
map.on('load', () => {
  C.frames.forEach((url, i) => {
    map.addSource('f' + i, {type: 'image', url, coordinates: C.coords});
    map.addLayer({id: 'f' + i, type: 'raster', source: 'f' + i, paint: {'raster-opacity': i ? 0 : 1, 'raster-opacity-transition': {duration: 450}, 'raster-fade-duration': 0, 'raster-resampling': 'linear'}});
  });
  map.addLayer({id: 'lab', type: 'raster', source: 'lab', paint: {'raster-opacity': 0.9}});
  if (C.gis) {   // official licence boundaries of coal mines: independent GIS data, drawn as outlines
    map.addSource('og', {type: 'geojson', data: C.gis.outlines});
    map.addLayer({id: 'og-fill', type: 'fill', source: 'og', paint: {'fill-color': '#7fe0d8', 'fill-opacity': ['case', ['get', 'active'], 0.07, 0.02]}}, 'f0');
    map.addLayer({id: 'og-line', type: 'line', source: 'og', paint: {'line-color': ['case', ['get', 'active'], '#7fe0d8', '#5b7791'], 'line-width': ['case', ['get', 'active'], 1.6, 0.8], 'line-dasharray': [3, 2]}});
    $('gisrow').style.display = 'block';
    $('gisnote').textContent = C.gis.inside + ' z ' + C.gis.n + ' niecek leży w obszarze górniczym węgla. Te obszary zajmują ' + C.gis.cover + '% mapy, więc to nie przypadek. To granice koncesji, nie przebieg wyrobisk.';
    $('gis').onchange = e => ['og-fill', 'og-line'].forEach(l => map.setLayoutProperty(l, 'visibility', e.target.checked ? 'visible' : 'none'));
  }
  map.addSource('bowls', {type: 'geojson', data: {type: 'FeatureCollection', features: C.bowls.map((b, i) => ({type: 'Feature', id: i, properties: {i}, geometry: {type: 'Point', coordinates: [b.lon, b.lat]}}))}});
  map.addLayer({id: 'bowls', type: 'circle', source: 'bowls', paint: {'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 9, 13, 26], 'circle-color': 'rgba(0,0,0,0)',
    'circle-stroke-color': ['case', ['boolean', ['feature-state', 'on'], false], '#7fe0d8', 'rgba(255,255,255,.55)'], 'circle-stroke-width': ['case', ['boolean', ['feature-state', 'on'], false], 2.5, 1]}});
  map.on('click', 'bowls', e => openChart(e.features[0].properties.i));
  map.on('mouseenter', 'bowls', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'bowls', () => map.getCanvas().style.cursor = '');
  // optional deep link: timeline.html#t=9&bowl=0 opens a given date and bowl
  const h = new URLSearchParams(location.hash.slice(1)); show(Math.min(STOPS - 1, +h.get('t') || 0));
  if (h.has('bowl')) openChart(Math.min(C.bowls.length - 1, +h.get('bowl')));
});
const marks = C.events.map(e => { const el = document.createElement('div'); el.className = 'boom'; el.innerHTML = '<i></i><b></b>'; el.style.display = 'none';
  el.onclick = () => showEvent(e); new maplibregl.Marker({element: el}).setLngLat([e.lon, e.lat]).addTo(map); return el; });
function showEvent(e) { $('evt').textContent = e.name + ' · ' + e.date_label + (e.approximate ? ' (miejsce przybliżone)' : '');
  $('evn').textContent = e.note + (e.source ? ' Źródło: ' + e.source : ''); $('ev').style.display = 'block'; }
function show(i) {
  cur = i; $('sl').value = i; const k0 = fr(i);
  if (map.getLayer('f0')) C.frames.forEach((_, k) => map.setPaintProperty('f' + k, 'raster-opacity', k === k0 ? 1 : 0));
  const days = Math.round((new Date(C.dates[k0]) - new Date(C.dates[0])) / 864e5);
  const future = i >= NM; document.body.classList.toggle('fut', future); $('badge').style.display = future ? 'inline-block' : 'none';
  $('date').textContent = C.labels[i];
  $('day').textContent = future ? 'nie pomiar: stan przy tempie z ostatnich 5 tygodni, ' + Math.round((new Date(C.dates[i]) - new Date(C.dates[NM - 1])) / 864e5) + ' dni po ostatnim pomiarze'
    : (i ? 'dzień ' + days + ' od pierwszego pomiaru' : 'pierwszy pomiar: punkt odniesienia');
  $('kmax').textContent = C.per_date[k0].max_cm.toFixed(0); $('karea').textContent = C.per_date[k0].area_km2.toFixed(1);
  let shown = null; C.events.forEach((e, k) => { const on = i >= e.stop; marks[k].style.display = on ? 'block' : 'none'; if (on && i === e.stop) shown = e; });
  if (shown) showEvent(shown); else $('ev').style.display = 'none';
  if (sel !== null) draw(sel);
}
$('all').onclick = () => { closeChart(); map.fitBounds([[BW, BS], [BE, BN]], {padding: {top: 20, bottom: 130, left: 330, right: 20}}); };
const sl = $('sl'); sl.max = STOPS - 1; sl.oninput = e => { stop(); show(+e.target.value); };
$('ticks').innerHTML = C.dates.map((d, i) => '<span class="' + (C.events.some(e => e.stop === i) ? 'e' : i >= NM ? 'f' : '') + '">' + (C.events.some(e => e.stop === i) ? '⚠ ' : '') + d.slice(8) + '.' + d.slice(5, 7) + '</span>').join('');
function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶'; }
$('play').onclick = () => { if (timer) return stop(); $('play').textContent = '❚❚'; if (cur === STOPS - 1) show(0);
  timer = setInterval(() => { if (cur >= STOPS - 1) return stop(); show(cur + 1); }, 900); };
function openChart(i) { if (sel !== null) map.setFeatureState({source: 'bowls', id: sel}, {on: false});
  sel = i; map.setFeatureState({source: 'bowls', id: i}, {on: true}); $('chart').style.display = 'block'; draw(i);
  map.flyTo({center: [C.bowls[i].lon, C.bowls[i].lat], zoom: Math.max(map.getZoom(), 12.3), duration: 1200}); }
function closeChart() { if (sel !== null) map.setFeatureState({source: 'bowls', id: sel}, {on: false}); sel = null; $('chart').style.display = 'none'; }
function draw(i) {
  const b = C.bowls[i], W = 332, H = 190, L = 34, R = 8, T = 8, B = 24;
  $('ctitle').textContent = b.mine ? 'Niecka nad złożem ' + b.mine : 'Niecka koło: ' + b.near;
  $('csub').textContent = (b.og ? 'obszar górniczy ' + b.og + ' · ' : '') + b.area_km2 + ' km² · potwierdzona drugim torem satelity';
  const f = b.fc, MD = C.dates.slice(0, NM), t0 = +new Date(C.dates[0]), t1 = +new Date(f ? f.dates[f.dates.length - 1] : C.dates[NM - 1]);
  const lo = Math.min(...b.curve, ...(f ? f.low_cm : []), -1);
  const X = d => L + (new Date(d) - t0) / (t1 - t0) * (W - L - R), Y = v => T + (v / lo) * (H - T - B);
  const path = (ds, vs) => ds.map((d, k) => vs[k] === null ? '' : (X(d).toFixed(1) + ',' + Y(vs[k]).toFixed(1))).filter(Boolean).join(' ');
  const step = lo < -80 ? 40 : lo < -30 ? 20 : lo < -12 ? 10 : 5; let g = '';
  for (let v = 0; v >= lo; v -= step) g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#24364c"/><text x="${L - 5}" y="${Y(v) + 4}" fill="#9aa9bb" font-size="10.5" text-anchor="end">${v}</text>`;
  const lbl = (d, anchor) => g += `<text x="${X(d)}" y="${H - 6}" fill="#9aa9bb" font-size="10.5" text-anchor="${anchor}">${d.slice(8)}.${d.slice(5, 7)}</text>`;
  lbl(C.dates[0], 'start'); lbl(C.dates[NM - 1], 'middle'); if (f) lbl(f.dates[f.dates.length - 1], 'end');
  if (f) {   // projection: band + dashed line in a different colour, starting at the last measurement
    const up = f.dates.map((d, k) => X(d).toFixed(1) + ',' + Y(f.high_cm[k]).toFixed(1)), dn = f.dates.map((d, k) => X(d).toFixed(1) + ',' + Y(f.low_cm[k]).toFixed(1)).reverse();
    g += `<polygon points="${up.concat(dn).join(' ')}" fill="#b79cff" opacity="0.16"/>`;
    g += `<polyline points="${path(f.dates, f.cm)}" fill="none" stroke="#b79cff" stroke-width="2.2" stroke-dasharray="6 4"/>`;
    g += `<line x1="${X(C.dates[NM - 1])}" x2="${X(C.dates[NM - 1])}" y1="${T}" y2="${H - B}" stroke="#44566e" stroke-dasharray="2 3"/>`;
    if (cur < NM) g += `<text x="${W - R - 2}" y="${Y(f.cm[f.cm.length - 1]) - 7}" fill="#cdbcff" font-size="12" font-weight="600" text-anchor="end">${f.cm[f.cm.length - 1].toFixed(0)} cm</text>`;
  }
  g += `<polyline points="${path(MD, b.curve)}" fill="none" stroke="#ff7a59" stroke-width="2.6"/>`;
  const q = cur, fu = q >= NM, val = fu ? (f ? f.cm[q - NM + 1] : b.curve[NM - 1]) : b.curve[q], col = fu ? '#b79cff' : '#ff7a59';
  g += `<line x1="${X(C.dates[q])}" x2="${X(C.dates[q])}" y1="${T}" y2="${H - B}" stroke="${fu ? '#b79cff' : '#7fe0d8'}" stroke-width="1.2"/>`;
  g += `<circle cx="${X(C.dates[q])}" cy="${Y(val)}" r="4.5" fill="${col}" stroke="#0b1420" stroke-width="1.5"/>`;
  const right = X(C.dates[q]) > W - 120;
  g += `<text x="${X(C.dates[q]) + (right ? -8 : 7)}" y="${Math.max(Y(val) - 8, 16)}" fill="#fff" font-size="12" font-weight="600" text-anchor="${right ? 'end' : 'start'}">${val.toFixed(1)} cm${fu ? ' (prognoza)' : ''}</text>`;
  $('svg').innerHTML = g;
}
</script></body></html>
"""

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output")); A = p.parse_args()
    build(A.only, json.loads(Path(A.cases).read_text())[A.only], Path(A.data), Path(A.out))
