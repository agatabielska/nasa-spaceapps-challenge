"""
change_methods.py -- the numerical change-detection building blocks shared by every disaster type.

All of them are standard SAR techniques:
  * multilooking / boxcar speckle filter on linear power
  * log-ratio (difference in dB) of backscatter between two dates
  * robust z-score: the change of every pixel is expressed in units of the scene's own noise, so one
    threshold works for any scene, polarisation or resolution (instead of a hand-picked dB value)
  * interferometric coherence loss against a quiet reference pair (damage-proxy-map idea, NASA ARIA)
  * unwrapped phase -> line-of-sight displacement
  * morphological clean-up of the final mask
"""
import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import median_filter



# ------------------------------------------------------------------ helpers
def nanfilter(a, size):
    """Boxcar mean that ignores NaN (normalised convolution)."""
    if size <= 1: return a
    ok = np.isfinite(a)
    s = ndi.uniform_filter(np.where(ok, a, 0.0).astype("float64"), size, mode="nearest")
    n = ndi.uniform_filter(ok.astype("float64"), size, mode="nearest")
    return np.where(n > 0.3, s / np.maximum(n, 1e-9), np.nan).astype("float32")


def to_db(p):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(p)


def robust_z(d, ok=None):
    """(d - median) / robust sigma. Median + MAD are barely affected by the changed area itself."""
    v = d[np.isfinite(d) if ok is None else ok & np.isfinite(d)]
    med = np.median(v); sig = 1.4826 * np.median(np.abs(v - med))
    return (d - med) / max(sig, 1e-6), float(med), float(sig)


def clean(mask, min_px=25, open_px=1):
    """Remove salt-and-pepper detections: binary opening, then drop connected blobs smaller than min_px."""
    m = ndi.binary_opening(mask, iterations=open_px) if open_px else mask
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    if n == 0: return m
    size = ndi.sum(m, lab, index=np.arange(1, n + 1))
    return np.isin(lab, np.flatnonzero(size >= min_px) + 1)


def match(a, shape):
    """Crop a 2-D array to a common shape (grids of the same track/frame differ by at most a pixel)."""
    return a[: shape[0], : shape[1]]


def resample_to(a, shape):
    """Nearest-neighbour resize of a coarse layer (80 m) onto a finer grid (20 m). Same extent assumed."""
    iy = np.minimum((np.arange(shape[0]) * a.shape[0] / shape[0]).astype(int), a.shape[0] - 1)
    ix = np.minimum((np.arange(shape[1]) * a.shape[1] / shape[1]).astype(int), a.shape[1] - 1)
    return a[np.ix_(iy, ix)]


# ------------------------------------------------------------------ backscatter (GCOV)
def log_ratio(before, after, win=5):
    """Speckle-filter both dates in linear power, then after-minus-before in dB."""
    return to_db(nanfilter(after, win)) - to_db(nanfilter(before, win))


def texture_db(p, win=5):
    """Local standard deviation of backscatter in dB: high on layover / foreshortened slopes and sharp edges."""
    d = to_db(p); mu = nanfilter(d, win)
    return np.sqrt(np.maximum(nanfilter((d - mu) ** 2, win), 0.0))


def reliable(before, after, pols, win=5, max_texture_db=3.5, dark_db=-20.0):
    """Pixels where a dB difference can be trusted.

    On steep slopes the image is a patchwork of very bright and very dark pixels; a sub-pixel shift
    between the two dates then creates large fake changes (red/blue pairs). Those places have a high
    local texture, so we drop them. Tested on the Nepal case: precision of the backscatter mask
    against the independent coherence mask rose from 0.06 to 0.35 while keeping 77 % of the scene.
    """
    ok = np.ones(before[pols[0]].shape, bool)
    for p in pols:
        t = np.fmax(texture_db(before[p]), texture_db(after[p]))
        ok &= nanfilter(t, win) < max_texture_db
    # permanently dark surfaces (sea, lakes, radar shadow) are pure noise in both dates: nothing to compare.
    # A surface that is dark in only ONE date is kept - that is exactly what a new flood looks like.
    p0 = pols[0]
    ok &= ~((to_db(nanfilter(before[p0], win)) < dark_db) & (to_db(nanfilter(after[p0], win)) < dark_db))
    return ok


