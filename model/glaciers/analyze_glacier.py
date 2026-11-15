
from pathlib import Path

import asf_search as asf
import numpy as np

from glacier_products import PRODUCTS
from glacier_io import read_goff_subset

# Initial area around Sermeq Kujalleq / Jakobshavn
# [min_lon, min_lat, max_lon, max_lat]
BBOX = [-50.6, 68.9, -49.2, 69.4]

granule = PRODUCTS["ascending"]["early"]

results = asf.granule_search([granule])
if not results:
    raise RuntimeError("GOFF product not found")

url = results[0].properties["url"]

print("Reading:", granule)

data = read_goff_subset(url, BBOX, layer="layer1")

print("EPSG:", data["epsg"])
print("Shape:", data["along"].shape)
print("Baseline:", data["baseline"], "days")

for name in ("along", "slant", "snr", "correlation"):
    arr = data[name]
    valid = np.isfinite(arr)

    print(f"\n{name}")
    print("Valid pixels:", valid.sum(), "/", arr.size)

    if valid.any():
        print("Min:", np.nanmin(arr))
        print("Max:", np.nanmax(arr))
        print("Median:", np.nanmedian(arr))

output = Path("data/glacier")
output.mkdir(parents=True, exist_ok=True)

np.savez_compressed(
    output / "ascending_early_layer1.npz",
    **data,
)

print("\nSaved:", output / "ascending_early_layer1.npz")
