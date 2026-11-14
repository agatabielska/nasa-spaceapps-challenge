"""
detect_burn.py -- region-based burn detector for the NISAR change map.

Why: a per-pixel "diff <= -2 dB" rule is dominated by speckle (std ~1.2 dB at 40 m) while the real
burn signal is only ~-0.6 dB. Averaging over ~800 m and using a lower threshold works far better.

Steps
  1. smooth   NaN-aware box average of diff_db.npy over --smooth pixels (default 20 = 800 m at 40 m/px)
  2. threshold  smoothed diff <= --thresh dB (default -0.5)
  3. clean    fill holes, drop connected blobs smaller than --min-km2
  4. report   one row per region (area, mean dB, centre lat/lon) + total burned-area estimate
  5. score    (optional) against Sentinel-2 dNBR if dnbr.npy is present (saved by validate_fire.py)

Writes into the event folder:
  burn_mask.npy    uint8 mask on the NISAR grid (1 = detected burn region)
  regions.json     per-region stats + parameters used
  DETECTION.png    smoothed diff, detected regions, and dNBR comparison (if available)

  uv run python detect_burn.py --event output/spain_fire
  uv run python detect_burn.py --event output/spain_fire --tune        # sweep smoothing x threshold vs dNBR
  uv run python detect_burn.py --event output/spain_fire --smooth 10 --thresh -0.8 --min-km2 0.5

STATUS: tested on the Spain diff_db.npy / dnbr.npy. Thresholds were tuned on that same event, so check
them on another fire before trusting the exact numbers.
"""
import argparse, json
from pathlib import Path
import numpy as np


# ---------------------------------------------------------------- core steps
def smooth(d, k):
    """NaN-aware box mean. Pixels with <50% valid neighbours, or invalid themselves, stay NaN."""
    from scipy.ndimage import uniform_filter
    ok = np.isfinite(d)
    num = uniform_filter(np.where(ok, d, 0.0).astype("float64"), size=k, mode="constant")
    den = uniform_filter(ok.astype("float64"), size=k, mode="constant")
    out = np.full(d.shape, np.nan, "float32")
    good = ok & (den >= 0.5)
    out[good] = num[good] / den[good]
    return out


def detect(d, k, thresh, min_km2, pixel_m):
    """Returns (smoothed diff, labelled regions array, number of regions). Regions sorted by label only."""
    from scipy import ndimage as ndi
    sm = smooth(d, k)
    raw = np.isfinite(sm) & (np.nan_to_num(sm, nan=0.0) <= thresh)
    raw = ndi.binary_fill_holes(raw)
    lab, n = ndi.label(raw, structure=np.ones((3, 3)))            # 8-connected
    if n:
        min_px = max(1, int(round(min_km2 * 1e6 / pixel_m ** 2)))
        sizes = ndi.sum(raw, lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool); keep[1:] = sizes >= min_px
        lab = np.where(keep[lab], lab, 0)
        lab, n = ndi.label(lab > 0, structure=np.ones((3, 3)))
    return sm, lab, n


def region_table(sm, lab, n, g):
    from scipy import ndimage as ndi
    from pyproj import Transformer
    if n == 0: return []
    px_km2 = (g["pixel_m"] / 1000.0) ** 2
    idx = np.arange(1, n + 1)
    areas = ndi.sum(np.ones_like(sm), lab, idx) * px_km2
    means = ndi.mean(np.nan_to_num(sm), lab, idx)
    mins = ndi.minimum(np.nan_to_num(sm, nan=0.0), lab, idx)
    cms = ndi.center_of_mass(np.ones_like(sm), lab, idx)
    tr = Transformer.from_crs(g["epsg"], 4326, always_xy=True)
    rows = []
    for i, (r, c) in enumerate(cms):
        lon, lat = tr.transform(g["x_left"] + (c + 0.5) * g["pixel_m"], g["y_top"] - (r + 0.5) * g["pixel_m"])
        rows.append({"id": int(idx[i]), "area_km2": round(float(areas[i]), 2), "mean_smoothed_dB": round(float(means[i]), 2),
                     "min_smoothed_dB": round(float(mins[i]), 2), "lat": round(float(lat), 4), "lon": round(float(lon), 4)})
    return sorted(rows, key=lambda x: -x["area_km2"])


def score(pred, dnbr, burn_thr, sm_label=None):
    """Pixel-wise agreement with the optical burn map (valid pixels only)."""
    ok = np.isfinite(dnbr) & np.isfinite(pred.astype("float32"))
    burn = dnbr > burn_thr
    p, b, o = pred[ok], burn[ok], ok
    tp = int((p & b).sum()); fp = int((p & ~b).sum()); fn = int((~p & b).sum())
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    return {"precision": prec, "recall": rec, "F1": 2 * prec * rec / max(prec + rec, 1e-9),
            "IoU": tp / max(tp + fp + fn, 1), "burned_share_by_dNBR": float(b.mean()), "detected_share": float(p.mean())}


def pretty(m):
    return "  ".join(f"{k}={v:.2f}" for k, v in m.items())


