"""
nisar_before_after.py  --  input: bounding box + event date  ->  output: BEFORE.png and AFTER.png
Uses NISAR L2 GCOV (geocoded backscatter) from ASF. Same track/frame/direction for both images.

Usage examples
  python nisar_before_after.py --events events.json --only venezuela --dry-run   # search only, no download
  python nisar_before_after.py --events events.json --only venezuela             # full run
  python nisar_before_after.py --bbox -5.2 40.2 -4.4 40.7 --date 2026-07-22 --name my_fire --pol HVHV
  python nisar_before_after.py --events events.json --only nepal --download       # force full download
  python nisar_before_after.py --inspect path/to/file.h5                         # print HDF5 layout (file or URL)

Install: uv sync
Login:   RECOMMENDED: set env EDL_TOKEN (Earthdata profile -> Generate Token). This also enables STREAMING:
         only the needed chunks are read over HTTPS, instead of downloading whole multi-GB files.
         Without a token: set EDL_USERNAME / EDL_PASSWORD (or be prompted) -> full download with size confirmation.

STATUS: search/download code follows the official ASF NISAR Cookbook example.
Selection logic and HDF5 reading/plotting were tested on SYNTHETIC data only (layout assumed from the NISAR
GCOV spec: lines marked CHECK). Run --inspect on your first real file to confirm.
"""
import argparse, json, os, re, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

GRID = "/science/LSAR/GCOV/grids/frequencyA"      # CHECK with --inspect
MAX_PX = 1500                                      # output image max size (block-averaged)

# ------------------------------------------------------------------ search
def parse_name(url):
    """NISAR_L2_PR_GCOV_006_172_A_008_2005_DHDH_A_20251204T024618_20251204T024653_X05007_N_F_J_001.h5"""
    t = Path(url).stem.split("_")
    return {"url": url, "config": t[2], "track": t[5], "direction": t[6], "frame": t[7],
            "start": datetime.strptime(t[11], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc),
            "crid": t[13]}

def search_gcov(bbox, event_date, window_days, session):
    """Returns (urls, footprints) where footprints maps file stem -> shapely polygon (or {} if unavailable)."""
    import asf_search as asf
    x0, y0, x1, y1 = bbox
    wkt = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
    opts = asf.ASFSearchOptions(**{
        "maxResults": 250, "intersectsWith": wkt,
        "start": event_date - timedelta(days=window_days), "end": event_date + timedelta(days=window_days),
        "processingLevel": ["GCOV"], "dataset": ["NISAR"], "session": session})
    resp = asf.search(opts=opts)
    urls = resp.find_urls(extension=".h5", pattern=r"^(?!.*QA_STATS).*", directAccess=False)
    geoms = {}
    try:
        from shapely.geometry import shape
        texts = [(str(p.properties), shape(p.geometry)) for p in resp]
        for u in urls:
            stem = Path(u).stem
            for t, g in texts:
                if stem in t: geoms[stem] = g; break
    except Exception as e:
        print(f"  (could not read scene footprints: {e}; ranking by time gap only)")
    return urls, geoms

def coverage(geom, bbox):
    from shapely.geometry import box
    bb = box(*bbox)
    return float(geom.intersection(bb).area / bb.area)

