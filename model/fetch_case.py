"""
fetch_case.py -- download (stream) the NISAR windows listed in cases.json into data/<case>/*.npz

  uv run python fetch_case.py                 # every case
  uv run python fetch_case.py --only etna

Only the pixels inside each case's bbox are transferred (see nisar_io.py). Re-running skips what is cached.
"""
import argparse, json, time
from pathlib import Path
import numpy as np
import nisar_io as nio

HERE = Path(__file__).parent


def fetch(name, case, root):
    out = root / name
    for key in ("gcov_before", "gcov_after", "gunw", "gunw_ref"):
        gran = case.get(key)
        if not gran: continue
        path = out / f"{key}.npz"
        if path.exists(): print(f"[{name}] {key}: cached"); continue
        t = time.time(); url = nio.granule_url(gran)
        reader = nio.read_gcov if key.startswith("gcov") else nio.read_gunw
        try:
            d = nio.cached(path, reader, url, case["bbox"])
        except ValueError as e:
            print(f"[{name}] {key}: SKIPPED ({e})"); continue
        main = d["HHHH"] if "HHHH" in d else d["w_coherence"]
        print(f"[{name}] {key}: {main.shape[1]}x{main.shape[0]} px, {np.isfinite(main).mean()*100:.0f}% valid, "
              f"{path.stat().st_size/1e6:.1f} MB on disk, {time.time()-t:.0f}s")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only"); p.add_argument("--cases", default=str(HERE / "cases.json"))
    p.add_argument("--data", default=str(HERE / "data"))
    a = p.parse_args()
    for n, c in json.loads(Path(a.cases).read_text()).items():
        if a.only and n != a.only: continue
        fetch(n, c, Path(a.data))
