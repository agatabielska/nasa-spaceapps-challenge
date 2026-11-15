"""Public metadata-only planning search. No authentication or imagery downloads."""
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "planning" / "catalog"
API = "https://api.daac.asf.alaska.edu/services/search/param"


def query(event):
    day = dt.date.fromisoformat(event["date"])
    lon, lat = event["coordinates"]
    dy = 5 / 111.32
    dx = dy / math.cos(math.radians(lat))
    bbox = [lon-dx, lat-dy, lon+dx, lat+dy]
    x0,y0,x1,y1 = bbox
    wkt = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
    params = dict(dataset="NISAR", processingLevel="GCOV", intersectsWith=wkt,
                  start=str(day-dt.timedelta(days=25))+"T00:00:00Z",
                  end=str(day+dt.timedelta(days=25))+"T23:59:59Z",
                  output="geojson", maxResults=250)
    url = API + "?" + urllib.parse.urlencode(params)
    path = OUT / (event["id"] + "_bbox_catalog.json")
    if path.exists():
        raw = json.loads(path.read_text())
    else:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    raw = json.load(response)
                path.write_text(json.dumps(raw, indent=2)+"\n")
                break
            except Exception as exc:
                if attempt == 2:
                    return dict(id=event["id"], error=str(exc), query_url=url)
                time.sleep(1)
    features = raw.get("features", [])
    groups = {}
    for feature in features:
        p = feature["properties"]
        key = (p.get("pathNumber"), p.get("frameNumber"), p.get("flightDirection"),
               tuple(p.get("mainBandPolarization") or []), tuple(p.get("rangeBandwidth") or []),
               p.get("collectionName"), p.get("crid"))
        groups.setdefault(key, []).append(feature)
    pairs = []
    for key, group in groups.items():
        before = sorted([f for f in group if f["properties"]["startTime"][:10] < event["date"]],
                        key=lambda f:f["properties"]["startTime"], reverse=True)
        earliest_post=event["date"] if event["id"]=="mozambique" else str(day+dt.timedelta(days=1))
        after = sorted([f for f in group if f["properties"]["startTime"][:10] >= earliest_post],
                       key=lambda f:f["properties"]["startTime"])
        if not before or not after:
            continue
        a,b = before[0]["properties"],after[0]["properties"]
        def size(p):
            return sum(v.get("bytes",0) for k,v in (p.get("bytes") or {}).items()
                       if k.endswith(".h5") and not k.endswith("_QA_STATS.h5"))
        span = (dt.date.fromisoformat(b["startTime"][:10])-dt.date.fromisoformat(a["startTime"][:10])).days
        def inside(point, ring):
            x,y=point
            result=False
            for i in range(len(ring)):
                ax,ay=ring[i-1]; bx,by=ring[i]
                if (ay>y)!=(by>y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
                    result=not result
            return result
        def contains_box(feature):
            geometry=feature["geometry"]
            polygons=[geometry["coordinates"]] if geometry["type"]=="Polygon" else geometry["coordinates"] if geometry["type"]=="MultiPolygon" else []
            return all(any(inside(corner,p[0]) and not any(inside(corner,h) for h in p[1:]) for p in polygons)
                       for corner in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
        pairs.append(dict(track=key[0], frame=key[1], direction=key[2],
                          polarizations=key[3], bandwidth=key[4], collection=key[5], crid=key[6],
                          before=a["sceneName"], after=b["sceneName"],
                          before_time=a["startTime"], after_time=b["startTime"],
                          before_url=a["url"], after_url=b["url"],
                          before_coverage=a.get("frameCoverage"), after_coverage=b.get("frameCoverage"),
                          full_h5_bytes=size(a)+size(b), interval_days=span,
                          both_footprints_contain_box_corners=contains_box(before[0]) and contains_box(after[0]),
                          same_day_post_needs_onset_check=b["startTime"][:10]==event["date"],
                          validation="catalog compatibility only; AOI intersection is not full or valid-pixel coverage"))
    pairs=list({(p["before"],p["after"]):p for p in pairs}.values())
    pairs.sort(key=lambda p:(not p["both_footprints_contain_box_corners"],"BETA" in (p["collection"] or ""),p["interval_days"],p["full_h5_bytes"]))
    return dict(id=event["id"], event_date=event["date"], event_verified=event.get("catalogVerified",False),
                source=event.get("source"), coordinate_source=event.get("coordinate_source"), center_lon_lat=[lon,lat], bbox_wgs84=bbox,
                bbox_status="proposed approximately 10 km search box; not a verified change footprint",
                query_url=url, granule_count=len(features), possibly_truncated=len(features)>=250,
                pair_count=len(pairs), pairs=pairs)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    events=json.loads((ROOT/"events.json").read_text())
    events += [
        dict(id="nepal_shyar_khola",date="2026-10-11",coordinates=[84.94629,28.45767],catalogVerified=True,
             coordinate_source="https://browser.dataspace.copernicus.eu/?zoom=13&lat=28.45767&lng=84.94629",
             source="https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-the-day/landslide-triggered-flash-flood-sweeps-through-nepals-himalayan-valleys"),
        dict(id="nepal_rasuwagadhi",date="2026-08-26",coordinates=[85.37767854,28.27741433],catalogVerified=True,
             coordinate_source="https://www.geonames.org/advanced-search.html?country=NP&q=&startRow=250",
             source="https://nepal.un.org/sites/default/files/2026-11/Nepal%20Rasuwa-Bhotekoshi%20Flood%20%26%20Budhi%20Gandaki%20Flood_Situation%20Report%20No.%2012.docx.pdf"),
        dict(id="spain_burgohondo",date="2026-07-22",coordinates=[-4.785,40.415],catalogVerified=True,
             source="https://science.nasa.gov/earth/earth-observatory/destructive-fires-char-western-europe/"),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(query,events))
    result=dict(searched_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                note="Placeholder dates are search anchors only. Verified event does not verify approximate center or mask.",
                events=results)
    (ROOT/"planning"/"nisar_pair_candidates.json").write_text(json.dumps(result,indent=2)+"\n")
    for event in results:
        pairs=event.get("pairs",[])
        print(event["id"],event.get("granule_count","ERROR"),"granules",len(pairs),"pairs",event.get("error",""))
        for p in pairs[:2]:
            print(" ",p["before_time"][:10],p["after_time"][:10],p["track"],p["frame"],p["collection"],round(p["full_h5_bytes"]/1e9,2),"GB")


if __name__ == "__main__":
    main()
