"""
validate_glacier.py -- Sentinel-2 imagery for glacier validation.
"""

from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt

from check_location import s2_mosaic, composites


NAME = "jakobshavn_glacier"
FOLDER = Path("data") / NAME
OUT = Path("output") / NAME

BBOX = [-50.6, 68.9, -49.2, 69.4]

BANDS = ("B04", "B03", "B02", "B8A", "B12")

def glacier_s2_mosaic(grid, bbox, start, end, bands, max_cloud=80):
    import check_location
    import validate_fire

    original = validate_fire.CLOUD_SCL

    try:
        # Keep snow/ice (class 11)
        validate_fire.CLOUD_SCL = (0, 1, 8, 9, 10)

        return check_location.s2_mosaic(
            grid, bbox, start, end, bands,
            max_cloud=max_cloud
        )
    finally:
        validate_fire.CLOUD_SCL = original

def metrics(pred, truth):
    tp = np.count_nonzero(pred & truth)
    fp = np.count_nonzero(pred & ~truth)
    fn = np.count_nonzero(~pred & truth)

    return {
        "IoU": float(tp / max(tp + fp + fn, 1)),
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / max(tp + fn, 1)),
    }


def auc(score, truth):
    from scipy.stats import rankdata

    npos = int(truth.sum())
    nneg = int((~truth).sum())

    if npos == 0 or nneg == 0:
        return None

    ranks = rankdata(score)
    return float(
        (ranks[truth].sum() - npos * (npos + 1) / 2)
        / (npos * nneg)
    )


def best_iou(score, truth, n=40):
    best = None

    for threshold in np.unique(
        np.quantile(score, np.linspace(0.5, 0.999, n))
    ):
        pred = score >= threshold
        result = metrics(pred, truth)

        if best is None or result["IoU"] > best["IoU"]:
            best = {
                **result,
                "threshold": float(threshold),
            }

    return best


