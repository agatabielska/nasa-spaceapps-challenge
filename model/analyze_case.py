"""
analyze_case.py -- turn the cached NISAR windows of one case into change masks, pictures and numbers.

  uv run python fetch_case.py --only nepal_flood      # once, needs the Earthdata token
  uv run python analyze_case.py --only nepal_flood    # offline, a few seconds

What is computed depends on the data a case has (cases.json) and on its "kind":

  GCOV pair  -> BACKSCATTER method : log-ratio of HH and HV, robust z-score, threshold, clean-up
  GUNW pair  -> COHERENCE method   : coherence loss versus a quiet reference pair of the same track
             -> DISPLACEMENT       : unwrapped phase -> line-of-sight ground motion in cm

  flood      backscatter change in BOTH directions (water/mud darkens, debris and wet soil brighten) + coherence
  fire       backscatter DECREASE, HV weighted higher (canopy loss removes volume scattering)
  volcano    backscatter both directions + coherence (new lava destroys it) + displacement (inflation/deflation)
  earthquake displacement + coherence loss (damage proxy); backscatter is optional and usually shows little

Outputs in output/<case>/ : BEFORE.jpg AFTER.jpg CHANGE_overlay.jpg SUMMARY.jpg, map layers mask_*.png (transparent, with
bounds.json for MapLibre), stats.json. Numeric layers go to data/<case>/layers.npz (large, git-ignored).
"""
import argparse, json
from pathlib import Path
import numpy as np
import nisar_io as nio
import change_methods as cm

HERE = Path(__file__).parent
KIND = {   # direction of backscatter change, polarisation weights (HH, HV), thresholds
    "flood":      dict(direction="both",     w=(1.0, 1.0), z=3.5, coh_drop=0.25),
    # fire settings were MEASURED against Sentinel-2 dNBR (validate_case.py, Spain): HV alone with a strong
    # 15x15 filter is best (IoU 0.30); adding HH lowers it (0.25-0.27); the first version scored 0.15.
    "fire":       dict(direction="decrease", w=(0.0, 1.0), z=1.8, coh_drop=0.25, win=15, texture=None),
    "volcano":    dict(direction="both",     w=(1.0, 1.0), z=3.5, coh_drop=0.30),
    "earthquake": dict(direction="both",     w=(1.0, 1.0), z=4.0, coh_drop=0.25),
}
COL = {"both": (0.85, 0.10, 0.75), "backscatter": (1.0, 0.55, 0.0), "coherence": (0.0, 0.75, 1.0)}


def load(folder, key):
    p = folder / f"{key}.npz"
    return nio.cached(p, None) if p.exists() else None


def corners_lonlat(x, y, epsg):
    from pyproj import Transformer
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    dx, dy = abs(x[1] - x[0]) / 2, abs(y[1] - y[0]) / 2
    pts = [(x[0] - dx, y[0] + dy), (x[-1] + dx, y[0] + dy), (x[-1] + dx, y[-1] - dy), (x[0] - dx, y[-1] - dy)]
    return [list(map(float, tr.transform(*p))) for p in pts]          # TL, TR, BR, BL  (MapLibre image source order)


def false_colour(d, lim):
    """R = HH, G = HV, B = HH/HV ratio: forest looks green, bare ground/urban magenta, water dark."""
    hh, hv = cm.to_db(cm.nanfilter(d["HHHH"], 3)), cm.to_db(cm.nanfilter(d["HVHV"], 3))
    s = lambda a, lo, hi: np.clip((np.nan_to_num(a, nan=lo) - lo) / (hi - lo), 0, 1)
    return np.dstack([s(hh, *lim["hh"]), s(hv, *lim["hv"]), s(hh - hv, 2, 14)])


def save_mask(path, mask, colour):
    import matplotlib.pyplot as plt
    rgba = np.zeros(mask.shape + (4,), "float32"); rgba[mask] = (*colour, 0.8)
    plt.imsave(path, rgba)


