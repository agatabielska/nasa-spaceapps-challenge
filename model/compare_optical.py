"""
compare_optical.py -- "what an optical satellite saw vs what NISAR saw" picture pairs.

  uv run --group validate python compare_optical.py --out ~/Downloads/nisar-vs-sentinel

For each entry in PAIRS: the Sentinel-2 true-colour scene(s) of one date (Microsoft Planetary Computer, clouds and
smoke left in on purpose) are put on the grid of a cached NISAR window, so both pictures show exactly the same
area. Writes <id>_sentinel2.jpg, <id>_nisar.jpg (same size, usable in a slider) and <id>_porownanie.jpg (side by side).
"""
import argparse, json, warnings
from pathlib import Path
import numpy as np
import nisar_io as nio, change_methods as cm

HERE = Path(__file__).parent
PAIRS = [
    dict(id="1_nepal_chmury", case="nepal_flood", nisar="gcov_after", s2_date="2026-09-01",
         title="Nepal, powódź po oberwaniu lodowca", s2_label="Sentinel-2 (optyczny)  ·  1 września 2026, 04:57 UTC",
         nisar_label="NISAR (radar, pasmo L)  ·  31 sierpnia 2026, 23:39 UTC",
         note="Ten sam obszar, 5 godzin różnicy, 5 dni po katastrofie. Chmury zakrywają 81% obszaru, w tym miejsce oberwania; radar widzi wszystko.", mask=True),
    dict(id="2_etna_chmura", crop_left=0.36, case="etna", nisar="gcov_0816", s2_date="2026-08-16",
         title="Etna, erupcja w sierpniu 2026", s2_label="Sentinel-2 (optyczny)  ·  16 sierpnia 2026, 09:50 UTC",
         nisar_label="NISAR (radar, pasmo L)  ·  16 sierpnia 2026, 04:08 UTC",
         note="Ten sam dzień, 6 godzin różnicy. Chmury zakrywają szczyt i świeżą lawę; radar (przed świtem) pokazuje szczyt i jęzory lawy.", mask=False),
    dict(id="3_hiszpania_dym", case="spain_fire_v2", nisar="gcov_during_0726", s2_date="2026-07-26",
         title="Hiszpania, pożar lasu koło Ávili (w trakcie)", s2_label="Sentinel-2 (optyczny)  ·  26 lipca 2026, 11:07 UTC",
         nisar_label="NISAR (radar, pasmo L)  ·  26 lipca 2026, 05:24 UTC (o świcie)",
         note="Ten sam dzień. Dym zasłania aktywny front ognia (prawy dolny róg); radar widzi teren pod nim. Bliznę po pożarze lepiej widać w optyce.", mask=False),
]


def sentinel_rgb(case, grid, date):
    import rasterio, pystac_client, planetary_computer
    from rasterio.warp import reproject, Resampling
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    x, y, px = grid["x"], grid["y"], float(grid["pixel_m"])
    tr = from_origin(x[0] - px / 2, y[0] + px / 2, px, px)
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=case["bbox"], datetime=date).items())
    out = np.zeros((len(y), len(x), 3), "uint8")
    for it in sorted(items, key=lambda i: i.id):
        rgb = np.zeros((3, len(y), len(x)), "uint8")
        with rasterio.open(it.assets["visual"].href) as src:
            for i in range(3):
                reproject(rasterio.band(src, i + 1), rgb[i], dst_transform=tr, dst_crs=CRS.from_epsg(int(grid["epsg"])), resampling=Resampling.bilinear)
        rgb = np.moveaxis(rgb, 0, -1); fill = (out.sum(2) == 0) & (rgb.sum(2) > 0); out[fill] = rgb[fill]
    return out, [it.id for it in items]


