from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy import ndimage as ndi

from check_location import composites


NAME = "jakobshavn_glacier"
FOLDER = Path("data") / NAME
OUT = Path("output") / NAME


def detect_ice(bands):
    green = bands["B03"].astype("float32")
    swir = bands["B12"].astype("float32")

    # Approximate snow/ice index using B12
    ndsi = (green - swir) / (green + swir + 1e-6)

    ice = np.isfinite(ndsi) & (ndsi > 0.4)

    # Remove small ice fragments and fill small gaps
    ice = ndi.binary_opening(ice, iterations=2)
    ice = ndi.binary_closing(ice, iterations=3)
    ice = ndi.binary_fill_holes(ice)

    # Keep the largest connected ice region
    labels, n = ndi.label(ice)

    if n == 0:
        return ice, ice

    sizes = np.bincount(labels.ravel())
    sizes[0] = 0

    ice = labels == np.argmax(sizes)

    # Extract boundary
    boundary = ice & ~ndi.binary_erosion(ice)

    return ice, boundary


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    with np.load(FOLDER / "sentinel2_glacier.npz") as z:
        june = {
            band: z[f"june_{band}"]
            for band in ("B03", "B04", "B02", "B8A", "B12")
        }
        october = {
            band: z[f"october_{band}"]
            for band in ("B03", "B04", "B02", "B8A", "B12")
        }

    june_ice, june_boundary = detect_ice(june)
    october_ice, october_boundary = detect_ice(october)

    comp = composites(june, october)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    for ax, image, boundary, title, color in [
        (axes[0], comp["tc_pre"], june_boundary, "June 2026", "red"),
        (axes[1], comp["tc_post"], october_boundary, "October 2026", "lime"),
    ]:
        ax.imshow(image)
        ax.contour(boundary.astype(float), levels=[0.5],
                   colors=color, linewidths=1.5)
        ax.set_title(title)
        ax.axis("off")

    fig.tight_layout()
    fig.savefig(OUT / "GLACIER_TERMINUS.png", dpi=150)
    plt.close(fig)

    print("Saved GLACIER_TERMINUS.png")


if __name__ == "__main__":
    main()