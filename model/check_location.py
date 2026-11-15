"""
check_location.py -- put the NISAR change on REAL satellite pictures to confirm WHERE it is.

Makes, inside the event folder:
  SATELLITE_CHECK.png  static 2x2 figure: Sentinel-2 true colour before/after, SWIR burn composite, NISAR overlay
  map.html             interactive map: Esri satellite basemap + Sentinel-2 before/after + NISAR decrease + FIRMS
                       (open in a browser; needs internet for the basemap and Leaflet)

  uv run --group validate python check_location.py --event output/spain_fire [--firms firms.csv]

STATUS: figure/map rendering, georeferencing (UTM -> lat/lon) were tested on synthetic data. The Sentinel-2
download from Planetary Computer was NOT run from my sandbox.
"""
import argparse, base64, csv, io, json
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import validate_fire as v

BANDS = ("B04", "B03", "B02", "B8A", "B12")

def s2_mosaic(g, bbox, start, end, bands, max_cloud=40):
    """Build cloud-masked Sentinel-2 band mosaics on the target grid."""
    import planetary_computer
    import pystac_client

    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    items = list(cat.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{start:%Y-%m-%d}/{end:%Y-%m-%d}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).items())
    items.sort(key=lambda it: it.properties["eo:cloud_cover"])

    H, W = g["shape"]
    mosaic = {band: np.full((H, W), np.nan, "float32") for band in bands}
    used = []
    for item in items:
        if all(np.isfinite(mosaic[band]).mean() > 0.97 for band in bands):
            break
        missing = [band for band in bands if band not in item.assets]
        if missing or "SCL" not in item.assets:
            continue

        arrays = {
            band: (v.reproject_band(item.assets[band].href, g) - 1000) / 10000
            for band in bands
        }
        scl = v.reproject_band(item.assets["SCL"].href, g, "nearest")
        ok = np.isfinite(scl) & ~np.isin(scl, v.CLOUD_SCL)
        fill = False
        for band, array in arrays.items():
            valid = ok & np.isfinite(array)
            target = ~np.isfinite(mosaic[band]) & valid
            mosaic[band][target] = array[target]
            fill = fill or target.any()
        if fill:
            used.append(f"{item.datetime:%Y-%m-%d} ({item.properties['eo:cloud_cover']:.0f}% cloud)")

    print(
        f"  Sentinel-2 {start:%d %b}-{end:%d %b}: {len(used)} scene(s): "
        f"{', '.join(used) or 'NONE'}; "
        f"coverage {np.isfinite(next(iter(mosaic.values()))).mean()*100:.0f}%"
    )
    return mosaic, used

def display_grid(g, factor=2):
    return {**g, "pixel_m": g["pixel_m"] / factor, "shape": [g["shape"][0] * factor, g["shape"][1] * factor]}

def smooth_up(diff, k, factor):
    """Block-average the NISAR diff (kills speckle), then repeat to the display grid."""
    d = v.coarsen(diff, k) if k > 1 else diff
    d = np.repeat(np.repeat(d, k if k > 1 else 1, 0), k if k > 1 else 1, 1)
    d = np.repeat(np.repeat(d, factor, 0), factor, 1)
    H, W = diff.shape[0] * factor, diff.shape[1] * factor
    out = np.full((H, W), np.nan, "float32"); h, w = min(H, d.shape[0]), min(W, d.shape[1]); out[:h, :w] = d[:h, :w]
    return out

def stretch(rgb, lo=None, hi=None, gamma=0.85):
    if lo is None: lo, hi = np.nanpercentile(rgb, [2, 98])
    return np.clip((rgb - lo) / (hi - lo + 1e-9), 0, 1) ** gamma, lo, hi

def composites(m_pre, m_post):
    tc = lambda m: np.dstack([m["B04"], m["B03"], m["B02"]])
    sw = lambda m: np.dstack([m["B12"], m["B8A"], m["B04"]])
    out = {}
    for name, f in (("tc", tc), ("sw", sw)):
        pre, lo, hi = stretch(f(m_pre)); post, _, _ = stretch(f(m_post), lo, hi)      # SAME stretch before/after
        out[name + "_pre"], out[name + "_post"] = pre, post
    return out