def nisar_rgb(d):
    hh, hv = cm.to_db(cm.nanfilter(d["HHHH"], 3)), cm.to_db(cm.nanfilter(d["HVHV"], 3))
    s = lambda a, lo, hi: np.clip((np.nan_to_num(a, nan=lo) - lo) / (hi - lo), 0, 1)
    lh, lv = np.nanpercentile(hh, [2, 98]), np.nanpercentile(hv, [2, 98])
    return (np.dstack([s(hh, *lh), s(hv, *lv), s(hh - hv, 2, 14)]) * 255).astype("uint8")


def build(p, cases, data, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    case = cases[p["case"]]; d = nio.cached(data / p["case"] / f"{p['nisar']}.npz", None)
    s2, ids = sentinel_rgb(case, d, p["s2_date"]); nis = nisar_rgb(d)
    h, w = min(s2.shape[0], nis.shape[0]), min(s2.shape[1], nis.shape[1]); c0 = int(w * p.get("crop_left", 0))   # cut the part outside the Sentinel-2 swath
    s2, nis = s2[:h, c0:w], nis[:h, c0:w]; w -= c0
    plt.imsave(out / f"{p['id']}_sentinel2.jpg", s2, pil_kwargs={"quality": 90}); plt.imsave(out / f"{p['id']}_nisar.jpg", nis, pil_kwargs={"quality": 90})
    overlay = None
    lay = data / p["case"] / "layers.npz"
    if p.get("mask") and lay.exists():
        z = np.load(lay); m = z["mask_coherence"].astype(bool)[:h, c0:c0 + w] | z["mask_backscatter"].astype(bool)[:h, c0:c0 + w]
        overlay = np.zeros((h, w, 4)); overlay[m] = (1.0, 0.1, 0.6, 1.0)
    bg = "#0b1420"; fig, ax = plt.subplots(1, 2, figsize=(16, 8 * h / w + 1.9), facecolor=bg)
    for a, img, lab, col in ((ax[0], s2, p["s2_label"], "#ffb37a"), (ax[1], nis, p["nisar_label"], "#7fe0d8")):
        a.imshow(img); a.set_title(lab, color=col, fontsize=15, fontweight="bold", pad=10); a.axis("off")
    if overlay is not None: ax[1].imshow(overlay)
    fig.suptitle(p["title"], color="white", fontsize=24, fontweight="bold", y=0.985)
    extra = "   Różowy: zmiany wykryte przez NISAR." if overlay is not None else ""
    fig.text(0.5, 0.025, p["note"] + extra, color="#d8dee8", fontsize=13.5, ha="center")
    fig.text(0.995, 0.004, "Dane: Copernicus Sentinel-2 (ESA), NISAR L2 GCOV (NASA/ISRO, ASF DAAC)", color="#7a8798", fontsize=8.5, ha="right")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.88, bottom=0.07, wspace=0.02)
    fig.savefig(out / f"{p['id']}_porownanie.jpg", dpi=130, facecolor=bg, pil_kwargs={"quality": 90}); plt.close(fig)
    cloud = float((s2.min(2) > 200).mean())
    print(f"[{p['id']}] {len(ids)} Sentinel-2 scene(s), very bright (cloud/smoke) pixels: {cloud*100:.0f}% of the area")
    return {"id": p["id"], "title": p["title"], "sentinel2_scenes": ids, "nisar_granule": case.get(p["nisar"], p["nisar"]),
            "bright_cloud_fraction": round(cloud, 3), "note": p["note"]}


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--only")
    ap.add_argument("--data", default=str(HERE / "data")); A = ap.parse_args()
    out = Path(A.out).expanduser(); out.mkdir(parents=True, exist_ok=True)
    cases = json.loads((HERE / "cases.json").read_text()); res = []
    for p in PAIRS:
        if A.only and A.only not in p["id"]: continue
        if not (Path(A.data) / p["case"] / f"{p['nisar']}.npz").exists(): print(f"[{p['id']}] NISAR window missing, skipped"); continue
        res.append(build(p, cases, Path(A.data), out))
    (out / "zrodla.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
