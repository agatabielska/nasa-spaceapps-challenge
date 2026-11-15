"""Download matched normal-orbit pre/late-post products for corrected Spain EDA."""
import json
import os
from pathlib import Path
import requests
from dotenv import dotenv_values
from download_nisar import EarthdataSession,download

ROOT=Path(__file__).resolve().parent
catalog=json.loads((ROOT/"planning/spain_verification/corrected_area_catalog.json").read_text())
selected=[]
for date,role in [("2026-07-02","before"),("2026-08-19","after")]:
    p=next(f["properties"] for f in catalog["features"] if f["properties"].get("pathNumber")==87
           and f["properties"]["startTime"].startswith(date))
    size=sum(v["bytes"] for k,v in p["bytes"].items() if k.endswith(".h5") and not k.endswith("_QA_STATS.h5"))
    selected.append(dict(event="spain_navaluenga_corrected",role=role,id=p["sceneName"],url=p["url"],bytes=size))
original=json.loads((ROOT/"data/download_manifest.json").read_text())
total=sum(p["full_h5_bytes"] for p in original["pairs"])+sum(p["bytes"] for p in selected)
if total>80_000_000_000: raise RuntimeError("Would exceed 80 GB raw budget")
(ROOT/"data/spain_correction_manifest.json").write_text(json.dumps(dict(files=selected,total_raw_budgeted_bytes=total,
    bbox=[-4.70,40.29,-4.58,40.38],source="EFFIS normalized mapped-fire geometry; see planning/spain_verification"),indent=2)+"\n")
credentials=dotenv_values(ROOT.parents[1]/".env")
session=EarthdataSession(); session.auth=(os.environ.get("EARTHDATA_LOGIN") or credentials["EARTHDATA_LOGIN"],
                                        os.environ.get("EARTHDATA_PASSWORD") or credentials["EARTHDATA_PASSWORD"])
for item in selected: download(session,item,ROOT/"data/raw")
print("SPAIN_CORRECTION_DOWNLOADED",flush=True)
