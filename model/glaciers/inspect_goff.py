
import h5py
import asf_search as asf

from glacier_products import PRODUCTS
import nisar_io as nio

granule = PRODUCTS["ascending"]["early"]

results = asf.granule_search([granule])

if not results:
    raise RuntimeError("GOFF product not found")

item = results[0]
url = item.properties["url"]

print("Product:", granule)
print("URL:", url)

# Use the existing project's remote HDF5 reader.
with nio.open_h5(url) as f:
    print("\nGOFF datasets:\n")

    def inspect(name, obj):
        if isinstance(obj, h5py.Dataset):
            print(
                name,
                "| shape:", obj.shape,
                "| dtype:", obj.dtype,
                "| units:", obj.attrs.get("units", "unknown")
            )


    import numpy as np

    base = "/science/LSAR/GOFF/grids/frequencyA/pixelOffsets"

    print("\n--- GRID INFORMATION ---")

    epsg = f[f"{base}/projection"][()]
    x = f[f"{base}/xCoordinates"][:]
    y = f[f"{base}/yCoordinates"][:]

    print("EPSG:", epsg)
    print("X range:", x.min(), x.max())
    print("Y range:", y.min(), y.max())
    print("X spacing:", np.median(np.diff(x)))
    print("Y spacing:", np.median(np.diff(y)))

    print("\n--- TEMPORAL BASELINE ---")
    baseline = f[
        "/science/LSAR/GOFF/metadata/orbit/temporalBaseline"
    ][()]
    print("Baseline:", baseline, "days")

    print("\n--- LAYER PARAMETERS ---")

    params = (
        "/science/LSAR/GOFF/metadata/"
        "processingInformation/parameters/"
        "pixelOffsets/frequencyA"
    )

    for layer in ("layer1", "layer2", "layer3"):
        print(f"\n{layer}")

        for name in (
            "alongTrackWindowSize",
            "slantRangeWindowSize",
            "alongTrackSearchWindowSize",
            "slantRangeSearchWindowSize",
        ):
            value = f[f"{params}/{layer}/{name}"][()]
            print(f"  {name}: {value}")

    # f["/science/LSAR/GOFF"].visititems(inspect)
