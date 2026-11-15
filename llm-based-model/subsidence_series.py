"""
subsidence_series.py -- ground subsidence from a chain of NISAR GUNW pairs (time-series InSAR, kept simple).

  uv run python fetch_series.py --only silesia && uv run python fetch_series.py --only silesia --check
  uv run python subsidence_series.py --only silesia

What is measured, and only this:
  1. how many centimetres the ground moved along the radar line of sight in each 12/24-day interval
  2. the sum over the whole period (June -> October 2026) = cumulative subsidence map
  3. for every sinking area ("bowl"): size, maximum sinking, and its curve in time

How a bowl is accepted as real (everything else is dropped):
  * it sinks in most of the individual intervals (a noise blob does not keep the same sign nine times)
  * a second, independent satellite track looking from the opposite side sees sinking in the same place

Processing per pair: unwrapped phase - ionosphere screen -> cm; keep coherent, unwrapped pixels; subtract a
~5 km moving average. The last step removes atmosphere and orbit errors, which are smooth over tens of km,
and keeps mining bowls, which are 0.5-2 km wide. It also means regional (wide) motion is NOT measured here.

Sign: InSAR phase sign conventions differ between processors, so the sign is fixed empirically: compact
strong anomalies above active coal mines are subsidence. Negative = sinking in all outputs.
"""
import argparse, json
from datetime import datetime
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
import nisar_io as nio, change_methods as cm

HERE = Path(__file__).parent
TOWNS = {"Bytom": (18.92, 50.35), "Ruda Śląska": (18.86, 50.29), "Katowice": (19.02, 50.26), "Zabrze": (18.79, 50.31),
         "Gliwice": (18.67, 50.29), "Knurów": (18.67, 50.22), "Mikołów": (18.90, 50.17), "Tychy": (18.99, 50.13),
         "Mysłowice": (19.14, 50.21), "Bieruń": (19.09, 50.09), "Lędziny": (19.13, 50.14), "Rybnik": (18.55, 50.10),
         "Żory": (18.70, 50.04), "Jastrzębie-Zdrój": (18.58, 49.95), "Pszczyna": (18.95, 49.98), "Ornontowice": (18.75, 50.19),
         "Czerwionka-Leszczyny": (18.68, 50.15), "Orzesze": (18.78, 50.15), "Łaziska Górne": (18.84, 50.15),
         "Piekary Śląskie": (18.95, 50.38), "Chorzów": (18.95, 50.30), "Sosnowiec": (19.13, 50.28), "Jaworzno": (19.27, 50.20),
         "Pawłowice": (18.72, 49.96), "Suszec": (18.79, 50.03), "Radlin": (18.47, 50.05), "Wodzisław Śląski": (18.47, 50.00),
         "Imielin": (19.18, 50.15), "Świętochłowice": (18.92, 50.29), "Siemianowice Śląskie": (19.03, 50.31)}


def pair_dates(granule):
    t = granule.split("_"); return datetime.strptime(t[11][:8], "%Y%m%d"), datetime.strptime(t[13][:8], "%Y%m%d")


def load_chain(folder, prefix, granules, hp_px=61, min_coh=0.25):
    """Per-pair local displacement in cm (high-passed), plus dates. Missing files are skipped."""
    out, seen = [], set()
    for i, gname in enumerate(granules):
        p = folder / f"{prefix}_{i:02d}.npz"
        if not p.exists() or pair_dates(gname) in seen: continue      # the catalogue can list one pair twice (two versions)
        seen.add(pair_dates(gname))
        g = nio.cached(p, None)
        d, _ = cm.los_displacement(g, min_coh=min_coh)
        d = d - cm.nanfilter(d, hp_px)
        out.append(dict(d=d, x=g["u_x"], y=g["u_y"], epsg=int(g["epsg"]), dates=pair_dates(gname), px=float(g["u_pixel_m"])))
    return out


