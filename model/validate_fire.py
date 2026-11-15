"""
validate_fire.py -- ground-truth check of the NISAR change map for a wildfire.

Compares  output/<event>/diff_db.npy  (NISAR HV after-minus-before, from nisar_before_after.py)
with      Sentinel-2 dNBR burn severity (optical, independent sensor, Microsoft Planetary Computer)
optionally with NASA FIRMS fire hotspots (CSV you download by hand).

  uv sync --group validate
  uv run --group validate python validate_fire.py --event output/spain_fire
  uv run --group validate python validate_fire.py --event output/spain_fire --firms firms_viirs.csv

STATUS: metrics, plotting and the reprojection step were tested on synthetic data. The Planetary Computer
search/download was NOT run (no access from my sandbox) -- if it errors, send me the message.
"""
import argparse, csv, json, warnings
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

CLOUD_SCL = (0, 1, 8, 9, 10, 11)      # no data, saturated, cloud medium/high, thin cirrus, snow  (burn scars kept)

# ---------------------------------------------------------------- grid helpers
def load(folder):
    g = json.loads((folder / "grid.json").read_text()); d = np.load(folder / "diff_db.npy")
    return g, d, json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}

def transform_of(g):
    from rasterio.transform import from_origin
    return from_origin(g["x_left"], g["y_top"], g["pixel_m"], g["pixel_m"])

