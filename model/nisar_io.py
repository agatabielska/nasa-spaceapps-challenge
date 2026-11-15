"""
nisar_io.py -- read small windows of NISAR L2 GCOV / GUNW granules straight from ASF (no full download).

A granule is 1.5-8 GB. HDF5 is chunked, so we open it over HTTPS with range requests and read only the
chunks that fall inside the bounding box (tens of MB). The window is cached as a compressed .npz in
data/<case>/ (git-ignored), so every later run is offline and instant.

Login: put an Earthdata token in ~/.edl_token or in the EDL_TOKEN env variable
       (urs.earthdata.nasa.gov -> profile -> Generate Token).

Layout verified on real files (Nov 2026, CRID P05023):
  GCOV  /science/LSAR/GCOV/grids/frequencyA/{HHHH,HVHV,mask,xCoordinates,yCoordinates,projection}
  GUNW  /science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/{unwrappedPhase,coherenceMagnitude,
        connectedComponents,ionospherePhaseScreen}                              (80 m posting)
        /science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/HH/{coherenceMagnitude,wrappedInterferogram}  (20 m)
"""
import json, os, urllib.request
from contextlib import contextmanager
from pathlib import Path
import numpy as np

GCOV = "/science/LSAR/GCOV/grids/frequencyA"
GUNW = "/science/LSAR/GUNW/grids/frequencyA"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"


def token():
    t = os.environ.get("EDL_TOKEN")
    p = Path.home() / ".edl_token"
    if not t and p.exists(): t = p.read_text().strip()
    if not t: raise SystemExit("No Earthdata token: set EDL_TOKEN or write it to ~/.edl_token")
    return t


def granule_url(name):
    """Granule name (no extension) -> https URL of its .h5 file, looked up in NASA CMR."""
    prod = "GCOV" if "_GCOV_" in name else "GUNW"
    for coll in (f"NISAR_L2_{prod}_PROVISIONAL_V1", f"NISAR_L2_{prod}_V1", f"NISAR_L2_{prod}_BETA_V1"):
        items = json.load(urllib.request.urlopen(f"{CMR}?short_name={coll}&granule_ur={name}"))["items"]
        for it in items:
            for r in it["umm"]["RelatedUrls"]:
                u = r["URL"]
                if u.startswith("https") and u.endswith(".h5") and "QA_STATS" not in u: return u
    raise ValueError(f"granule not found in CMR: {name}")


@contextmanager
def open_h5(src):
    """Open a local path or an https URL (URL = HTTP range requests, only the needed chunks are fetched)."""
    import h5py
    if str(src).startswith("http"):
        import fsspec
        fs = fsspec.filesystem("http", client_kwargs={"headers": {"Authorization": f"Bearer {token()}"}})
        with fs.open(str(src), "rb", block_size=4 * 2**20, cache_type="blockcache",
                     cache_options={"maxblocks": 128}) as fo, h5py.File(fo, "r") as f:
            yield f
    else:
        with h5py.File(src, "r") as f:
            yield f


def _window(g, bbox):
    """Index window of group g (has xCoordinates/yCoordinates/projection) covering a lon/lat bbox."""
    from pyproj import Transformer
    x, y = g["xCoordinates"][:], g["yCoordinates"][:]
    epsg = int(g["projection"][()])
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = zip(*[tr.transform(lon, lat) for lon in (bbox[0], bbox[2]) for lat in (bbox[1], bbox[3])])
    ix = np.where((x >= min(xs)) & (x <= max(xs)))[0]
    iy = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    if len(ix) == 0 or len(iy) == 0: raise ValueError("bbox does not overlap this scene")
    sy, sx = slice(iy[0], iy[-1] + 1), slice(ix[0], ix[-1] + 1)
    return sy, sx, x[sx], y[sy], epsg


def _north_up(a, y):
    return (a[::-1], y[::-1]) if y[0] < y[-1] else (a, y)


def block_mean(a, k):
    """k x k block average ignoring NaN (for SAR power this is multilooking: less speckle)."""
    if k <= 1: return a
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3))


def read_gcov(src, bbox, target_m=20.0):
    """Backscatter (linear gamma0 power) for every polarisation, multilooked to ~target_m posting."""
    with open_h5(src) as f:
        g = f[GCOV]
        sy, sx, x, y, epsg = _window(g, bbox)
        pols = [p.decode() for p in g["listOfCovarianceTerms"][:] if len(p) == 4 and p[:2] == p[2:]]
        dx = float(abs(x[1] - x[0])); k = max(1, int(round(target_m / dx)))
        out = {}
        valid = g["mask"][sy, sx]
        valid = (valid > 0) & (valid < 255)                    # 0 = no data, 255 = fill
        for p in pols:
            a = g[p][sy, sx].astype("float32")
            a[~valid | ~np.isfinite(a) | (a <= 0)] = np.nan
            a, yy = _north_up(a, y)
            out[p] = block_mean(a, k).astype("float32")
        h, w = out[pols[0]].shape
        xx = x[: w * k].reshape(w, k).mean(1); yy = yy[: h * k].reshape(h, k).mean(1)
    return {**out, "x": xx, "y": yy, "epsg": epsg, "pixel_m": dx * k}


def read_gunw(src, bbox, wrapped=True):
    """Interferogram layers: 80 m unwrapped phase (+ quality layers) and, if wrapped=True, 20 m coherence / wrapped phase."""
    with open_h5(src) as f:
        out = {"wavelength_m": 299792458.0 / float(f[GUNW]["centerFrequency"][()])}
        u = f[GUNW]["unwrappedInterferogram"]; pol = sorted(k for k in u if k in ("HH", "VV"))[0]
        sy, sx, x, y, epsg = _window(u[pol], bbox)
        for name in ("unwrappedPhase", "coherenceMagnitude", "connectedComponents", "ionospherePhaseScreen"):
            a, yy = _north_up(u[pol][name][sy, sx], y); out["u_" + name] = a
        out.update(u_x=x, u_y=yy, epsg=epsg, u_pixel_m=float(abs(x[1] - x[0])))
        out["pol"] = pol
        if not wrapped: return out                               # time series need only the small 80 m layers
        w = f[GUNW]["wrappedInterferogram"]
        sy, sx, x, y, _ = _window(w[pol], bbox)
        coh, yy = _north_up(w[pol]["coherenceMagnitude"][sy, sx], y)
        ifg, _ = _north_up(w[pol]["wrappedInterferogram"][sy, sx], y)
        out.update(w_coherence=coh.astype("float32"), w_phase=np.angle(ifg).astype("float32"),
                   w_x=x, w_y=yy, w_pixel_m=float(abs(x[1] - x[0])), pol=pol)
    return out


def cached(path, fn, *args, **kw):
    """Run fn(*args) once and keep the result as .npz; later calls load the file."""
    path = Path(path)
    if path.exists():
        with np.load(path, allow_pickle=False) as z: return {k: (z[k].item() if z[k].shape == () else z[k]) for k in z.files}
    d = fn(*args, **kw); path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **d)
    return d