def cumulative(chain):
    """Steps of the cumulative curve. A pixel missing in one interval gets that pixel's own mean rate there."""
    shape = tuple(np.min([c["d"].shape for c in chain], axis=0))
    d = np.stack([c["d"][: shape[0], : shape[1]] for c in chain]); days = np.array([(c["dates"][1] - c["dates"][0]).days for c in chain], float)
    rate = d / days[:, None, None]
    n = np.isfinite(rate).sum(0)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_rate = np.where(n >= 0.7 * len(chain), np.nanmean(rate, 0), np.nan)
    steps = np.where(np.isfinite(d), d, mean_rate[None] * days[:, None, None])
    return np.cumsum(steps, 0), steps, n


def sample(chain_cum, src, dst_x, dst_y):
    """Nearest-neighbour resample of a [T, H, W] stack from the src grid to another grid in the same projection."""
    c = np.rint((dst_x - src["x"][0]) / (src["x"][1] - src["x"][0])).astype(int)
    r = np.rint((dst_y - src["y"][0]) / (src["y"][1] - src["y"][0])).astype(int)
    ok = (r[:, None] >= 0) & (r[:, None] < chain_cum.shape[1]) & (c[None] >= 0) & (c[None] < chain_cum.shape[2])
    out = chain_cum[:, np.clip(r, 0, chain_cum.shape[1] - 1)][:, :, np.clip(c, 0, chain_cum.shape[2] - 1)]
    return np.where(ok[None], out, np.nan)


def nearest_town(lon, lat):
    k = min(TOWNS, key=lambda t: ((TOWNS[t][0] - lon) * 0.64) ** 2 + (TOWNS[t][1] - lat) ** 2)
    km = float(np.hypot((TOWNS[k][0] - lon) * 71.5, (TOWNS[k][1] - lat) * 111.2))
    return k, km


