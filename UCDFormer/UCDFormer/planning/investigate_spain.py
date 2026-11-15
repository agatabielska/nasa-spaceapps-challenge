"""Fetch public CEMS/EFFIS evidence for correcting the exploratory Spain AOI."""
import json
from pathlib import Path
import requests

OUT=Path(__file__).resolve().parent/"spain_verification"
OUT.mkdir(exist_ok=True)
for code in ["EMSR900","EMSR898"]:
    url="https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"
    response=requests.get(url,params={"code":code},timeout=45)
    print(code,response.status_code,flush=True)
    response.raise_for_status(); data=response.json()
    (OUT/(code+".json")).write_text(json.dumps(data,indent=2)+"\n")
    for event in data.get("results",[]):
        print(event.get("name"),event.get("eventTime"),event.get("centroid"),flush=True)
        for aoi in event.get("aois",[]):
            print("AOI",aoi.get("number"),aoi.get("name"),aoi.get("extent"),flush=True)
            for product in aoi.get("products",[]):
                print("PRODUCT",product.get("type"),product.get("downloadPath"),flush=True)
                for layer in product.get("layers",[]):
                    if "observedEvent" in layer.get("name",""):
                        print("EVENT_LAYER",json.dumps(layer),"BUCKET",event.get("aws_bucket"),flush=True)
for layer in ["modis.ba.poly.2026","modis.ba.poly.season"]:
    try:
        params=dict(service="WFS",version="1.0.0",request="GetFeature",typename="ms:"+layer,
                    outputformat="geojson",bbox="-5,40,-4,40.8")
        r=requests.get("https://maps.effis.emergency.copernicus.eu/effis",params=params,timeout=60)
        print("EFFIS",layer,r.status_code,len(r.content),flush=True)
        data=r.json(); (OUT/(layer+".geojson")).write_text(json.dumps(data,indent=2)+"\n")
        for f in data.get("features",[]): print("FIRE",f.get("properties"),flush=True)
    except Exception as exc: print("EFFIS_FAILED",layer,type(exc).__name__,flush=True)