def to_wgs84(arrs, g):
    """Reproject layers from the UTM display grid to lat/lon. Returns (list of arrays, [south, west, north, east])."""
    from rasterio.crs import CRS
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    H, W = arrs[0].shape; crs = CRS.from_epsg(g["epsg"])
    left, top = g["x_left"], g["y_top"]; right, bottom = left + W * g["pixel_m"], top - H * g["pixel_m"]
    dtr, dw, dh = calculate_default_transform(crs, "EPSG:4326", W, H, left=left, bottom=bottom, right=right, top=top)
    outs = []
    for a in arrs:
        o = np.full((dh, dw), np.nan, "float32")
        reproject(a.astype("float32"), o, src_transform=v.transform_of(g), src_crs=crs, src_nodata=np.nan,
                  dst_transform=dtr, dst_crs="EPSG:4326", dst_nodata=np.nan, resampling=Resampling.nearest)
        outs.append(o)
    return outs, [dtr.f + dh * dtr.e, dtr.c, dtr.f, dtr.c + dw * dtr.a]

def png_b64(rgba):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    buf = io.BytesIO(); plt.imsave(buf, np.clip(rgba, 0, 1), format="png"); return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def rgba_from_rgb(rgb3):                         # rgb3: three warped float bands
    rgb = np.dstack(rgb3); a = np.isfinite(rgb).all(2).astype("float32")
    return np.dstack([np.nan_to_num(rgb), a])

def rgba_mask(mask, color=(1, 0, 0), alpha=0.6):
    out = np.zeros(mask.shape + (4,), "float32"); out[..., :3] = color; out[..., 3] = np.where(mask > 0.5, alpha, 0); return out

def read_firms(path, d0, d1, bbox):
    pts = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            d = datetime.strptime(r["acq_date"], "%Y-%m-%d"); lat, lon = float(r["latitude"]), float(r["longitude"])
            if d0 <= d <= d1 and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]: pts.append((lat, lon))
    return pts

HTML = """<!doctype html><html><head><meta charset="utf-8"><title>NISAR location check</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#map{height:100%;margin:0}.ctl{position:absolute;z-index:1000;bottom:24px;left:12px;background:#fff;padding:6px 10px;border-radius:6px;font:13px sans-serif}</style></head>
<body><div id="map"></div><div class="ctl">Overlay opacity <input id="op" type="range" min="0" max="1" step="0.05" value="0.85"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const B=__BOUNDS__, BBOX=__BBOX__, imgs=__IMGS__, ORDER=__ORDER__, DEFAULT=__DEFAULT__, FIRMS=__FIRMS__;
const sat=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Tiles &copy; Esri'});
const osm=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'});
const map=L.map('map',{layers:[sat]}).fitBounds(B);
const over={}; ORDER.forEach((k,i)=>{over[k]=L.imageOverlay(imgs[k],B,{opacity:0.85,zIndex:10+i}); if(DEFAULT.includes(k)) over[k].addTo(map);});
if(FIRMS.length){const g=L.layerGroup(FIRMS.map(p=>L.circleMarker(p,{radius:4,color:'#000',weight:1,fillColor:'#ffd400',fillOpacity:1}))); over['FIRMS hotspots']=g; g.addTo(map);}
L.control.layers({'Esri satellite (basemap)':sat,'OpenStreetMap (names/roads)':osm},over,{collapsed:false}).addTo(map);
L.rectangle([[BBOX[1],BBOX[0]],[BBOX[3],BBOX[2]]],{color:'#ffff00',weight:1,fill:false}).addTo(map);
document.getElementById('op').oninput=e=>ORDER.forEach(k=>over[k].setOpacity(+e.target.value));
map.on('click',e=>L.popup().setLatLng(e.latlng).setContent(e.latlng.lat.toFixed(5)+', '+e.latlng.lng.toFixed(5)).openOn(map));
</script></body></html>"""