def analyze(name, case, data_root, out_root, win=5, min_px=None):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    folder, out = data_root / name, out_root / name; out.mkdir(parents=True, exist_ok=True)
    k = KIND[case["kind"]]
    b, a, g, r = (load(folder, x) for x in ("gcov_before", "gcov_after", "gunw", "gunw_ref"))
    if (b is None or a is None) and g is None:
        print(f"[{name}] no cached data in {folder}: run fetch_case.py --only {name} first"); return None
    stats = {"case": name, "kind": case["kind"], "title": case.get("title"), "event_date": case.get("event_date"),
             "bbox_lonlat": case["bbox"], "methods": {}}
    layers, masks, panels = {}, {}, []
    grid = None

    # ---------------- backscatter (GCOV)
    if b is not None and a is not None:
        shape = tuple(min(s, t) for s, t in zip(b["HHHH"].shape, a["HHHH"].shape))
        for d in (b, a):
            for p in ("HHHH", "HVHV"): d[p] = cm.match(d[p], shape)
        grid = dict(x=b["x"][: shape[1]], y=b["y"][: shape[0]], epsg=int(b["epsg"]), pixel_m=float(b["pixel_m"]))
        win = k.get("win", win)
        score, diffs, rel = cm.backscatter_change(b, a, win=win, direction=k["direction"], weights=k["w"],
                                                  max_texture_db=k.get("texture", 3.5))
        px_km2 = (grid["pixel_m"] / 1000) ** 2
        mp = min_px or int(round(0.02 / px_km2))                      # ignore blobs smaller than 2 ha
        m = cm.clean(np.isfinite(score) & (score >= k["z"]), mp)
        masks["backscatter"] = m; layers.update(score_backscatter=score, diff_hh_db=diffs["HHHH"], diff_hv_db=diffs["HVHV"])
        lim = {"hh": tuple(np.nanpercentile(cm.to_db(b["HHHH"]), [2, 98])), "hv": tuple(np.nanpercentile(cm.to_db(b["HVHV"]), [2, 98]))}
        rgb_b, rgb_a = false_colour(b, lim), false_colour(a, lim)
        plt.imsave(out / "BEFORE.jpg", rgb_b, pil_kwargs={"quality": 88}); plt.imsave(out / "AFTER.jpg", rgb_a, pil_kwargs={"quality": 88})
        stats["methods"]["backscatter"] = {
            "what": f"log-ratio {'HV' if k['w'][0] == 0 else 'HH+HV'}, {k['direction']} direction, {win}x{win} filter, threshold {k['z']} sigma",
            "area_km2": float(m.sum() * px_km2), "reliable_fraction": float(rel.mean()),
            "mean_change_db_in_mask": {p: float(np.nanmean(diffs[p][m])) if m.any() else None for p in diffs},
            "scene_noise_db": {p: cm.robust_z(diffs[p])[2] for p in diffs}}
        panels += [("Before  (R=HH G=HV B=HH/HV)", rgb_b, {}), ("After", rgb_a, {}),
                   ("HH change (dB)", diffs["HHHH"], dict(cmap="RdBu_r", vmin=-5, vmax=5)),
                   ("HV change (dB)", diffs["HVHV"], dict(cmap="RdBu_r", vmin=-5, vmax=5))]

    # ---------------- coherence + displacement (GUNW)
    if g is not None:
        ce = g["w_coherence"]
        if grid is None:
            grid = dict(x=g["w_x"], y=g["w_y"], epsg=int(g["epsg"]), pixel_m=float(g["w_pixel_m"]))
        tgt = (len(grid["y"]), len(grid["x"]))
        ce = cm.resample_to(ce, tgt)
        px_km2 = (grid["pixel_m"] / 1000) ** 2
        mp = min_px or int(round(0.02 / px_km2))
        if r is not None:
            loss, usable = cm.coherence_loss(ce, cm.resample_to(r["w_coherence"], tgt), win=3)
            m = cm.clean(usable & (loss >= k["coh_drop"]), mp)
            masks["coherence"] = m; layers.update(coherence_loss=loss)
            stats["methods"]["coherence"] = {
                "what": f"coherence drop >= {k['coh_drop']} versus a quiet pair of the same track",
                "area_km2": float(m.sum() * px_km2), "usable_fraction": float(usable.mean()),
                "mean_coherence_event": float(np.nanmean(ce)), "mean_coherence_reference": float(np.nanmean(r["w_coherence"]))}
            panels += [("Coherence, event pair", ce, dict(cmap="viridis", vmin=0, vmax=1)),
                       ("Coherence loss vs quiet pair", loss, dict(cmap="magma", vmin=0, vmax=0.6))]
        else:
            panels += [("Coherence, event pair", ce, dict(cmap="viridis", vmin=0, vmax=1))]
        disp, okd = cm.los_displacement(g)
        disp = cm.detrend_plane(disp)
        layers.update(displacement_cm=disp, coherence_event=ce)
        v = np.abs(disp[np.isfinite(disp)])
        stats["methods"]["displacement"] = {
            "what": "unwrapped phase - ionosphere screen -> line-of-sight cm, plane removed, relative to scene median",
            "valid_fraction": float(okd.mean()), "p99_abs_cm": float(np.percentile(v, 99)) if v.size else None,
            "min_cm": float(np.nanmin(disp)) if v.size else None, "max_cm": float(np.nanmax(disp)) if v.size else None,
            "wavelength_cm": float(g["wavelength_m"]) * 100}
        lim = max(2.0, float(np.percentile(v, 99))) if v.size else 5.0
        panels += [("Line-of-sight displacement (cm)", disp, dict(cmap="RdBu_r", vmin=-lim, vmax=lim)),
                   ("Wrapped phase (1 fringe = %.1f cm)" % (g["wavelength_m"] * 50), g["w_phase"], dict(cmap="hsv", vmin=-np.pi, vmax=np.pi))]

    # ---------------- agreement of the two independent methods
    base = (np.dstack([cm.to_db(cm.nanfilter(a["HHHH"], 3))] * 3) if a is not None else np.dstack([ce] * 3))
    if a is not None:
        lo, hi = np.nanpercentile(base[..., 0], [2, 98]); base = np.clip((np.nan_to_num(base, nan=lo) - lo) / (hi - lo), 0, 1)
    over = 0.75 * base
    if "backscatter" in masks and "coherence" in masks:
        mb, mc = masks["backscatter"], masks["coherence"]
        cls = {"both": mb & mc, "backscatter": mb & ~mc, "coherence": mc & ~mb}
        inter, union = (mb & mc).sum(), (mb | mc).sum()
        stats["agreement"] = {"iou_backscatter_vs_coherence": float(inter / union) if union else None,
                              **{f"area_{n}_km2": float(v.sum() * px_km2) for n, v in cls.items()}}
        masks["high_confidence"] = cls["both"]
    else:
        cls = {n: v for n, v in masks.items()}
    for n, v in cls.items(): over[v] = COL.get(n, COL["both"])
    plt.imsave(out / "CHANGE_overlay.jpg", over, pil_kwargs={"quality": 90})
    panels.append(("Detected change: " + ", ".join(f"{n}={c}" for n, c in
                   zip(cls, ("magenta", "orange", "cyan")[: len(cls)])) if len(cls) > 1 else "Detected change", over, {}))

    # ---------------- files for the map + numbers
    for n, v in masks.items(): save_mask(out / f"mask_{n}.png", v, COL.get(n, COL["both"]))
    (out / "bounds.json").write_text(json.dumps({"corners_lonlat_TL_TR_BR_BL": corners_lonlat(grid["x"], grid["y"], grid["epsg"]),
                                                 "epsg": grid["epsg"], "pixel_m": grid["pixel_m"], "shape": list(over.shape[:2])}))
    np.savez_compressed(folder / "layers.npz", x=grid["x"], y=grid["y"], epsg=grid["epsg"],
                        **{n: v.astype("float32") for n, v in layers.items()}, **{"mask_" + n: v for n, v in masks.items()})
    stats["granules"] = {x: case[x] for x in ("gcov_before", "gcov_after", "gunw", "gunw_ref") if case.get(x)}
    (out / "stats.json").write_text(json.dumps(stats, indent=2))

    n = len(panels); cols = 3 if n > 4 else 2; rows = -(-n // cols)
    fig, ax = plt.subplots(rows, cols, figsize=(6.2 * cols, 6.2 * rows * over.shape[0] / over.shape[1] + 0.6 * rows))
    for axi, (t, img, kw) in zip(np.ravel(ax), panels):
        im = axi.imshow(img, **kw); axi.set_title(t, fontsize=11)
        if kw: fig.colorbar(im, ax=axi, fraction=0.035, pad=0.02)
    for axi in np.ravel(ax): axi.axis("off")
    fig.suptitle(f"{case.get('title', name)}  |  event {case.get('event_date')}", fontsize=14)
    fig.tight_layout(); fig.savefig(out / "SUMMARY.jpg", dpi=100, pil_kwargs={"quality": 88}); plt.close(fig)
    print(json.dumps({k2: v for k2, v in stats.items() if k2 in ("case", "methods", "agreement")}, indent=1))
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output"))
    p.add_argument("--win", type=int, default=5, help="speckle filter window in pixels")
    A = p.parse_args()
    for n, c in json.loads(Path(A.cases).read_text()).items():
        if A.only and n != A.only: continue
        analyze(n, c, Path(A.data), Path(A.out), A.win)
