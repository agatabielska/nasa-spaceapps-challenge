"""Resumable, authenticated shortlist downloader. Credentials never enter logs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import time
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
ALLOWED = {"urs.earthdata.nasa.gov", "nisar.asf.earthdatacloud.nasa.gov", "datapool.asf.alaska.edu"}


class EarthdataSession(requests.Session):
    def rebuild_auth(self, prepared_request, response):
        if urlparse(prepared_request.url).hostname not in ALLOWED:
            prepared_request.headers.pop("Authorization", None)


def queue():
    data=json.loads((ROOT/"planning/nisar_pair_candidates.json").read_text())
    events={e["id"]:e for e in data["events"]}
    chosen=[]
    for key in ["etna","spain_burgohondo","nepal_shyar_khola","mozambique","hubbard","nepal_rasuwagadhi"]:
        pairs=events[key]["pairs"]
        if key=="hubbard":
            pair=next(p for p in pairs if p["before_time"].startswith("2025-11-26"))
        elif key=="nepal_rasuwagadhi":
            pair=next(p for p in pairs if p["crid"]=="P05023" and len(p["polarizations"])==2)
        else:
            pair=pairs[0]
        chosen.append(dict(event=key,**pair))
    quad=next(p for p in events["nepal_shyar_khola"]["pairs"] if len(p["polarizations"])==4)
    chosen.append(dict(event="nepal_quad",**quad))
    seen=set(); files=[]
    for pair in chosen:
        for role in ["before","after"]:
            if pair[role] in seen: continue
            seen.add(pair[role])
            files.append(dict(event=pair["event"],role=role,id=pair[role],url=pair[role+"_url"],
                              pair_bytes=pair["full_h5_bytes"]))
    return chosen,files


def download(session, item, destination):
    target=destination/(item["id"]+".h5")
    partial=target.with_suffix(".h5.part")
    if target.exists():
        print("EXISTS",item["event"],item["role"],target.stat().st_size,flush=True)
        return
    for attempt in range(5):
        offset=partial.stat().st_size if partial.exists() else 0
        try:
            headers={"Range":f"bytes={offset}-"} if offset else {}
            with session.get(item["url"],headers=headers,stream=True,timeout=(30,120)) as response:
                response.raise_for_status()
                if "text/html" in response.headers.get("Content-Type",""):
                    raise RuntimeError("HTML returned instead of HDF5; Earthdata authorization may be needed")
                append=offset>0 and response.status_code==206
                if append and not response.headers.get("Content-Range","").startswith(f"bytes {offset}-"):
                    raise RuntimeError("Invalid resume Content-Range")
                expected=int(response.headers.get("Content-Length",0))+(offset if append else 0)
                if not append: offset=0
                print("START",item["event"],item["role"],"offset",offset,"expected",expected,flush=True)
                last=time.monotonic(); count=offset
                with partial.open("ab" if append else "wb") as output:
                    for block in response.iter_content(4*1024*1024):
                        if not block: continue
                        output.write(block); count+=len(block)
                        if time.monotonic()-last>30:
                            print("PROGRESS",item["event"],item["role"],round(count/1e9,3),"GB",flush=True)
                            last=time.monotonic()
                if expected and partial.stat().st_size!=expected:
                    raise RuntimeError("Incomplete transfer")
            with partial.open("rb") as stream:
                if stream.read(8)!=b"\x89HDF\r\n\x1a\n":
                    raise RuntimeError("Response is not an HDF5 file")
            partial.replace(target)
            print("DONE",item["event"],item["role"],target.stat().st_size,flush=True)
            return
        except Exception as exc:
            # No credential values, response bodies or headers in this diagnostic.
            print("RETRY",item["event"],item["role"],attempt+1,type(exc).__name__,flush=True)
            if attempt==4: raise RuntimeError(f"Download failed for {item['event']} {item['role']}") from None
            time.sleep(min(30,2**attempt))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--etna-only",action="store_true")
    args=parser.parse_args()
    destination=ROOT/"data/raw"; destination.mkdir(parents=True,exist_ok=True)
    chosen,files=queue()
    if args.etna_only: files=[f for f in files if f["event"]=="etna"]
    total=sum(p["full_h5_bytes"] for p in chosen)
    if total>80_000_000_000: raise RuntimeError("Raw shortlist exceeds 80 GB budget")
    if shutil.disk_usage(destination).free<total+15_000_000_000:
        raise RuntimeError("Insufficient disk headroom for shortlist")
    (ROOT/"data/download_manifest.json").write_text(json.dumps(dict(raw_budget=80_000_000_000,pairs=chosen,files=files),indent=2)+"\n")
    credentials=dotenv_values(ROOT.parents[1]/".env")
    login=os.environ.get("EARTHDATA_LOGIN") or credentials.get("EARTHDATA_LOGIN")
    password=os.environ.get("EARTHDATA_PASSWORD") or credentials.get("EARTHDATA_PASSWORD")
    if not login or not password: raise RuntimeError("Earthdata variables missing in root .env/environment")
    session=EarthdataSession(); session.auth=(login,password)
    session.headers["User-Agent"]="NISAR-UCDFormer-research/1.0"
    failures=[]
    for item in files:
        try: download(session,item,destination)
        except Exception as exc:
            failures.append(dict(event=item["event"],role=item["role"],error=str(exc)))
            print("FAILED",item["event"],item["role"],flush=True)
            (ROOT/"data/download_failures.json").write_text(json.dumps(failures,indent=2)+"\n")
            if item["event"]=="etna": raise
    print("QUEUE_FINISHED",len(files),"files",len(failures),"failures",flush=True)


if __name__=="__main__": main()
