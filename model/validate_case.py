"""
validate_case.py -- score the fire pipeline against an independent optical burn map (Sentinel-2 dNBR)
and compare method variants, so that every design choice is measured instead of assumed.

  uv run --group validate python validate_case.py --only spain_fire

Needs data/<case>/gcov_*.npz (fetch_case.py). Downloads Sentinel-2 from Microsoft Planetary Computer once
and caches the dNBR in data/<case>/dnbr.npy. Writes output/<case>/validation_methods.json + VALIDATION_methods.png
"""
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import nisar_io as nio, change_methods as cm, validate_fire as vf

HERE = Path(__file__).parent


def acq_time(granule):
    return datetime.strptime(granule.split("_")[11], "%Y%m%dT%H%M%S")


def dnbr_on_grid(case, b, cache):
    if cache.exists(): return np.load(cache)
    x, y = b["x"], b["y"]; px = float(b["pixel_m"])
    g = {"x_left": float(x[0] - px / 2), "y_top": float(y[0] + px / 2), "pixel_m": px, "shape": list(b["HHHH"].shape), "epsg": int(b["epsg"])}
    t0, t1 = acq_time(case["gcov_before"]), acq_time(case["gcov_after"])
    d = vf.s2_nbr(g, case["bbox"], t0 - timedelta(days=15), t0) - vf.s2_nbr(g, case["bbox"], t1 - timedelta(days=7), t1 + timedelta(days=20))
    np.save(cache, d.astype("float32")); return d


def auc(score, truth):
    r = vf.ranks(score); npos, nneg = truth.sum(), (~truth).sum()
    return float((r[truth].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def best_iou(score, truth, n=60):
    """Best IoU / F1 over all thresholds: what the method can reach when the threshold is chosen well."""
    best = (0, None, 0, 0)
    for t in np.quantile(score, np.linspace(0.5, 0.999, n)):
        p = score >= t; tp = (p & truth).sum(); u = (p | truth).sum()
        if u and tp / u > best[0]: best = (tp / u, float(t), tp / max(p.sum(), 1), tp / truth.sum())
    return best


def run(name, case, data, out, burn_thr=0.27):
    b, a = (nio.cached(data / name / f"{k}.npz", None) for k in ("gcov_before", "gcov_after"))
    shape = tuple(min(s, t) for s, t in zip(b["HHHH"].shape, a["HHHH"].shape))
    for d in (b, a):
        for p in ("HHHH", "HVHV"): d[p] = cm.match(d[p], shape)
    dnbr = cm.match(dnbr_on_grid(case, b, data / name / "dnbr.npy"), shape)
    truth_all = dnbr > burn_thr
    variants = {}
    for win in (1, 3, 5, 9, 15):
        for label, pols, w in (("HV", ("HVHV",), None), ("HH", ("HHHH",), None), ("HH+HV equal", ("HHHH", "HVHV"), (1, 1)),
                               ("HH+HV (HV x2)", ("HHHH", "HVHV"), (0.5, 1))):
            s, diffs, _ = cm.backscatter_change(b, a, pols=pols, win=win, direction="decrease", weights=w, max_texture_db=None)
            variants[f"{label}, filter {win}x{win}"] = s
        # the cross-pol ratio HV/HH: insensitive to soil-moisture changes that move both channels together
        ratio = cm.log_ratio(b["HVHV"], a["HVHV"], win) - cm.log_ratio(b["HHHH"], a["HHHH"], win)
        variants[f"HV/HH ratio, filter {win}x{win}"] = -cm.robust_z(ratio)[0]
    ok = np.isfinite(dnbr) & np.all([np.isfinite(v) for v in variants.values()], 0)
    truth = truth_all[ok]; res = {}
    for label, s in variants.items():
        v = s[ok]; iou, thr, prec, rec = best_iou(v, truth)
        res[label] = {"AUC": auc(v, truth), "best_IoU": float(iou), "precision": float(prec), "recall": float(rec), "threshold_sigma": thr}
    # the first version of the pipeline, for reference: HV only, 2x2 average, fixed -2 dB
    d0 = cm.to_db(a["HVHV"]) - cm.to_db(b["HVHV"]); p0 = (d0 <= -2.0)[ok]
    tp = (p0 & truth).sum()
    res["BASELINE: HV, no filter, fixed -2 dB"] = {"AUC": auc(-np.nan_to_num(d0[ok]), truth), "best_IoU": float(tp / (p0 | truth).sum()),
                                                   "precision": float(tp / max(p0.sum(), 1)), "recall": float(tp / truth.sum()), "threshold_sigma": None}
    order = sorted(res, key=lambda k: -res[k]["best_IoU"])
    print(f"[{name}] burned share by Sentinel-2 dNBR: {truth.mean()*100:.1f}%  ({ok.sum()} valid pixels)")
    for k in order: print(f"  {k:38s} AUC {res[k]['AUC']:.3f}  IoU {res[k]['best_IoU']:.3f}  prec {res[k]['precision']:.2f}  rec {res[k]['recall']:.2f}")
    (out / name).mkdir(parents=True, exist_ok=True)
    (out / name / "validation_methods.json").write_text(json.dumps({"burn_threshold_dNBR": burn_thr, "ranked": {k: res[k] for k in order}}, indent=2))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    best = order[0]; s = variants[best]; pred = s >= res[best]["threshold_sigma"]
    fig, ax = plt.subplots(1, 3, figsize=(18, 5.5))
    ax[0].imshow(s, cmap="magma", vmin=0, vmax=6); ax[0].set_title(f"NISAR change score\n{best}")
    ax[1].imshow(dnbr, cmap="magma", vmin=-0.1, vmax=0.8); ax[1].set_title("Sentinel-2 dNBR (optical ground truth)")
    ag = np.full(s.shape + (3,), 0.9); okk = np.isfinite(dnbr) & np.isfinite(s)
    ag[okk & pred & truth_all] = (0.1, 0.7, 0.2); ag[okk & pred & ~truth_all] = (0.9, 0.2, 0.2); ag[okk & ~pred & truth_all] = (0.2, 0.4, 0.9)
    ax[2].imshow(ag); ax[2].set_title(f"green = both, red = NISAR only, blue = optical only   IoU {res[best]['best_IoU']:.2f}")
    for x in ax: x.axis("off")
    fig.tight_layout(); fig.savefig(out / name / "VALIDATION_methods.png", dpi=110); plt.close(fig)
    return res


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output"))
    A = p.parse_args()
    for n, c in json.loads(Path(A.cases).read_text()).items():
        if c["kind"] != "fire" or (A.only and n != A.only): continue
        run(n, c, Path(A.data), Path(A.out))
