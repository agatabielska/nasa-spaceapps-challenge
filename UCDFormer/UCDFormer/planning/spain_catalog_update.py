import json
from pathlib import Path
import requests
OUT=Path(__file__).resolve().parent/"spain_verification"
params=dict(dataset="NISAR",processingLevel="GCOV",intersectsWith="POLYGON((-4.9 40.2,-4.1 40.2,-4.1 40.6,-4.9 40.6,-4.9 40.2))",
            start="2026-07-01T00:00:00Z",end="2026-09-01T23:59:59Z",output="geojson",maxResults=250)
r=requests.get("https://api.daac.asf.alaska.edu/services/search/param",params=params,timeout=60); r.raise_for_status()
data=r.json(); (OUT/"corrected_area_catalog.json").write_text(json.dumps(data,indent=2)+"\n")
print("COUNT",len(data.get("features",[])))
for f in data.get("features",[]):
    p=f["properties"]
    if p.get("pathNumber")==87:
        print(p["sceneName"],p.get("collectionName"),p.get("crid"),p.get("mainBandPolarization"),flush=True)

url="https://rapidmapping-viewer.s3.eu-west-1.amazonaws.com/EMSR900/AOI04/GRA_PRODUCT/EMSR900_AOI04_GRA_PRODUCT_observedEventA_v1.json"
r=requests.get(url,timeout=45)
print("CEMS_GEOMETRY",r.status_code,len(r.content))
if r.ok:
    (OUT/"CEMS_Piedralaves_observed_event.json").write_bytes(r.content)
    print("CEMS_KEYS",list(r.json())[:12])
