"""
subsidence_detail.py -- 20 m view of one cluster of subsidence bowls (4x finer than subsidence_series.py).

  uv run python fetch_series.py --only krzyzowice --wrapped
  uv run python subsidence_detail.py --only krzyzowice

The product ships displacement-ready (unwrapped) phase only at 80 m, and the raw wrapped interferogram at 20 m.
Wrapped phase only knows the motion modulo one fringe (12 cm). We restore the missing whole fringes from the
80 m layer:  phase_20m = wrapped_20m + 2 pi * round((unwrapped_80m - wrapped_20m) / 2 pi)   ("guided unwrapping").
Everything after that is the same as in the 80 m analysis: ionosphere screen removed, ~5 km moving average removed,
intervals summed. Extra at 20 m: coherence per interval, because ground that breaks up (cracks, a forming
sinkhole) loses coherence before it shows as displacement.
"""
import argparse, json
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
import nisar_io as nio, change_methods as cm
from subsidence_series import pair_dates

HERE = Path(__file__).parent


def pair_20m(g, hp_m=5000.0, min_coh=0.2):
    w = g["w_phase"].astype("float64"); shape = w.shape
    up = lambda a: ndi.zoom(np.nan_to_num(a.astype("float64"), nan=0.0), (shape[0] / a.shape[0], shape[1] / a.shape[1]), order=1)
    unw80 = g["u_unwrappedPhase"]; ok80 = np.isfinite(unw80) & (g["u_connectedComponents"] > 0)
    guide = up(np.where(ok80, unw80, 0.0)); okg = up(ok80.astype("float32")) > 0.9
    full = w + 2 * np.pi * np.round((guide - w) / (2 * np.pi))
    iono = g["u_ionospherePhaseScreen"]; full = full - up(np.where(np.isfinite(iono), iono, 0.0))
    coh = g["w_coherence"]
    d = np.where(okg & np.isfinite(w) & (cm.nanfilter(coh, 3) >= min_coh), full * g["wavelength_m"] / (4 * np.pi) * 100.0, np.nan)
    d = d - np.nanmedian(d)
    k = int(round(hp_m / float(g["w_pixel_m"]))) | 1
    return (d - cm.nanfilter(d, k)).astype("float32"), coh