# ---------------------------------------------------------------- figure
def figure(path, sm, mask, dnbr, burn_thr, pts=None, vlim=2.0):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    panels = 3 if dnbr is not None else 2
    fig, ax = plt.subplots(1, panels, figsize=(6.5 * panels, 5.6))
    im = ax[0].imshow(sm, cmap="RdBu_r", vmin=-vlim, vmax=vlim); ax[0].set_title("Smoothed NISAR change (dB)\nblue = decrease")
    plt.colorbar(im, ax=ax[0], fraction=.046)
    ax[1].imshow(sm, cmap="gray_r", vmin=-vlim, vmax=vlim, alpha=0.6)
    ov = np.zeros(mask.shape + (4,), "float32"); ov[mask > 0] = (1, 0, 0, 0.55); ax[1].imshow(ov)
    ax[1].set_title("Detected burn regions (red)")
    if dnbr is not None:
        ok = np.isfinite(dnbr); pred = mask > 0; burn = dnbr > burn_thr
        ag = np.full(mask.shape + (3,), 0.92)
        ag[ok & pred & burn] = (0.1, 0.7, 0.2); ag[ok & pred & ~burn] = (0.9, 0.2, 0.2)
        ag[ok & ~pred & burn] = (0.2, 0.4, 0.9); ag[~ok] = 1
        ax[2].imshow(ag); ax[2].set_title(f"vs Sentinel-2 dNBR > {burn_thr}\ngreen=both  red=NISAR only  blue=optical only")
    for a in ax: a.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--event", required=True, help="folder with diff_db.npy + grid.json, e.g. output/spain_fire")
    p.add_argument("--smooth", type=int, default=20, help="box size in pixels (default 20 = 800 m at 40 m/px)")
    p.add_argument("--thresh", type=float, default=-0.5, help="smoothed dB decrease that counts as burn (default -0.5)")
    p.add_argument("--min-km2", type=float, default=1.0, help="drop regions smaller than this (default 1 km2)")
    p.add_argument("--dnbr", type=float, default=0.27, help="dNBR burn threshold used for scoring (default 0.27)")
    p.add_argument("--tune", action="store_true", help="sweep smoothing x threshold against dnbr.npy and print the best")
    A = p.parse_args(); folder = Path(A.event)

    g = json.loads((folder / "grid.json").read_text()); d = np.load(folder / "diff_db.npy")
    dn_path = folder / "dnbr.npy"; dnbr = np.load(dn_path) if dn_path.exists() else None
    if dnbr is not None and dnbr.shape != d.shape:
        print(f"WARNING: dnbr.npy shape {dnbr.shape} != diff {d.shape}; ignoring dNBR"); dnbr = None
    if dnbr is None: print("(no dnbr.npy found: skipping scoring; run validate_fire.py to create it)")

    smooth_k, thresh = A.smooth, A.thresh
    if A.tune:
        if dnbr is None: raise SystemExit("--tune needs dnbr.npy in the event folder")
        res = []
        for k in (5, 10, 15, 20, 30, 40):
            for th in (-0.3, -0.4, -0.5, -0.6, -0.8, -1.0, -1.5):
                sm, lab, n = detect(d, k, th, A.min_km2, g["pixel_m"])
                s = score(lab > 0, dnbr, A.dnbr); res.append((s["F1"], k, th, s))
        res.sort(key=lambda r: -r[0])
        print(f"\nTop settings vs dNBR>{A.dnbr} (min region {A.min_km2} km2). NOTE: tuned on this event: in-sample.")
        for f, k, th, s in res[:6]: print(f"  smooth={k:>2} ({k*g['pixel_m']:.0f} m) thresh={th:>5}  {pretty(s)}")
        smooth_k, thresh = res[0][1], res[0][2]
        print(f"\nUsing best: smooth={smooth_k}, thresh={thresh}\n")

    sm, lab, n = detect(d, smooth_k, thresh, A.min_km2, g["pixel_m"])
    mask = (lab > 0).astype("uint8")
    rows = region_table(sm, lab, n, g)
    total = float(mask.sum() * (g["pixel_m"] / 1000.0) ** 2)
    out = {"params": {"smooth_px": smooth_k, "smooth_m": smooth_k * g["pixel_m"], "thresh_dB": thresh, "min_km2": A.min_km2},
           "n_regions": n, "total_area_km2": round(total, 2), "regions": rows}
    if dnbr is not None:
        out["score_vs_dNBR"] = {f"dNBR>{A.dnbr}": score(mask > 0, dnbr, A.dnbr)}
        for t in (0.44, 0.66):
            if t != A.dnbr: out["score_vs_dNBR"][f"dNBR>{t}"] = score(mask > 0, dnbr, t)
    np.save(folder / "burn_mask.npy", mask)
    (folder / "regions.json").write_text(json.dumps(out, indent=2))
    figure(folder / "DETECTION.png", sm, mask, dnbr, A.dnbr)

    print(f"Smoothing {smooth_k} px ({smooth_k*g['pixel_m']:.0f} m), threshold {thresh} dB, min region {A.min_km2} km2")
    print(f"{n} region(s), total {total:.1f} km2 ({mask.mean()*100:.1f}% of the box)")
    for r in rows[:8]:
        print(f"  #{r['id']}: {r['area_km2']:.1f} km2, mean {r['mean_smoothed_dB']:+.2f} dB, centre {r['lat']}, {r['lon']}")
    if len(rows) > 8: print(f"  ... {len(rows)-8} smaller region(s) in regions.json")
    for k, v in out.get("score_vs_dNBR", {}).items(): print(f"  vs {k}: {pretty(v)}")
    print(f"Wrote {folder/'burn_mask.npy'}, {folder/'regions.json'}, {folder/'DETECTION.png'}")


if __name__ == "__main__":
    main()