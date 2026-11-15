"""
focus_area.py -- cut one neighbourhood out of a regional subsidence analysis, at 20 m detail.

  uv run python subsidence_series.py --only silesia        # regional: finds the bowls and confirms them with the second track
  uv run python gis_check.py --only silesia                # mine / mining area for every bowl
  uv run python subsidence_detail.py --only krzyzowice     # 20 m cumulative maps of the neighbourhood
  uv run python focus_area.py --only krzyzowice --source silesia
  uv run python make_timeline.py --only krzyzowice

Keeps only what lies inside the focus case's bbox: bowls (with curves, forecast, mine names), mining-area outlines
and the map frames. The frames come from the 20 m layers; which pixels belong to a confirmed bowl is still decided by
the regional two-track check, so nothing unconfirmed is drawn.
"""
import argparse, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent


def run(name, source, cases, data, out):
    from shapely.geometry import shape, box, mapping
    case = cases[name]; w, s, e, n = case["bbox"]; (out / name).mkdir(parents=True, exist_ok=True)
    reg = np.load(data / source / "subsidence_layers.npz"); det = np.load(data / name / "detail_layers.npz")
    x, y = det["x"], det["y"]
    c = np.clip(np.rint((x - reg["x"][0]) / (reg["x"][1] - reg["x"][0])).astype(int), 0, len(reg["x"]) - 1)
    r = np.clip(np.rint((y - reg["y"][0]) / (reg["y"][1] - reg["y"][0])).astype(int), 0, len(reg["y"]) - 1)
    confirmed = reg["confirmed"][np.ix_(r, c)]
    np.savez_compressed(data / name / "subsidence_layers.npz", x=x, y=y, epsg=int(det["epsg"]), cumulative_cm=det["cumulative_cm"],
                        total_cm=det["cumulative_cm"][-1], confirmed=confirmed, dates=det["dates"], check_dates=reg["check_dates"])
    st = json.loads((out / source / "stats.json").read_text()); gis = json.loads((out / source / "gis_check.json").read_text())
    keep = [i for i, b in enumerate(st["bowls"]) if w <= b["lon"] <= e and s <= b["lat"] <= n]
    st["bowls"] = [st["bowls"][i] for i in keep]; st["case"] = name; st["title"] = case["title"]
    st["region_candidates"], st["region_confirmed"] = st["candidates"], st["confirmed"]
    st["confirmed"] = st["candidates"] = len(keep); st["total_confirmed_area_km2"] = round(sum(b["area_km2"] for b in st["bowls"]), 1)
    (out / name / "stats.json").write_text(json.dumps(st, indent=2, ensure_ascii=False))
    bb = box(w, s, e, n); gis["per_bowl"] = [gis["per_bowl"][i] for i in keep]; gis["bowls"] = len(keep); gis["bowls_inside"] = sum(p["inside"] for p in gis["per_bowl"])
    feats = []
    for f in gis["outlines"]["features"]:
        g = shape(f["geometry"])
        if g.intersects(bb): feats.append({**f, "geometry": mapping(g)})
    gis["outlines"]["features"] = feats
    from shapely.ops import unary_union
    gis["share_of_box_covered"] = round(unary_union([shape(f["geometry"]) for f in feats]).intersection(bb).area / bb.area, 3) if feats else 0.0
    (out / name / "gis_check.json").write_text(json.dumps(gis, ensure_ascii=False))
    print(f"[{name}] kept {len(keep)} of {st['region_confirmed']} confirmed bowls, {len(feats)} mining areas; mining areas cover {gis['share_of_box_covered']*100:.0f}% of this box")
    for b, g in zip(st["bowls"], gis["per_bowl"]): print(f"   {b['max_sink_cm']:5.1f} cm  złoże {g['deposit']:10s} ({b['lon']}, {b['lat']})  forecast 31.12: {b['forecast']['cm'][-1]} cm")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--source", required=True)
    p.add_argument("--data", default=str(HERE / "data")); p.add_argument("--out", default=str(HERE / "output")); A = p.parse_args()
    run(A.only, A.source, json.loads((HERE / "cases.json").read_text()), Path(A.data), Path(A.out))