def backscatter_change(before, after, pols=("HHHH", "HVHV"), win=5, direction="both", weights=None,
                       max_texture_db=3.5):
    """Change score from one or more polarisations.

    direction: 'decrease' (fire, open water), 'increase', or 'both' (debris, lava, flooded vegetation).
    Returns score (in noise sigmas, >0 = change in the requested direction; NaN where unreliable),
    the per-pol dB differences and the reliability mask.
    """
    ok = reliable(before, after, pols, win, max_texture_db) if max_texture_db else None
    diffs, zs = {}, []
    for p in pols:
        d = log_ratio(before[p], after[p], win); diffs[p] = d
        zs.append(robust_z(d, ok)[0])
    z = np.stack(zs); w = np.ones(len(pols)) if weights is None else np.asarray(weights, float)
    w = w[:, None, None]
    if direction == "both":
        score = np.sqrt((w * z**2).sum(0) / w.sum())           # magnitude of the change vector
    else:
        sgn = -1.0 if direction == "decrease" else 1.0
        score = sgn * (w * z).sum(0) / np.sqrt((w**2).sum())    # sum of z-scores, rescaled to unit sigma
    if ok is not None: score = np.where(ok, score, np.nan)
    return score.astype("float32"), diffs, (ok if ok is not None else np.isfinite(score))


# ------------------------------------------------------------------ coherence (GUNW)
def coherence_loss(coh_event, coh_ref, win=3, min_ref=0.35):
    """Drop of interferometric coherence in the event pair relative to a quiet pair of the same track.

    Only pixels that were coherent before (ref >= min_ref) can show a loss: water, snow and steep
    layover are incoherent in every pair and are excluded instead of being reported as damage.
    """
    e, r = nanfilter(coh_event, win), nanfilter(coh_ref, win)
    loss = r - e
    usable = np.isfinite(loss) & (r >= min_ref)
    return np.where(usable, loss, np.nan).astype("float32"), usable


# ------------------------------------------------------------------ displacement (GUNW)
def los_displacement(g, min_coh=0.3):
    """Unwrapped phase -> line-of-sight displacement in cm, relative to the stable part of the scene.

    Steps: subtract the ionosphere screen shipped in the product, keep pixels that were unwrapped
    (connected component > 0) and coherent, convert with lambda / 4 pi, remove the scene median
    (InSAR measures relative motion only).
    """
    phase = g["u_unwrappedPhase"].astype("float64")
    iono = g["u_ionospherePhaseScreen"].astype("float64")
    phase = phase - np.where(np.isfinite(iono), iono, 0.0)
    ok = np.isfinite(phase) & (g["u_connectedComponents"] > 0) & (g["u_coherenceMagnitude"] >= min_coh)
    disp = phase * g["wavelength_m"] / (4 * np.pi) * 100.0
    disp = np.where(ok, disp, np.nan)
    return (disp - np.nanmedian(disp)).astype("float32"), ok


def detrend_plane(d):
    """Remove a best-fit plane (orbit / long-wavelength atmosphere), fitted robustly on the outer scene."""
    yy, xx = np.mgrid[: d.shape[0], : d.shape[1]]
    ok = np.isfinite(d)
    A = np.c_[xx[ok], yy[ok], np.ones(ok.sum())]; b = d[ok]
    keep = np.ones(len(b), bool)
    for _ in range(3):                                           # iteratively ignore the deforming area
        c, *_ = np.linalg.lstsq(A[keep], b[keep], rcond=None)
        res = b - A @ c; keep = np.abs(res) < 2.0 * 1.4826 * np.median(np.abs(res - np.median(res))) + 1e-6
    return (d - (c[0] * xx + c[1] * yy + c[2])).astype("float32")


# ------------ glacier velocity