def run(name, case, data, out_root):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from pyproj import Transformer
    folder, out = data / name, out_root / name; out.mkdir(parents=True, exist_ok=True)
    pairs = []
    for i, gname in enumerate(case["gunw_series"]):
        p = folder / f"a_{i:02d}.npz"
        if p.exists():
            g = nio.cached(p, None); d, coh = pair_20m(g); pairs.append(dict(d=d, coh=coh, phase=g["w_phase"], dates=pair_dates(gname), g=g))
    if len(pairs) < 2: print(f"[{name}] need at least 2 pairs"); return
    H, W = np.min([p["d"].shape for p in pairs], axis=0); g0 = pairs[0]["g"]; x, y = g0["w_x"][:W], g0["w_y"][:H]
    d = np.stack([p["d"][:H, :W] for p in pairs]); days = np.array([(p["dates"][1] - p["dates"][0]).days for p in pairs], float)
    rate = d / days[:, None, None]; n = np.isfinite(rate).sum(0)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning); mean_rate = np.where(n >= 0.6 * len(pairs), np.nanmean(rate, 0), np.nan)
    steps = np.where(np.isfinite(d), d, mean_rate[None] * days[:, None, None]); cum = np.cumsum(steps, 0); total = cum[-1]
    sign = -1.0 if np.nansum(total[np.abs(total) > np.nanpercentile(np.abs(total), 99.5)]) > 0 else 1.0
    steps, cum, total = steps * sign, cum * sign, total * sign
    coh = np.stack([cm.nanfilter(p["coh"][:H, :W], 3) for p in pairs])
    coh_drop = np.nanmedian(coh[:-1], 0) - coh[-1]                       # where the last interval lost coherence it had before
    np.savez_compressed(folder / "detail_layers.npz", x=x, y=y, epsg=int(g0["epsg"]), cumulative_cm=cum.astype("float32"),
                        coherence=coh.astype("float32"), dates=np.array([f"{pairs[0]['dates'][0]:%Y-%m-%d}"] + [f"{p['dates'][1]:%Y-%m-%d}" for p in pairs]))
    px = float(g0["w_pixel_m"]); sm = cm.nanfilter(total, 5)
    r, c = np.unravel_index(np.nanargmin(sm), sm.shape); inv = Transformer.from_crs(int(g0["epsg"]), 4326, always_xy=True)
    lon, lat = inv.transform(float(x[c]), float(y[r]))
    stats = {"case": name, "pixel_m": px, "pairs": len(pairs), "period": [f"{pairs[0]['dates'][0]:%Y-%m-%d}", f"{pairs[-1]['dates'][1]:%Y-%m-%d}"],
             "deepest_cm": round(float(-sm[r, c]), 1), "deepest_lonlat": [round(lon, 5), round(lat, 5)],
             "area_over_5cm_km2": round(float((sm <= -5).sum() * (px / 1000) ** 2), 2), "area_over_20cm_km2": round(float((sm <= -20).sum() * (px / 1000) ** 2), 2),
             "valid_fraction": round(float(np.isfinite(total).mean()), 2),
             "last_interval": {"dates": [f"{d:%Y-%m-%d}" for d in pairs[-1]["dates"]], "max_sink_cm": round(float(-np.nanmin(cm.nanfilter(steps[-1], 5))), 1),
                               "area_coherence_drop_over_0.3_km2": round(float((coh_drop >= 0.3).sum() * (px / 1000) ** 2), 2)}}
    (out / "detail_stats.json").write_text(json.dumps(stats, indent=2)); print(json.dumps(stats, indent=1))

    ext = [x[0], x[-1], y[-1], y[0]]; f = Transformer.from_crs(4326, int(g0["epsg"]), always_xy=True)
    places = {"Krzyżowice": (18.679, 49.985), "Pniówek (kopalnia)": (18.695, 49.972), "Zofiówka (kopalnia)": (18.628, 49.962), "Warszowice": (18.713, 50.000),
              "Pawłowice": (18.718, 49.962), "Borynia": (18.63, 50.0), "Bzie": (18.67, 49.94), "Szeroka": (18.61, 49.99)}
    def deco(a):
        for nme, (lo, la) in places.items():
            tx, ty = f.transform(lo, la)
            if x[0] < tx < x[-1] and y[-1] < ty < y[0]: a.plot(tx, ty, "o", ms=3, color="#7fe0d8"); a.text(tx + 120, ty + 120, nme, color="#d8f5f2", fontsize=9)
        a.set_xlim(x[0], x[-1]); a.set_ylim(y[-1], y[0]); a.axis("off")
    bgim = np.nanmean(coh, 0)
    fig, ax = plt.subplots(1, 3, figsize=(24, 24 * H / W / 3 + 1.6), facecolor="#0b1420")
    ax[0].imshow(bgim, cmap="gray", vmin=0, vmax=1, extent=ext); im = ax[0].imshow(np.where(cm.clean(np.isfinite(sm) & (sm <= -3.0), 150, 0), -sm, np.nan), cmap="inferno", vmin=0, vmax=55, extent=ext)
    ax[0].set_title(f"Osiadanie łącznie, {stats['period'][0]} – {stats['period'][1]} (piksel 20 m)", color="white", fontsize=13, fontweight="bold")
    cb = fig.colorbar(im, ax=ax[0], fraction=0.035, pad=0.01); cb.set_label("cm", color="white"); plt.setp(cb.ax.get_yticklabels(), color="white")
    last = cm.nanfilter(steps[-1], 5)
    ax[1].imshow(bgim, cmap="gray", vmin=0, vmax=1, extent=ext); im = ax[1].imshow(np.where(cm.clean(np.isfinite(last) & (last <= -1.5), 150, 0), -last, np.nan), cmap="inferno", vmin=0, vmax=10, extent=ext)
    ax[1].set_title(f"Tylko ostatni odstęp: {pairs[-1]['dates'][0]:%d.%m} – {pairs[-1]['dates'][1]:%d.%m.%Y}", color="white", fontsize=13, fontweight="bold")
    cb = fig.colorbar(im, ax=ax[1], fraction=0.035, pad=0.01); cb.set_label("cm", color="white"); plt.setp(cb.ax.get_yticklabels(), color="white")
    ax[2].imshow(pairs[-1]["phase"][:H, :W], cmap="hsv", vmin=-np.pi, vmax=np.pi, extent=ext, interpolation="nearest")
    ax[2].set_title("Surowy interferogram ostatniego odstępu (1 pełny cykl kolorów = 12 cm)", color="white", fontsize=13, fontweight="bold")
    for a in ax: deco(a)
    fig.tight_layout(); fig.savefig(out / "DETAL_20m.jpg", dpi=100, facecolor="#0b1420", pil_kwargs={"quality": 90}); plt.close(fig)

    cols = min(5, len(pairs)); rows = -(-len(pairs) // cols)
    fig, ax = plt.subplots(rows, cols, figsize=(4.6 * cols, 4.6 * rows * H / W + 0.5 * rows), facecolor="#0b1420"); ax = np.atleast_1d(ax).ravel()
    for a, p, s in zip(ax, pairs, steps):
        a.imshow(bgim, cmap="gray", vmin=0, vmax=1, extent=ext); v = cm.nanfilter(s, 5) / ((p["dates"][1] - p["dates"][0]).days / 12.0)
        a.imshow(np.where(cm.clean(np.isfinite(v) & (v <= -1.5), 150, 0), -v, np.nan), cmap="inferno", vmin=0, vmax=10, extent=ext)
        a.set_title(f"{p['dates'][0]:%d.%m} – {p['dates'][1]:%d.%m}", color="white", fontsize=12)
    for a in ax: a.axis("off"); a.set_xlim(x[0], x[-1]); a.set_ylim(y[-1], y[0])
    fig.suptitle("Osiadanie w każdym odstępie osobno (cm na 12 dni, skala 0–10): gdzie teren opadał w danym okresie", color="white", fontsize=14, fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "ODSTEPY_20m.jpg", dpi=90, facecolor="#0b1420", pil_kwargs={"quality": 90}); plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--data", default=str(HERE / "data"))
    p.add_argument("--out", default=str(HERE / "output")); A = p.parse_args()
    run(A.only, json.loads((HERE / "cases.json").read_text())[A.only], Path(A.data), Path(A.out))