def choose_pair(urls, event_date, after_from=None, bbox=None, geoms=None, min_cov=0.5, info=None, track=None):
    """Pick before/after scenes from the SAME track+frame+direction (+same maturity).
    Prefer groups whose footprint covers >= min_cov of the bbox (then smallest time gap); else best coverage."""
    scenes = {}
    for u in urls:                                   # drop duplicates of the same acquisition (keep newest CRID)
        s = parse_name(u); k = (s["config"], s["track"], s["frame"], s["direction"], s["start"])
        if k not in scenes or s["crid"] > scenes[k]["crid"]: scenes[k] = s
    day0 = event_date.replace(hour=0, minute=0, second=0, microsecond=0)
    groups = {}
    for s in scenes.values():
        groups.setdefault((s["config"], s["track"], s["frame"], s["direction"]), []).append(s)
    cands = []
    for k, lst in groups.items():
        if track and k[1] != str(track).zfill(3): continue
        a0 = max(day0 + timedelta(days=1), after_from) if after_from else day0 + timedelta(days=1)  # event day is ambiguous
        before = [s for s in lst if s["start"] < day0]; after = [s for s in lst if s["start"] >= a0]
        if not (before and after): continue
        b = max(before, key=lambda s: s["start"]); a = min(after, key=lambda s: s["start"])
        gap = (a["start"] - b["start"]).total_seconds() / 86400
        cov = None
        if geoms and bbox:
            cs = [coverage(geoms[x["url"].split("/")[-1][:-3]], bbox) for x in (b, a) if x["url"].split("/")[-1][:-3] in geoms]
            cov = min(cs) if cs else None
        cands.append({"cov": cov, "gap": gap, "b": b, "a": a, "key": k})
    if info is not None:
        for c in sorted(cands, key=lambda c: (-(c["cov"] or 0), c["gap"]))[:6]:
            kk = c["key"]; cv = "n/a" if c["cov"] is None else f"{c['cov']*100:.0f}%"
            info.append(f"    track {kk[1]} frame {kk[2]} {kk[3]}: covers {cv} of bbox, gap {c['gap']:.0f} d, "
                        f"{c['b']['start']:%d %b} -> {c['a']['start']:%d %b}")
    if not cands: return None
    known = [c for c in cands if c["cov"] is not None]
    if known:
        good = [c for c in known if c["cov"] >= min_cov]
        best = min(good, key=lambda c: c["gap"]) if good else max(known, key=lambda c: c["cov"])
    else:
        best = min(cands, key=lambda c: c["gap"])
    return best["b"], best["a"]

# ------------------------------------------------------------------ read + crop
from contextlib import contextmanager

@contextmanager
def open_h5(src, token=None):
    """Open a local path OR an https URL. URLs are read with HTTP range requests (only needed chunks)."""
    import h5py
    if str(src).startswith("http"):
        import fsspec
        hdr = {"Authorization": f"Bearer {token}"} if token else {}
        fs = fsspec.filesystem("http", client_kwargs={"headers": hdr})
        with fs.open(str(src), "rb", block_size=2 * 2**20, cache_type="blockcache",
                     cache_options={"maxblocks": 64}) as fobj, h5py.File(fobj, "r") as f:
            yield f
    else:
        with h5py.File(src, "r") as f:
            yield f

def inspect(path, token=None):
    with open_h5(path, token) as f: f.visititems(lambda n, o: print(n, getattr(o, "shape", "")))

def remote_size_mb(url, session):
    try:
        r = session.head(url, allow_redirects=True, timeout=30)
        return int(r.headers["Content-Length"]) / 1e6
    except Exception:
        return None

def read_window(h5_path, bbox, pol, token=None):
    from pyproj import Transformer
    with open_h5(h5_path, token) as f:
        g = f[GRID]
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        epsg = int(g["projection"][()]) if g["projection"].shape == () else int(g["projection"].attrs["epsg_code"])  # CHECK
        tr = Transformer.from_crs(4326, epsg, always_xy=True)
        xs, ys = zip(*[tr.transform(lon, lat) for lon in (bbox[0], bbox[2]) for lat in (bbox[1], bbox[3])])
        ix = np.where((x >= min(xs)) & (x <= max(xs)))[0]; iy = np.where((y >= min(ys)) & (y <= max(ys)))[0]
        if len(ix) == 0 or len(iy) == 0: raise ValueError("bbox does not overlap this scene")
        ds = g[pol]
        arr = ds[iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1].astype("float64")
        flip = y[0] < y[-1]
        dx = float(abs(x[1] - x[0])); dy = float(abs(y[1] - y[0]))
        ytop = float(y[iy[-1]] if flip else y[iy[0]])
        geo = {"epsg": epsg, "x_left": float(x[ix[0]]) - dx / 2, "y_top": ytop + dy / 2}
    return (arr[::-1] if flip else arr), dx, geo