def validate_changes(june, october):
    import json
    from scipy import ndimage as ndi
    import change_methods as cm

    with np.load(FOLDER / "gcov_layers.npz") as z:
        early_db = z["early_db"].astype("float32")
        late_db = z["late_db"].astype("float32")
        valid_nisar = z["valid"].astype(bool)

    # --------------------------------------------------
    # Sentinel-2 optical change score
    # --------------------------------------------------

    optical_bands = ("B04", "B8A", "B12")

    valid_s2 = np.ones(early_db.shape, dtype=bool)

    for band in optical_bands:
        valid_s2 &= (
            np.isfinite(june[band])
            & np.isfinite(october[band])
        )

    optical_score = np.zeros(early_db.shape, dtype="float32")

    for band in optical_bands:
        before = june[band].astype("float32")
        after = october[band].astype("float32")

        # Absolute reflectance difference
        difference = np.abs(after - before)

        optical_score[valid_s2] += difference[valid_s2] ** 2

    optical_score = np.sqrt(optical_score)
    optical_score[~valid_s2] = np.nan

    # --------------------------------------------------
    # Common valid pixels
    # --------------------------------------------------

    valid = (
        valid_s2
        & valid_nisar
        & np.isfinite(early_db)
        & np.isfinite(late_db)
        & np.isfinite(optical_score)
    )

    print(f"Common S2 + NISAR coverage: {valid.mean():.1%}")

    if not valid.any():
        raise ValueError("No common valid pixels")

    # Optical reference: top 10% of changes
    optical_threshold = float(
        np.quantile(optical_score[valid], 0.90)
    )

    truth_all = valid & (optical_score >= optical_threshold)
    truth = truth_all[valid]

    # --------------------------------------------------
    # NISAR method variants
    # --------------------------------------------------

    radar_difference = late_db - early_db

    variants = {}

    for win in (1, 3, 5, 9, 15):
        smooth = cm.nanfilter(radar_difference, win)

        variants[f"HH absolute, filter {win}x{win}"] = np.abs(smooth)
        variants[f"HH decrease, filter {win}x{win}"] = -smooth
        variants[f"HH increase, filter {win}x{win}"] = smooth

    # --------------------------------------------------
    # Evaluation
    # --------------------------------------------------

    results = {}

    for label, score in variants.items():
        ok = valid & np.isfinite(score)

        if not ok.any():
            continue

        score_values = score[ok]
        truth_values = truth_all[ok]

        if not truth_values.any():
            continue

        best = best_iou(score_values, truth_values)

        results[label] = {
            "AUC": auc(score_values, truth_values),
            "best_IoU": best["IoU"],
            "precision": best["precision"],
            "recall": best["recall"],
            "threshold": best["threshold"],
        }

    if not results:
        raise ValueError("No valid NISAR method variants")

    order = sorted(
        results,
        key=lambda k: -results[k]["best_IoU"]
    )

    print("\nNISAR vs Sentinel-2 optical change")
    print(f"Optical threshold: {optical_threshold:.4f}")

    for label in order:
        result = results[label]

        print(
            f"{label:38s} "
            f"AUC {result['AUC']:.3f} "
            f"IoU {result['best_IoU']:.3f} "
            f"prec {result['precision']:.2f} "
            f"rec {result['recall']:.2f}"
        )

    # --------------------------------------------------
    # Save results
    # --------------------------------------------------

    OUT.mkdir(parents=True, exist_ok=True)

    summary = {
        "reference": "Sentinel-2 optical reflectance change",
        "optical_bands": list(optical_bands),
        "optical_threshold_quantile": 0.90,
        "optical_threshold": optical_threshold,
        "common_valid_fraction": float(valid.mean()),
        "note": (
            "Exploratory agreement between radar and optical "
            "surface changes, not validated glacier retreat."
        ),
        "ranked": {
            label: results[label]
            for label in order
        },
    }

    (OUT / "validation_glacier_methods.json").write_text(
        json.dumps(summary, indent=2)
    )

    # --------------------------------------------------
    # Visualization
    # --------------------------------------------------

    best_label = order[0]
    best_score = variants[best_label]
    best_threshold = results[best_label]["threshold"]

    comparison_valid = valid & np.isfinite(best_score)
    pred = comparison_valid & (best_score >= best_threshold)

    agreement = np.full(
        early_db.shape + (3,),
        0.9,
        dtype="float32"
    )

    agreement[comparison_valid & pred & truth_all] = (0.1, 0.7, 0.2)
    agreement[comparison_valid & pred & ~truth_all] = (0.9, 0.2, 0.2)
    agreement[comparison_valid & ~pred & truth_all] = (0.2, 0.4, 0.9)

    fig, ax = plt.subplots(1, 3, figsize=(18, 6))

    radar_display = np.ma.masked_where(
        ~comparison_valid, best_score
    )
    optical_display = np.ma.masked_where(
        ~comparison_valid, optical_score
    )

    ax[0].imshow(
        radar_display,
        cmap="magma",
        vmin=0,
        vmax=np.nanpercentile(best_score[comparison_valid], 99)
    )
    ax[0].set_title(f"NISAR GCOV change\n{best_label}")

    ax[1].imshow(
        optical_display,
        cmap="magma",
        vmin=0,
        vmax=np.nanpercentile(optical_score[comparison_valid], 99)
    )
    ax[1].set_title("Sentinel-2 optical change")

    ax[2].imshow(agreement)
    ax[2].set_title(
        "Green = both | Red = NISAR only | Blue = S2 only\n"
        f"IoU = {results[best_label]['best_IoU']:.3f}"
    )

    for axis in ax:
        axis.axis("off")

    fig.tight_layout()

    fig.savefig(
        OUT / "VALIDATION_GLACIER_methods.png",
        dpi=110
    )

    plt.close(fig)

    print("\nSaved validation_glacier_methods.json")
    print("Saved VALIDATION_GLACIER_methods.png")