def figure(path, comp, mask_up, pts_rc, labels):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(15, 11.5)); ax = ax.ravel()
    ax[0].imshow(comp["tc_pre"]); ax[0].set_title(f"Sentinel-2 true colour BEFORE\n{labels[0]}")
    ax[1].imshow(comp["tc_post"]); ax[1].set_title(f"Sentinel-2 true colour AFTER\n{labels[1]}")
    ax[2].imshow(comp["sw_post"]); ax[2].set_title("Sentinel-2 SWIR composite AFTER (burn scar = dark red/brown)")
    ax[3].imshow(comp["tc_post"]); ax[3].set_title("AFTER + NISAR HV decrease (red outline) + FIRMS (yellow)")
    m = np.nan_to_num(mask_up) > 0.5
    for a in (ax[2], ax[3]):
        if m.any(): a.contour(m.astype(float), levels=[0.5], colors="red", linewidths=0.8)
    if pts_rc:
        r, c = np.array(pts_rc).T; ax[3].scatter(c, r, s=14, c="yellow", edgecolors="k", linewidths=0.4)
    for a in ax: a.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--event", required=True); p.add_argument("--pre", nargs=2); p.add_argument("--post", nargs=2)
    p.add_argument("--thresh", type=float, default=-2.0); p.add_argument("--smooth", type=int, default=3, help="block size to smooth NISAR diff (default 3)")
    p.add_argument("--firms"); A = p.parse_args(); folder = Path(A.event)
    g, diff, meta = v.load(folder); bbox = meta.get("bbox_lonlat")
    if not bbox: raise SystemExit("meta.json with bbox_lonlat missing: rerun nisar_before_after.py")
    g2 = display_grid(g)
    t = lambda s: datetime.fromisoformat(str(s).split("+")[0].strip()); b0, a0 = t(meta["before"]["start"]), t(meta["after"]["start"])
    pre = [datetime.fromisoformat(x) for x in A.pre] if A.pre else [b0 - timedelta(days=15), b0]
    post = [datetime.fromisoformat(x) for x in A.post] if A.post else [a0 - timedelta(days=7), a0 + timedelta(days=20)]
    print("Fetching Sentinel-2 true-colour + SWIR bands (can take a few minutes)...")
    m_pre, used_pre = s2_mosaic(g2, bbox, *pre, BANDS); m_post, used_post = s2_mosaic(g2, bbox, *post, BANDS)
    comp = composites(m_pre, m_post); dsm = smooth_up(diff, A.smooth, 2); mask = (dsm <= A.thresh).astype("float32"); mask[~np.isfinite(dsm)] = np.nan
    firms = read_firms(A.firms, b0, a0, bbox) if A.firms else []
    pts_rc = []
    if firms:
        from pyproj import Transformer
        tr = Transformer.from_crs(4326, g["epsg"], always_xy=True)
        for lat, lon in firms:
            x, y = tr.transform(lon, lat); pts_rc.append(((g2["y_top"] - y) / g2["pixel_m"], (x - g2["x_left"]) / g2["pixel_m"]))
    figure(folder / "SATELLITE_CHECK.png", comp, mask, pts_rc, (", ".join(used_pre[:2]) or "no scene", ", ".join(used_post[:2]) or "no scene"))
    # interactive map layers (warped to lat/lon so they sit exactly on the basemap)
    names = {"Sentinel-2 BEFORE (true colour)": "tc_pre", "Sentinel-2 AFTER (true colour)": "tc_post", "Sentinel-2 AFTER (SWIR burn composite)": "sw_post"}
    flat, order = [], []
    for k in names.values(): flat += [comp[k][..., i] for i in range(3)]
    flat.append(mask); warped, bounds = to_wgs84(flat, g2); imgs = {}
    for n, k in enumerate(names):
        imgs[k] = png_b64(rgba_from_rgb(warped[3 * n:3 * n + 3])); order.append(k)
    imgs["NISAR HV decrease (red)"] = png_b64(rgba_mask(np.nan_to_num(warped[-1]))); order.append("NISAR HV decrease (red)")
    html = (HTML.replace("__BOUNDS__", json.dumps([[bounds[0], bounds[1]], [bounds[2], bounds[3]]])).replace("__BBOX__", json.dumps(bbox))
            .replace("__IMGS__", json.dumps(imgs)).replace("__ORDER__", json.dumps(order))
            .replace("__DEFAULT__", json.dumps(["Sentinel-2 AFTER (true colour)", "NISAR HV decrease (red)"])).replace("__FIRMS__", json.dumps(firms)))
    (folder / "map.html").write_text(html, encoding="utf-8")
    if np.nansum(mask) > 0:                                    # where is the detected area?
        from pyproj import Transformer
        rr, cc = np.where(np.nan_to_num(mask) > 0.5); x = g2["x_left"] + cc.mean() * g2["pixel_m"]; y = g2["y_top"] - rr.mean() * g2["pixel_m"]
        lon, lat = Transformer.from_crs(g["epsg"], 4326, always_xy=True).transform(x, y)
        print(f"NISAR decrease centre of mass: {lat:.4f}, {lon:.4f}   (paste into Google Maps)")
    print(f"Wrote {folder/'SATELLITE_CHECK.png'} and {folder/'map.html'}  -> open map.html in your browser")

if __name__ == "__main__":
    main()