def to_db(a, block):
    a = np.where(np.isfinite(a) & (a > 0), a, np.nan)
    if block > 1:                                            # block-average (also reduces speckle)
        h, w = (a.shape[0] // block) * block, (a.shape[1] // block) * block
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)      # all-NaN blocks (outside the scene footprint)
            a = np.nanmean(a[:h, :w].reshape(h // block, block, w // block, block), axis=(1, 3))
    return 10 * np.log10(a)

def safe_imsave(path, arr, **kw):
    """Save a PNG; if Windows refuses (file open in a viewer / OneDrive lock), save under a new name instead."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    path = Path(path)
    try:
        plt.imsave(path, arr, **kw); return path
    except OSError as e:
        alt = path.with_name(f"{path.stem}_{datetime.now():%H%M%S}{path.suffix}")
        print(f"  WARNING: could not write {path} ({e}). Close any viewer showing it. Trying {alt.name} ...")
        plt.imsave(alt, arr, **kw); return alt

def make_images(h5_before, h5_after, bbox, pol, outdir, token=None, block=None, thresh=-2.0):
    """Writes BEFORE, AFTER, DIFF (after-before, dB) and CHANGE overlay (red = backscatter decrease <= thresh dB)."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    b, dx, geo = read_window(h5_before, bbox, pol, token); a, _, _ = read_window(h5_after, bbox, pol, token)
    h, w = min(b.shape[0], a.shape[0]), min(b.shape[1], a.shape[1]); b, a = b[:h, :w], a[:h, :w]
    block = block or max(1, math.ceil(max(h, w) / MAX_PX))
    b, a = to_db(b, block), to_db(a, block)
    ok = np.isfinite(b) & np.isfinite(a)
    if ok.sum() == 0: raise ValueError("no valid pixels: bbox is outside the scene footprint or data are empty")
    both = np.concatenate([b[ok], a[ok]]); vmin, vmax = np.percentile(both, [2, 98])   # same stretch for both
    saved = []
    saved.append(safe_imsave(outdir / "BEFORE.png", b, cmap="gray", vmin=vmin, vmax=vmax))
    saved.append(safe_imsave(outdir / "AFTER.png", a, cmap="gray", vmin=vmin, vmax=vmax))
    d = np.where(ok, a - b, np.nan); v = float(np.nanpercentile(np.abs(d), 98))
    saved.append(safe_imsave(outdir / "DIFF_after_minus_before.png", d, cmap="RdBu_r", vmin=-max(v, 1.0), vmax=max(v, 1.0)))
    g = np.clip((np.nan_to_num(a, nan=vmin) - vmin) / (vmax - vmin), 0, 1)
    rgb = np.dstack([g, g, g]); dec = ok & (d <= thresh)
    rgb[dec] = 0.5 * rgb[dec] + 0.5 * np.array([1.0, 0.0, 0.0])
    saved.append(safe_imsave(outdir / "CHANGE_overlay.png", rgb))
    try:   # georeferenced array for validation scripts
        np.save(outdir / "diff_db.npy", d.astype("float32"))
        (outdir / "grid.json").write_text(json.dumps({**geo, "pixel_m": dx * block, "shape": [int(d.shape[0]), int(d.shape[1])]}))
    except OSError as e: print(f"  WARNING: could not write diff_db.npy/grid.json ({e})")
    px_km2 = (dx * block / 1000.0) ** 2
    return {"shape": [int(b.shape[0]), int(b.shape[1])], "block": block, "pixel_m": dx * block,
            "valid_fraction": float(ok.mean()), "mean_db_before": float(np.nanmean(b[ok])), "mean_db_after": float(np.nanmean(a[ok])),
            "diff_abs_p98_dB": v, "thresh_dB": thresh,
            "area_decrease_km2": float((ok & (d <= thresh)).sum() * px_km2),
            "area_increase_km2": float((ok & (d >= -thresh)).sum() * px_km2), "files": [p.name for p in saved], "db_stretch": [float(vmin), float(vmax)]}

# ------------------------------------------------------------------ main
def run(name, bbox, date_str, window, pol, dry, outroot, force_download=False, yes=False, after_from=None, block=None, thresh=-2.0, min_cov=0.5, track=None):
    import asf_search as asf
    event_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    token = os.environ.get("EDL_TOKEN")
    session = asf.ASFSession()
    if token: session.auth_with_token(token)
    else:
        user = os.environ.get("EDL_USERNAME") or input("Earthdata username: ")
        pwd = os.environ.get("EDL_PASSWORD") or __import__("getpass").getpass("Earthdata password: ")
        session.auth_with_creds(user, pwd)
    urls, geoms = search_gcov(bbox, event_date, window, session)
    print(f"[{name}] {len(urls)} GCOV files found in +/-{window} days")
    af = datetime.strptime(after_from, "%Y-%m-%d").replace(tzinfo=timezone.utc) if after_from else None
    info = []
    pair = choose_pair(urls, event_date, af, bbox, geoms, min_cov, info, track)
    if info: print("  Candidate scene groups (coverage of YOUR bbox, best first):"); print(*info, sep="\n")
    if pair is None:
        print(f"[{name}] NO usable before/after pair on the same track/frame. Try a bigger --window, "
              "check Vertex, or pick another event."); return
    b, a = pair
    for lab, s in (("BEFORE", b), ("AFTER ", a)):
        mb = remote_size_mb(s["url"], session)
        print(f"  {lab}: {s['start']:%Y-%m-%d %H:%M} UTC  track {s['track']} frame {s['frame']} {s['direction']} "
              f"[{s['config']}]  full file: {'%.0f MB' % mb if mb else 'size unknown'}\n          {s['url']}")
    if geoms and not any(c for c in info if "covers" in c and int(c.split("covers ")[1].split("%")[0] or 0) >= min_cov * 100):
        print("  WARNING: no scene covers most of your bbox. Shift/shrink the bbox into the covered area, or accept partial data.")
    if b["config"] != a["config"]: print("  WARNING: different data maturity between before/after")
    if dry: return
    out = Path(outroot) / name; out.mkdir(parents=True, exist_ok=True)
    stream = bool(token) and not force_download
    if stream:
        print("STREAMING mode: reading only the chunks inside your bbox (no full download).")
        hb, ha = b["url"], a["url"]
    else:
        hb, ha = out / Path(b["url"]).name, out / Path(a["url"]).name
        todo = [u for u, p in ((b["url"], hb), (a["url"], ha)) if not p.exists()]
        if todo:
            if not yes and input(f"Download {len(todo)} FULL file(s) now? [y/N] ").lower() != "y": return
            asf.download_urls(todo, str(out), session=session, processes=2)
        else: print("Files already downloaded, reusing them.")
    stats = make_images(hb, ha, bbox, pol, out, token if stream else None, block, thresh)
    meta = {"name": name, "bbox_lonlat": bbox, "event_date": date_str, "polarization": pol, "mode": "stream" if stream else "download",
            "before": {k: str(v) for k, v in b.items()}, "after": {k: str(v) for k, v in a.items()}, **stats}
    try: (out / "meta.json").write_text(json.dumps(meta, indent=2))
    except OSError as e: print(f"  WARNING: could not write meta.json ({e})")
    print(json.dumps(stats, indent=2))
    print(f"Done -> {out}: " + ", ".join(stats["files"]))
    if stats["valid_fraction"] < 0.5: print(f"WARNING: only {stats['valid_fraction']*100:.0f}% of the box has data. Images are mostly empty: shift the bbox (see candidate list above).")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--events"); p.add_argument("--only"); p.add_argument("--bbox", nargs=4, type=float)
    p.add_argument("--date"); p.add_argument("--name", default="event"); p.add_argument("--window", type=int, default=30)
    p.add_argument("--pol", default="HHHH", help="HHHH or HVHV"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--diff", action="store_true", help="(ignored: diff is always written)"); p.add_argument("--out", default="output"); p.add_argument("--inspect")
    p.add_argument("--download", action="store_true", help="force full download instead of streaming")
    p.add_argument("--yes", action="store_true", help="skip the download confirmation")
    p.add_argument("--after-from", help="YYYY-MM-DD: only use 'after' scenes on/after this date")
    p.add_argument("--block", type=int, help="averaging block in pixels (default auto; bigger = smoother diff)")
    p.add_argument("--thresh", type=float, default=-2.0, help="dB decrease counted as change (default -2)")
    p.add_argument("--track", help="force a relative-orbit track, e.g. 087 (see candidate list)")
    p.add_argument("--min-coverage", type=float, default=0.5, help="min share of bbox a scene must cover (default 0.5)")
    A = p.parse_args()
    if A.inspect: inspect(A.inspect, os.environ.get("EDL_TOKEN"))
    elif A.events:
        ev = json.loads(Path(A.events).read_text())
        for n, e in ev.items():
            if A.only and n != A.only: continue
            run(n, e["bbox"], e["date"], e.get("window_days", A.window), e.get("pol", A.pol), A.dry_run, A.out, A.download, A.yes, A.after_from or e.get("after_from"), A.block, A.thresh, A.min_coverage, A.track or e.get("track"))
    else:
        run(A.name, A.bbox, A.date, A.window, A.pol, A.dry_run, A.out, A.download, A.yes, A.after_from, A.block, A.thresh, A.min_coverage, A.track)