def plot_sentinel2_changes(june, october):
    optical_bands = ("B04", "B8A", "B12")

    valid = np.ones(june["B04"].shape, dtype=bool)
    score = np.zeros(june["B04"].shape, dtype="float32")

    for band in optical_bands:
        before = june[band].astype("float32")
        after = october[band].astype("float32")

        valid &= np.isfinite(before) & np.isfinite(after)
        score += np.nan_to_num((after - before) ** 2, nan=0.0)

    score = np.sqrt(score)
    score[~valid] = np.nan

    threshold = np.quantile(score[valid], 0.90)
    change_mask = valid & (score >= threshold)

    comp = composites(june, october)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    for ax, image, title in zip(
        axes,
        (comp["tc_pre"], comp["tc_post"]),
        ("June 2026", "October 2026"),
    ):
        ax.imshow(image)

        overlay = np.zeros((*change_mask.shape, 4), dtype="float32")
        overlay[change_mask] = [1.0, 0.0, 0.6, 0.55]

        ax.imshow(overlay)
        ax.set_title(f"Sentinel-2 | {title}")
        ax.axis("off")

    fig.suptitle(
        "Sentinel-2 optical changes | Top 10% reflectance differences",
        fontsize=14
    )
    fig.tight_layout()
    fig.savefig(OUT / "SENTINEL2_CHANGES.png", dpi=150)
    plt.close(fig)

    print("Saved SENTINEL2_CHANGES.png")

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    with np.load(FOLDER / "gcov_layers.npz") as z:
        x = z["x"]
        y = z["y"]
        epsg = int(z["epsg"])

    pixel_m = abs(float(x[1] - x[0]))

    # Rasterio grid: upper-left pixel corner
    grid = {
        "x_left": float(x[0] - pixel_m / 2),
        "y_top": float(max(y) + pixel_m / 2),
        "pixel_m": pixel_m,
        "shape": [len(y), len(x)],
        "epsg": epsg,
    }

    # Check orientation before using rasterio
    if y[0] < y[-1]:
        raise ValueError("GCOV y coordinates are not north-up")


    cache_path = FOLDER / "sentinel2_glacier.npz"

    if cache_path.exists():
        print("Loading cached Sentinel-2 data...")

        with np.load(cache_path) as z:
            june = {
                band: z[f"june_{band}"]
                for band in BANDS
            }
            october = {
                band: z[f"october_{band}"]
                for band in BANDS
            }

        june_dates = ["Loaded from cache"]
        october_dates = ["Loaded from cache"]

    else:
        print("Downloading June Sentinel-2...")
        june, june_dates = glacier_s2_mosaic(
            grid, BBOX,
            datetime(2026, 6, 10),
            datetime(2026, 6, 25),
            BANDS,
            max_cloud=80,
        )

        print("Downloading October Sentinel-2...")
        october, october_dates = glacier_s2_mosaic(
            grid, BBOX,
            datetime(2026, 9, 25),
            datetime(2026, 10, 12),
            BANDS,
            max_cloud=80,
        )

        np.savez_compressed(
            cache_path,
            **{f"june_{k}": v for k, v in june.items()},
            **{f"october_{k}": v for k, v in october.items()},
        )



    june_valid = np.isfinite(june["B04"])
    october_valid = np.isfinite(october["B04"])

    common_valid = june_valid & october_valid

    print(f"June coverage: {june_valid.mean():.1%}")
    print(f"October coverage: {october_valid.mean():.1%}")
    print(f"Common coverage: {common_valid.mean():.1%}")


    comp = composites(june, october)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    axes[0].imshow(comp["tc_pre"])
    axes[0].set_title("Sentinel-2 | June 2026")
    axes[0].axis("off")

    axes[1].imshow(comp["tc_post"])
    axes[1].set_title("Sentinel-2 | October 2026")
    axes[1].axis("off")

    fig.tight_layout()
    fig.savefig(OUT / "SENTINEL2_COMPARISON.png", dpi=150)
    plt.close(fig)

    print("June scenes:", june_dates)
    print("October scenes:", october_dates)
    print("Saved Sentinel-2 comparison")
    validate_changes(june, october)
    plot_sentinel2_changes(june, october)


if __name__ == "__main__":
    main()