def reproject_band(href, g, resampling="average", dtype="float32"):
    """Read one raster (path or URL) onto the NISAR grid."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import reproject, Resampling
    H, W = g["shape"]; out = np.full((H, W), np.nan, dtype)
    with rasterio.open(href) as src:
        reproject(rasterio.band(src, 1), out, src_transform=src.transform, src_crs=src.crs,
                  src_nodata=0, dst_transform=transform_of(g), dst_crs=CRS.from_epsg(g["epsg"]),
                  dst_nodata=np.nan, init_dest_nodata=True, resampling=getattr(Resampling, resampling))
    return out

# ---------------------------------------------------------------- Sentinel-2 NBR mosaic
def s2_nbr(g, bbox, start, end, max_cloud=40):
    import pystac_client, planetary_computer
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{start:%Y-%m-%d}/{end:%Y-%m-%d}",
                            query={"eo:cloud_cover": {"lt": max_cloud}}).items())
    items.sort(key=lambda it: it.properties["eo:cloud_cover"])
    H, W = g["shape"]; nbr = np.full((H, W), np.nan, "float32"); used = []
    for it in items:
        if np.isfinite(nbr).mean() > 0.97: break
        b8a = (reproject_band(it.assets["B8A"].href, g) - 1000) / 10000      # L2A offset (baseline >= 04.00)
        b12 = (reproject_band(it.assets["B12"].href, g) - 1000) / 10000
        scl = reproject_band(it.assets["SCL"].href, g, "nearest")
        ok = np.isfinite(b8a) & np.isfinite(b12) & ~np.isin(scl, CLOUD_SCL) & ((b8a + b12) > 0)
        val = np.where(ok, (b8a - b12) / (b8a + b12 + 1e-9), np.nan)
        fill = ~np.isfinite(nbr) & np.isfinite(val); nbr[fill] = val[fill]
        if fill.any(): used.append(f"{it.datetime:%Y-%m-%d} ({it.properties['eo:cloud_cover']:.0f}% cloud)")
    print(f"  Sentinel-2 {start:%d %b}-{end:%d %b}: {len(used)} scene(s): {', '.join(used) or 'NONE'}; "
          f"coverage {np.isfinite(nbr).mean()*100:.0f}%")
    return nbr

# ---------------------------------------------------------------- metrics (pure numpy)
def coarsen(a, k):
    if k <= 1: return a
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3))

def ranks(v):
    o = np.argsort(v, kind="stable"); r = np.empty(len(v)); r[o] = np.arange(1, len(v) + 1); return r

def metrics(diff, dnbr, thresh_db=-2.0, dnbr_burn=0.27, seed=0):
    ok = np.isfinite(diff) & np.isfinite(dnbr)
    if ok.sum() < 100: return {"error": "too few pixels where both datasets are valid"}
    x, y = diff[ok], dnbr[ok]; burn = y > dnbr_burn; pred = x <= thresh_db
    tp = int((pred & burn).sum()); fp = int((pred & ~burn).sum()); fn = int((~pred & burn).sum()); tn = int((~pred & ~burn).sum())
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    rng = np.random.default_rng(seed); idx = rng.choice(len(x), min(len(x), 300_000), replace=False)
    xs, ys, bs = x[idx], y[idx], burn[idx]
    r = ranks(-xs); npos = bs.sum(); nneg = (~bs).sum()
    auc = float((r[bs].sum() - npos * (npos + 1) / 2) / (npos * nneg)) if npos and nneg else None
    return {"valid_pixels": int(ok.sum()), "burned_share_by_dNBR": float(burn.mean()), "predicted_share_by_NISAR": float(pred.mean()),
            "TP": tp, "FP": fp, "FN": fn, "TN": tn, "precision": prec, "recall": rec,
            "F1": 2 * prec * rec / max(prec + rec, 1e-9), "IoU": tp / max(tp + fp + fn, 1),
            "AUC_(1=perfect,0.5=random)": auc,
            "spearman_diff_vs_dNBR_(negative=good)": float(np.corrcoef(ranks(xs), ranks(ys))[0, 1]),
            "mean_diff_dB_in_burn": float(x[burn].mean()) if burn.any() else None,
            "mean_diff_dB_outside_burn": float(x[~burn].mean())}

def verdict(m):
    if "error" in m: return m["error"]
    a, r = m["AUC_(1=perfect,0.5=random)"], m["spearman_diff_vs_dNBR_(negative=good)"]
    if a is None: return "no burned pixels in the optical map: bbox may not contain the burn, or dNBR threshold too high"
    if a >= 0.75 and r < -0.3: return "STRONG agreement: NISAR HV change tracks the optical burn map."
    if a >= 0.62: return "MODERATE agreement: NISAR sees part of the burn; expect noise and other changes."
    return "WEAK/NO agreement: the red/blue patterns are probably not (only) the fire. Check bbox, polarization, dates."

# ---------------------------------------------------------------- FIRMS hotspots
def firms_hits(csv_path, g, diff, dnbr_burn_mask, d0, d1, thresh_db):
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, g["epsg"], always_xy=True); H, W = diff.shape; pts = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            d = datetime.strptime(row["acq_date"], "%Y-%m-%d")
            if not (d0 <= d <= d1): continue
            x, y = tr.transform(float(row["longitude"]), float(row["latitude"]))
            c, r = int((x - g["x_left"]) // g["pixel_m"]), int((g["y_top"] - y) // g["pixel_m"])
            if 0 <= r < H and 0 <= c < W and np.isfinite(diff[r, c]): pts.append((r, c))
    if not pts: return {"hotspots_in_box": 0}
    rr, cc = np.array(pts).T; pred = diff <= thresh_db; k = 3          # 3-pixel tolerance (~120 m) for FIRMS 375 m pixels
    near = lambda m: float(np.mean([m[max(r-k,0):r+k+1, max(c-k,0):c+k+1].any() for r, c in pts]))
    out = {"hotspots_in_box": len(pts), "share_of_hotspots_near_NISAR_decrease": near(pred),
           "share_of_box_flagged_by_NISAR_(baseline)": float(np.nanmean(pred[np.isfinite(diff)]))}
    if dnbr_burn_mask is not None: out["share_of_hotspots_near_S2_burn"] = near(dnbr_burn_mask)
    out["_pts"] = pts; return out

# ---------------------------------------------------------------- figure
def figure(path, diff, dnbr, burn, pred, pts=None, v=3.0):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(20, 5.2))
    im = ax[0].imshow(diff, cmap="RdBu_r", vmin=-v, vmax=v); ax[0].set_title("NISAR HV change (dB)\nblue = decrease"); plt.colorbar(im, ax=ax[0], fraction=.046)
    im = ax[1].imshow(dnbr, cmap="magma", vmin=-0.1, vmax=0.8); ax[1].set_title("Sentinel-2 dNBR\n(bright = burned)"); plt.colorbar(im, ax=ax[1], fraction=.046)
    ok = np.isfinite(diff) & np.isfinite(dnbr); ag = np.full(diff.shape + (3,), 0.9)
    ag[ok & pred & burn] = (0.1, 0.7, 0.2); ag[ok & pred & ~burn] = (0.9, 0.2, 0.2)
    ag[ok & ~pred & burn] = (0.2, 0.4, 0.9); ag[~ok] = 1
    ax[2].imshow(ag); ax[2].set_title("Agreement\ngreen=both  red=NISAR only  blue=optical only")
    ax[3].imshow(np.where(ok, burn, np.nan), cmap="Oranges", vmin=0, vmax=1.5); ax[3].set_title("Optical burn mask (+ FIRMS hotspots)")
    if pts:
        rr, cc = np.array(pts).T; ax[3].scatter(cc, rr, s=6, c="k")
        ax[2].scatter(cc, rr, s=6, c="k")
    for a in ax: a.axis("off")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)

# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--event", required=True, help="folder written by nisar_before_after.py, e.g. output/spain_fire")
    p.add_argument("--pre", nargs=2, metavar=("START", "END"), help="Sentinel-2 pre-fire window YYYY-MM-DD YYYY-MM-DD")
    p.add_argument("--post", nargs=2, metavar=("START", "END"), help="Sentinel-2 post-fire window")
    p.add_argument("--dnbr", type=float, default=0.27, help="dNBR burn threshold (0.27 = moderate-low severity, common default)")
    p.add_argument("--thresh", type=float, default=-2.0, help="NISAR decrease threshold in dB")
    p.add_argument("--coarsen", type=int, default=5, help="also score on a coarser grid (blocks of N pixels) to beat speckle")
    p.add_argument("--firms", help="FIRMS CSV (VIIRS or MODIS) with latitude, longitude, acq_date")
    A = p.parse_args(); folder = Path(A.event)
    g, diff, meta = load(folder); bbox = meta.get("bbox_lonlat")
    if not bbox: raise SystemExit("meta.json with bbox_lonlat missing: rerun nisar_before_after.py")
    t = lambda s: datetime.fromisoformat(str(s).split("+")[0].strip())
    b0, a0 = t(meta["before"]["start"]), t(meta["after"]["start"])
    pre = [datetime.fromisoformat(x) for x in A.pre] if A.pre else [b0 - timedelta(days=15), b0]
    post = [datetime.fromisoformat(x) for x in A.post] if A.post else [a0 - timedelta(days=7), a0 + timedelta(days=20)]
    print("Fetching Sentinel-2 (Microsoft Planetary Computer)...")
    dnbr = s2_nbr(g, bbox, *pre) - s2_nbr(g, bbox, *post)
    res = {}
    for k in (1, A.coarsen):
        d, n = coarsen(diff, k), coarsen(dnbr, k)
        res[f"scale_{k}x"] = m = metrics(d, n, A.thresh, A.dnbr)
        print(f"\n=== scale {k}x ({g['pixel_m']*k:.0f} m) ===");
        for key, val in m.items(): print(f"  {key}: {val:.3f}" if isinstance(val, float) else f"  {key}: {val}")
        print("  ->", verdict(m))
    pts = None
    if A.firms:
        fm = firms_hits(A.firms, g, diff, dnbr > A.dnbr, b0, a0, A.thresh); pts = fm.pop("_pts", None); res["firms"] = fm
        print("\n=== FIRMS hotspots ===", fm)
    figure(folder / "VALIDATION.png", diff, dnbr, dnbr > A.dnbr, diff <= A.thresh, pts)
    (folder / "validation.json").write_text(json.dumps(res, indent=2, default=float))
    print(f"\nWrote {folder/'VALIDATION.png'} and validation.json")

if __name__ == "__main__":
    main()