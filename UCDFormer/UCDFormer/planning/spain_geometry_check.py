"""Normalize official EFFIS WFS axis order and measure old/new AOI overlap."""
import json
from pathlib import Path
import numpy as np
from rasterio.features import bounds,rasterize
from rasterio.transform import from_bounds

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/"planning/spain_verification"
raw=json.loads((out/"modis.ba.poly.season.geojson").read_text())
features=[f for f in raw["features"] if f["properties"].get("id") in ["562592","592438","572496"]]
def swap(coords):
    if isinstance(coords[0],(int,float)): return [coords[1],coords[0]]
    return [swap(c) for c in coords]
for f in features:
    box=bounds(f["geometry"])
    if 35<box[0]<45 and -10<box[1]<0:
        f["geometry"]["coordinates"]=swap(f["geometry"]["coordinates"])
        f["properties"]["axis_normalization"]="WFS returned latitude,longitude; swapped to GeoJSON longitude,latitude after Spanish geography check"
    print(f["properties"]["id"],f["properties"]["COMMUNE"],bounds(f["geometry"]))
data=dict(type="FeatureCollection",features=features)
(out/"spain_fire_perimeters_lonlat.geojson").write_text(json.dumps(data,indent=2)+"\n")
old=json.loads((ROOT/"outputs/eda/spain_burgohondo/eda.json").read_text())["bbox_wgs84"]
proposed={"original_burgohondo":old,"navaluenga_south":[-4.70,40.29,-4.58,40.38],
          "el_tiemblo":[-4.60,40.31,-4.48,40.40],"navas_del_rey":[-4.35,40.32,-4.23,40.41]}
result={}
for name,box in proposed.items():
    mask=rasterize([(f["geometry"],1) for f in features],out_shape=(600,600),transform=from_bounds(*box,600,600),fill=0)
    result[name]=dict(bbox=box,mapped_fire_fraction=float(mask.mean()))
print(json.dumps(result,indent=2))
(out/"aoi_overlap.json").write_text(json.dumps(result,indent=2)+"\n")