def glacier_velocity(data, min_correlation=0.3, min_snr=3.0):
    """
    Calculate radar-projected displacement rates in m/day.

    These are along-track and slant-range components,
    NOT the full horizontal glacier velocity.
    """
    import numpy as np

    along = data["along"].astype(float)
    slant = data["slant"].astype(float)
    correlation = data["correlation"].astype(float)
    snr = data["snr"].astype(float)

    baseline = float(data["baseline"])

    if baseline <= 0:
        raise ValueError("Temporal baseline must be positive")

    valid = (
        np.isfinite(along)
        & np.isfinite(slant)
        & np.isfinite(correlation)
        & np.isfinite(snr)
        & (correlation >= min_correlation)
        & (snr >= min_snr)
    )

    along_rate = np.where(valid, along / baseline, np.nan)
    slant_rate = np.where(valid, slant / baseline, np.nan)

    return {
        "along_rate": along_rate,
        "slant_rate": slant_rate,
        "valid": valid,
    }


def compare_glacier_periods(early, late):
    """
    Compare radar-projected displacement rates
    between two observation periods.
    """
    import numpy as np

    for key in ("epsg",):
        if int(early[key]) != int(late[key]):
            raise ValueError(f"Different {key}")

    for key in ("x", "y"):
        if not np.allclose(
            early[key], late[key], rtol=0, atol=0.01
        ):
            raise ValueError(
                f"Different {key} coordinates: "
                "rasters must be aligned before comparison"
            )

    v_early = glacier_velocity(early)
    v_late = glacier_velocity(late)

    valid = v_early["valid"] & v_late["valid"]

    return {
        "along_change": np.where(
            valid,
            v_late["along_rate"] - v_early["along_rate"],
            np.nan,
        ),
        "slant_change": np.where(
            valid,
            v_late["slant_rate"] - v_early["slant_rate"],
            np.nan,
        ),
        "valid": valid,
    }



def glacier_quality_summary(data):
    """Summarise quality metrics for a GOFF subset."""
    correlation = data["correlation"]
    snr = data["snr"]

    finite = (
        np.isfinite(data["along"])
        & np.isfinite(data["slant"])
        & np.isfinite(correlation)
        & np.isfinite(snr)
    )

    quality = finite & (correlation >= 0.3) & (snr >= 3.0)

    print(f"Finite measurements: {finite.mean():.1%}")
    print(f"Passing quality filters: {quality.mean():.1%}")

    for name, arr in [
        ("Correlation", correlation),
        ("SNR", snr),
    ]:
        values = arr[np.isfinite(arr)]
        if values.size:
            print(
                f"{name} percentiles (10, 25, 50, 75, 90):",
                np.percentile(values, [10, 25, 50, 75, 90])
            )

    print("GOFF mask values:")
    values, counts = np.unique(data["mask"], return_counts=True)
    for value, count in zip(values, counts):
        print(f"  {value}: {count} pixels")


def glacier_backscatter_change(
    early,
    late,
    threshold_db=3.0,
    filter_size=5,
):
    early_hh = early["HHHH"].astype(float)
    late_hh = late["HHHH"].astype(float)

    valid = (
        np.isfinite(early_hh) &
        np.isfinite(late_hh) &
        (early_hh > 0) &
        (late_hh > 0)
    )

    early_db = np.full(early_hh.shape, np.nan)
    late_db = np.full(late_hh.shape, np.nan)

    early_db[valid] = 10 * np.log10(early_hh[valid])
    late_db[valid] = 10 * np.log10(late_hh[valid])

    difference = late_db - early_db

    # Filter each image before computing a smoothed difference
    early_smooth = nanfilter(early_db, filter_size)
    late_smooth = nanfilter(late_db, filter_size)

    smooth_difference = late_smooth - early_smooth
    smooth_difference[~valid] = np.nan

    # smooth_difference = late_smooth - early_smooth
    smooth_difference[~valid] = np.nan

    increase = valid & (smooth_difference >= threshold_db)
    decrease = valid & (smooth_difference <= -threshold_db)

    return {
        "early_db": early_db.astype("float32"),
        "late_db": late_db.astype("float32"),
        "difference": difference.astype("float32"),
        "smooth_difference": smooth_difference.astype("float32"),
        "increase": increase,
        "decrease": decrease,
        "valid": valid,
    }