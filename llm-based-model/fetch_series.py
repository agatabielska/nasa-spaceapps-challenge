"""
fetch_series.py -- stream a chain of GUNW pairs (only the 80 m unwrapped layers) for a time-series case.

  uv run python fetch_series.py --only silesia                 # main track  -> data/<case>/a_00.npz ...
  uv run python fetch_series.py --only silesia --check         # second track -> data/<case>/b_00.npz ...
"""
import argparse, json, time
from pathlib import Path
import nisar_io as nio

HERE = Path(__file__).parent
if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--check", action="store_true")
    p.add_argument("--data", default=str(HERE / "data")); A = p.parse_args()
    c = json.loads((HERE / "cases.json").read_text())[A.only]
    for i, g in enumerate(c["gunw_series_check" if A.check else "gunw_series"]):
        path = Path(A.data) / A.only / f"{'b' if A.check else 'a'}_{i:02d}.npz"; t = time.time()
        if path.exists(): continue
        try:
            nio.cached(path, nio.read_gunw, nio.granule_url(g), c["bbox"], wrapped=False)
            print(f"{path.name}: {g.split('_')[11][:8]} -> {g.split('_')[13][:8]}  {time.time()-t:.0f}s", flush=True)
        except Exception as e: print(f"{path.name}: FAILED {e}", flush=True)