def run(name, case, data, out_root, min_sink_cm=3.0, min_area_km2=0.15):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from pyproj import Transformer
    folder, out = data / name, out_root / name; out.mkdir(parents=True, exist_ok=True)
    A = load_chain(folder, "a", case["gunw_series"]); B = load_chain(folder, "b", case.get("gunw_series_check", []))
    if len(A) < 3: print(f"[{name}] need at least 3 pairs in {folder}"); return
    cumA, stepsA, nA = cumulative(A); H, W = cumA.shape[1:]; x, y = A[0]["x"][:W], A[0]["y"][:H]; px_km2 = (A[0]["px"] / 1000) ** 2
    total = cumA[-1]
    sign = -1.0 if np.nansum(total[np.abs(total) > np.nanpercentile(np.abs(total), 99.5)]) > 0 else 1.0   # make sinking negative
    cumA, stepsA, total = cumA * sign, stepsA * sign, total * sign
    cumB = None
    if len(B) >= 3 and B[0]["epsg"] == A[0]["epsg"]:
        cb, _, _ = cumulative(B); tb = cb[-1]
        sb = -1.0 if np.nansum(tb[np.abs(tb) > np.nanpercentile(np.abs(tb), 99.5)]) > 0 else 1.0
        cumB = sample(cb * sb, B[0], x, y)
    noise = 1.4826 * np.nanmedian(np.abs(total - np.nanmedian(total)))
    thr = -max(min_sink_cm, 5 * noise)
    sm = cm.nanfilter(total, 3)
    lab, n = ndi.label(cm.clean(np.isfinite(sm) & (sm <= thr), int(round(min_area_km2 / px_km2)), open_px=0), structure=np.ones((3, 3)))
    tr = Transformer.from_crs(A[0]["epsg"], 4326, always_xy=True)
    datesA = [A[0]["dates"][0]] + [c["dates"][1] for c in A]
    datesB = ([B[0]["dates"][0]] + [c["dates"][1] for c in B]) if cumB is not None else None
    bowls = []
    for i in range(1, n + 1):
        m = lab == i; r, c = np.unravel_index(np.nanargmin(np.where(m, sm, np.nan)), sm.shape)
        core = m & (sm <= 0.5 * sm[r, c])                              # the deepest half of the bowl
        curve = np.concatenate([[0.0], np.nanmedian(cumA[:, core], axis=1)])
        steps = np.diff(curve); sinking = float((steps < 0).mean())
        lon, lat = tr.transform(float(x[c]), float(y[r])); town, km = nearest_town(lon, lat)
        b = dict(lon=round(lon, 4), lat=round(lat, 4), near=town, km_from_town=round(km, 1), area_km2=round(float(m.sum() * px_km2), 2),
                 max_sink_cm=round(float(-sm[r, c]), 1), core_sink_cm=round(float(-curve[-1]), 1), share_of_intervals_sinking=round(sinking, 2),
                 curve_cm=[round(float(v), 2) for v in curve], _core=core)
        if cumB is not None:
            cb_curve = np.concatenate([[0.0], np.nanmedian(cumB[:, core], axis=1)])
            b["check_track_sink_cm"] = None if not np.isfinite(cb_curve[-1]) else round(float(-cb_curve[-1]), 1)
            b["check_curve_cm"] = [None if not np.isfinite(v) else round(float(v), 2) for v in cb_curve]
        ok_time = sinking >= 0.65
        # the two tracks can cover different time spans, so compare sinking RATES, not totals
        dA = (datesA[-1] - datesA[0]).days; b["rate_cm_per_month"] = round(b["core_sink_cm"] / dA * 30, 1)
        if cumB is not None and b["check_track_sink_cm"] is not None:
            b["check_rate_cm_per_month"] = round(b["check_track_sink_cm"] / (datesB[-1] - datesB[0]).days * 30, 1)
        ok_track = cumB is None or (b.get("check_rate_cm_per_month") is not None and b["check_rate_cm_per_month"] >= 0.3 * b["rate_cm_per_month"])
        b["confirmed"] = bool(ok_time and ok_track)
        b["why_rejected"] = None if b["confirmed"] else ("does not sink steadily" if not ok_time else "second track does not see it")
        bowls.append(b)
    real = sorted([b for b in bowls if b["confirmed"]], key=lambda b: -b["max_sink_cm"])
    # ---------------- projection to the end of the year: "if the recent pace continues"
    # Rate = straight line through the last 4 measurements (about 5 weeks). Checked by hiding the last 3 measurements
    # (36 days) and predicting them: the spread of that error gives the band. It is an extrapolation, not a mining model:
    # a bowl slows down and stops once the coal face has passed, and that cannot be seen in advance from the surface.
    tA = np.array([(d - datesA[0]).days for d in datesA], float); NFIT, HIDE = 4, 3
    end = datetime(datesA[-1].year, 12, 31); horizon = (end - datesA[-1]).days
    def rate_of(curve, k): return np.polyfit(tA[k - NFIT:k], np.asarray(curve)[k - NFIT:k], 1)[0]
    bt = []
    for b in real:
        c = np.asarray(b["curve_cm"]); k = len(c) - HIDE; span = tA[-1] - tA[k - 1]
        actual = c[-1] - c[k - 1]
        if abs(actual) > 1: bt.append((rate_of(c, k) * span - actual) / abs(actual))
    bt = np.array(bt); band = float(np.percentile(np.abs(bt), 80)) if len(bt) else 0.5
    band_h = min(1.0, band * np.sqrt(horizon / (tA[-1] - tA[-1 - HIDE])))          # wider for the longer horizon
    fdates = [datesA[-1] + (end - datesA[-1]) * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    for b in real:
        r = min(0.0, rate_of(b["curve_cm"], len(b["curve_cm"]))); last = b["curve_cm"][-1]
        inc = [r * (d - datesA[-1]).days for d in fdates]
        b["forecast"] = {"dates": [f"{d:%Y-%m-%d}" for d in fdates], "cm": [round(last + v, 1) for v in inc],
                         "low_cm": [round(last + v * (1 + band_h), 1) for v in inc], "high_cm": [round(last + v * (1 - band_h), 1) for v in inc],
                         "rate_cm_per_month": round(-r * 30, 1)}
    forecast_info = {"until": f"{end:%Y-%m-%d}", "horizon_days": horizon, "fit_points": NFIT,
                     "backtest": {"hidden_days": int(tA[-1] - tA[-1 - HIDE]), "bowls": int(len(bt)), "median_abs_error_pct": round(float(np.median(np.abs(bt)) * 100)) if len(bt) else None,
                                  "p80_abs_error_pct": round(band * 100), "bias_pct": round(float(np.median(bt) * 100)) if len(bt) else None},
                     "band_pct_at_horizon": round(band_h * 100)}
    days = (datesA[-1] - datesA[0]).days
    stats = {"case": name, "title": case["title"], "period": [f"{datesA[0]:%Y-%m-%d}", f"{datesA[-1]:%Y-%m-%d}"], "days": days,
             "pairs_main_track": len(A), "pairs_check_track": len(B), "noise_cm": round(float(noise), 2), "threshold_cm": round(float(thr), 2),
             "candidates": len(bowls), "confirmed": len(real), "rejected": {k: sum(1 for b in bowls if b["why_rejected"] == k) for k in ("does not sink steadily", "second track does not see it")},
             "total_confirmed_area_km2": round(sum(b["area_km2"] for b in real), 1),
             "forecast": forecast_info,
             "bowls": [{k: v for k, v in b.items() if not k.startswith("_")} for b in real]}
    (out / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    realmask = np.zeros((H, W), bool)
    for b in real: realmask |= lab == (bowls.index(b) + 1)
    np.savez_compressed(folder / "subsidence_layers.npz", x=x, y=y, epsg=A[0]["epsg"], total_cm=total.astype("float32"), confirmed=realmask,
                        cumulative_cm=cumA.astype("float32"), dates=np.array([f"{d:%Y-%m-%d}" for d in datesA]),
                        check_dates=np.array([f"{d:%Y-%m-%d}" for d in (datesB or [])]),
                        coherence=np.nanmean([nio.cached(folder / f"a_{i:02d}.npz", None)["u_coherenceMagnitude"][:H, :W] for i in range(len(A))], 0))
    print(json.dumps({k: v for k, v in stats.items() if k != "bowls"}, indent=1, ensure_ascii=False))
    for b in real[:12]: print(f"  {b['near']:22s} {b['max_sink_cm']:5.1f} cm  {b['area_km2']:5.2f} km2  sinking in {b['share_of_intervals_sinking']*100:.0f}% of intervals  rate {b['rate_cm_per_month']} cm/month, check track {b.get('check_rate_cm_per_month')} cm/month")

    # ---------------- figure 1: map
    bg = np.load(folder / "subsidence_layers.npz")["coherence"]
    vmax = max(6.0, float(np.percentile([b["max_sink_cm"] for b in real], 90))) if real else 6.0
    fig, ax = plt.subplots(figsize=(15, 15 * H / W + 1.2), facecolor="#0b1420")
    ext = [x[0], x[-1], y[-1], y[0]]
    ax.imshow(bg, cmap="gray", vmin=0, vmax=1, extent=ext, alpha=0.9)
    show = np.where(realmask | (cm.nanfilter(total, 3) <= thr / 2) & ndi.binary_dilation(realmask, iterations=6), -total, np.nan)
    im = ax.imshow(show, cmap="inferno", vmin=0, vmax=vmax, extent=ext)
    f = Transformer.from_crs(4326, A[0]["epsg"], always_xy=True)
    for t, (lo, la) in TOWNS.items():
        tx, ty = f.transform(lo, la)
        if x[0] < tx < x[-1] and y[-1] < ty < y[0]:
            ax.plot(tx, ty, "o", ms=3, color="#7fe0d8"); ax.text(tx + 500, ty + 300, t, color="#bfeee9", fontsize=9)
    for k, b in enumerate(real[:10], 1):
        tx, ty = f.transform(b["lon"], b["lat"]); ax.text(tx, ty + 900, str(k), color="white", fontsize=12, fontweight="bold", ha="center")
    ax.set_xlim(x[0], x[-1]); ax.set_ylim(y[-1], y[0]); ax.axis("off")
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01); cb.set_label("osiadanie w linii widzenia radaru (cm)", color="white")
    cb.ax.yaxis.set_tick_params(color="white"); plt.setp(cb.ax.get_yticklabels(), color="white")
    ax.set_title(f"Górny Śląsk: osiadanie terenu nad kopalniami, {datesA[0]:%d.%m} – {datesA[-1]:%d.%m.%Y} ({days} dni)\n"
                 f"NISAR, {len(A)} kolejnych interferogramów. Pokazano {len(real)} niecek potwierdzonych drugim torem satelity.",
                 color="white", fontsize=15, fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "MAPA_osiadania.jpg", dpi=110, facecolor="#0b1420", pil_kwargs={"quality": 90}); plt.close(fig)

    # ---------------- figure 2: curves (one measured line per bowl + projection)
    top = real[:6]
    if top:
        fig, ax = plt.subplots(2, 3, figsize=(17, 9), facecolor="white"); ax = ax.ravel()
        for k, (a, b) in enumerate(zip(ax, top), 1):
            fd = [datetime.strptime(d, "%Y-%m-%d") for d in b["forecast"]["dates"]]
            a.fill_between(fd, b["forecast"]["low_cm"], b["forecast"]["high_cm"], color="#8e6bd6", alpha=0.18, lw=0)
            a.plot(fd, b["forecast"]["cm"], "--", color="#8e6bd6", lw=2.2, label="prognoza przy obecnym tempie")
            a.plot(datesA, b["curve_cm"], "-o", color="#c0392b", lw=2.4, label="pomiar NISAR")
            a.axvline(datesA[-1], color="#999", lw=0.8, ls=":"); a.axhline(0, color="#888", lw=0.8)
            a.annotate(f"{b['forecast']['cm'][-1]:.0f} cm", (fd[-1], b["forecast"]["cm"][-1]), textcoords="offset points", xytext=(-6, 8), ha="right", color="#6a45b8", fontweight="bold")
            a.annotate(f"{b['curve_cm'][-1]:.0f} cm", (datesA[-1], b["curve_cm"][-1]), textcoords="offset points", xytext=(-6, -14), ha="right", color="#c0392b", fontweight="bold")
            a.set_title(f"{k}. {b['near']} ({b['km_from_town']} km), {b['area_km2']} km²", fontsize=12, fontweight="bold")
            a.set_ylabel("cm"); a.grid(alpha=0.3); a.tick_params(axis="x", rotation=30)
            if k == 1: a.legend(fontsize=9, loc="lower left")
        for a in ax[len(top):]: a.axis("off")
        fig.suptitle(f"Sześć największych niecek: pomiar do {datesA[-1]:%d.%m.%Y} i prognoza do końca roku (pas: ±{forecast_info['band_pct_at_horizon']}% przyrostu)\n"
                     "Każdą nieckę potwierdził drugi tor satelity. Ruch w linii widzenia radaru.", fontsize=13, fontweight="bold")
        fig.tight_layout(); fig.savefig(out / "WYKRES_niecki.jpg", dpi=110, pil_kwargs={"quality": 90}); plt.close(fig)
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--data", default=str(HERE / "data"))
    p.add_argument("--out", default=str(HERE / "output")); A = p.parse_args()
    run(A.only, json.loads((HERE / "cases.json").read_text())[A.only], Path(A.data), Path(A.out))
