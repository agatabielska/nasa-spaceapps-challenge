
import numpy as np
import nisar_io as nio

GOFF = "/science/LSAR/GOFF/grids/frequencyA/pixelOffsets"


def read_goff_subset(url, bbox, layer="layer1"):
    with nio.open_h5(url) as f:
        grid = f[GOFF]

        # Convert geographic bbox into raster indices
        sy, sx, x, y, epsg = nio._window(grid, bbox)

        layer_group = grid[f"HH/{layer}"]

        along = layer_group["alongTrackOffset"][sy, sx].astype("float32")
        slant = layer_group["slantRangeOffset"][sy, sx].astype("float32")
        snr = layer_group["snr"][sy, sx].astype("float32")
        correlation = layer_group["correlationSurfacePeak"][sy, sx].astype("float32")

        baseline = float(
            f["/science/LSAR/GOFF/metadata/orbit/temporalBaseline"][()]
        )

        # Respect HDF5 fill values
        for name, arr in [
            ("alongTrackOffset", along),
            ("slantRangeOffset", slant),
            ("snr", snr),
            ("correlationSurfacePeak", correlation),
        ]:
            ds = layer_group[name]
            fill = ds.attrs.get("_FillValue", ds.fillvalue)

            arr[~np.isfinite(arr)] = np.nan
            if fill is not None:
                arr[arr == fill] = np.nan

        # Orient the arrays north-up
        if y[0] < y[-1]:
            y = y[::-1]
            along = along[::-1]
            slant = slant[::-1]
            snr = snr[::-1]
            correlation = correlation[::-1]

        return {
            "along": along,
            "slant": slant,
            "snr": snr,
            "correlation": correlation,
            "x": x,
            "y": y,
            "epsg": epsg,
            "baseline": baseline,
        }
