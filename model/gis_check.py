"""
gis_check.py -- compare the confirmed subsidence bowls with official mining-area polygons (independent GIS data).

  uv run python gis_check.py --only silesia

Source: MIDAS database of the Polish Geological Institute (PIG-PIB), layer "obszary górnicze" = the area in which a
mine is licensed to extract. Downloaded once through the public ArcGIS REST service into data/<case>/gis/.
The polygons are licence boundaries, NOT the tunnels: plans of the workings (longwall panels) are not public.

Writes output/<case>/gis_check.json (mine name for every bowl, share of bowls inside coal mining areas and the
share expected by chance) and MAPA_obszary_gornicze.jpg.
"""
import argparse, json, subprocess
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
URL = "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/midas/MapServer/1/query"


def mining_areas(folder, bbox):
    f = folder / "gis" / "midas_1.geojson"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-s", "-m", "120", "-G", URL, "--data-urlencode", "geometry=" + ",".join(map(str, bbox)),
                        "--data-urlencode", "geometryType=esriGeometryEnvelope", "--data-urlencode", "inSR=4326",
                        "--data-urlencode", "spatialRel=esriSpatialRelIntersects", "--data-urlencode", "outFields=*",
                        "--data-urlencode", "outSR=4326", "--data-urlencode", "f=geojson", "-o", str(f)], check=True)
    return json.loads(f.read_text())["features"]


def run(name, case, data, out):
    from shapely.geometry import shape, Point, box, mapping
    from shapely.ops import unary_union
    stats = json.loads((out / name / "stats.json").read_text())
    feats = [f for f in mining_areas(data / name, case["bbox"]) if "WĘGLE KAMIENNE" in (f["properties"]["KOPALINA"] or "").upper()]
    coal = [(f["properties"], shape(f["geometry"]).buffer(0)) for f in feats]
    bb = box(*case["bbox"]); cover = unary_union([g for _, g in coal]).intersection(bb).area / bb.area
    rows, used = [], {}
    for b in stats["bowls"]:
        pt = Point(b["lon"], b["lat"]); inside = [(p, g) for p, g in coal if g.contains(pt)]
        mine = sorted({(p["NAZWA_ZLOZA"] or "").strip() for p, _ in inside}); area = sorted({p["NAZWA_OG"].strip().split(" od ")[0] for p, _ in inside})
        rows.append({"lon": b["lon"], "lat": b["lat"], "near": b["near"], "max_sink_cm": b["max_sink_cm"], "inside": bool(inside),
                     "deposit": ", ".join(mine) or None, "mining_area": ", ".join(area) or None})
        for p, g in inside: used[p["NAZWA_OG"].strip().split(" od ")[0]] = g
    n, k = len(rows), sum(r["inside"] for r in rows)
    res = {"source": "PIG-PIB MIDAS, obszary górnicze (węgle kamienne), status aktualny", "coal_mining_areas_in_box": len({p["NAZWA_OG"].strip().split(" od ")[0] for p, _ in coal}),
           "share_of_box_covered": round(cover, 3), "bowls": n, "bowls_inside": k,
           "expected_inside_by_chance": round(cover * n, 1), "probability_all_by_chance": float(f"{cover ** k:.1e}") if k == n else None, "per_bowl": rows,
           "outlines": {"type": "FeatureCollection", "features": [
               {"type": "Feature", "properties": {"name": nm, "active": nm in used}, "geometry": mapping(unary_union([g for p, g in coal if p["NAZWA_OG"].strip().split(" od ")[0] == nm]).simplify(0.0004))}
               for nm in sorted({p["NAZWA_OG"].strip().split(" od ")[0] for p, _ in coal})]}}
    (out / name / "gis_check.json").write_text(json.dumps(res, ensure_ascii=False))
    print(f"[{name}] {k} of {n} bowls lie inside a coal mining area; those areas cover {cover*100:.0f}% of the box "
          f"(by chance we would expect {cover*n:.1f}).")
    for r in rows[:10]: print(f"   {r['max_sink_cm']:5.1f} cm  near {r['near']:20s} -> złoże {r['deposit']}  (OG {r['mining_area']})")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    z = np.load(data / name / "subsidence_layers.npz")
    from pyproj import Transformer
    inv = Transformer.from_crs(int(z["epsg"]), 4326, always_xy=True)
    fig, ax = plt.subplots(figsize=(15, 10.5), facecolor="#0b1420"); ax.set_facecolor("#0b1420")
    for ft in res["outlines"]["features"]:
        g = shape(ft["geometry"]); col = "#7fe0d8" if ft["properties"]["active"] else "#3d5670"
        for poly in (g.geoms if hasattr(g, "geoms") else [g]):
            xs, ys = poly.exterior.xy; ax.fill(xs, ys, color=col, alpha=0.10 if ft["properties"]["active"] else 0.04); ax.plot(xs, ys, color=col, lw=1.3 if ft["properties"]["active"] else 0.7)
        if ft["properties"]["active"]:
            c = g.representative_point(); ax.text(c.x, c.y, ft["properties"]["name"], color="#bfeee9", fontsize=8.5, ha="center")
    sc = ax.scatter([r["lon"] for r in rows], [r["lat"] for r in rows], c=[r["max_sink_cm"] for r in rows], cmap="inferno", vmin=0, vmax=55,
                    s=[40 + 6 * r["max_sink_cm"] for r in rows], edgecolors="white", linewidths=0.8, zorder=5)
    b = case["bbox"]; ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); ax.set_aspect(1 / np.cos(np.radians((b[1] + b[3]) / 2))); ax.axis("off")
    cb = fig.colorbar(sc, ax=ax, fraction=0.025, pad=0.01); cb.set_label("osiadanie niecki (cm)", color="white"); plt.setp(cb.ax.get_yticklabels(), color="white")
    ax.set_title(f"Niecki wykryte przez NISAR a oficjalne obszary górnicze węgla kamiennego (PIG-PIB, MIDAS)\n"
                 f"{k} z {n} niecek leży w obszarze górniczym; te obszary zajmują {cover*100:.0f}% analizowanego terenu", color="white", fontsize=14, fontweight="bold")
    fig.tight_layout(); fig.savefig(out / name / "MAPA_obszary_gornicze.jpg", dpi=110, facecolor="#0b1420", pil_kwargs={"quality": 90}); plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--only", required=True); p.add_argument("--data", default=str(HERE / "data"))
    p.add_argument("--out", default=str(HERE / "output")); A = p.parse_args()
    run(A.only, json.loads((HERE / "cases.json").read_text())[A.only], Path(A.data), Path(A.out))
