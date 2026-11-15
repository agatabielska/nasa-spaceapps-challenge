"""Launch authorized download/EDA workers with persistent local logs and PIDs."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import signal
import sys
import time

ROOT=Path(__file__).resolve().parent
logs=ROOT/"outputs/jobs"; logs.mkdir(parents=True,exist_ok=True)
state=logs/"workers.json"
previous=json.loads(state.read_text()) if state.exists() else {}
parser=argparse.ArgumentParser(); parser.add_argument("--restart-eda",action="store_true")
args=parser.parse_args()
if args.restart_eda and previous.get("eda",{}).get("pid"):
    pid=previous["eda"]["pid"]
    try:
        if b"make_eda.py" in Path(f"/proc/{pid}/cmdline").read_bytes():
            os.kill(pid,signal.SIGTERM)
            for _ in range(20):
                time.sleep(.1)
                if not Path(f"/proc/{pid}/cmdline").exists() or not Path(f"/proc/{pid}/cmdline").read_bytes(): break
    except ProcessLookupError: pass
workers={}
for name,args in [("downloads",["download_nisar.py"]),("eda",["make_eda.py","--watch"])]:
    existing=previous.get(name,{}).get("pid")
    alive=False
    if existing:
        try:
            cmd=Path(f"/proc/{existing}/cmdline").read_bytes()
            alive=args[0].encode() in cmd
        except (OSError,ProcessLookupError): pass
    if alive:
        workers[name]=previous[name]; continue
    path=logs/(name+".log")
    with path.open("ab",buffering=0) as stream:
        process=subprocess.Popen([sys.executable,"-u",*args],cwd=ROOT,stdin=subprocess.DEVNULL,
                                 stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    workers[name]=dict(pid=process.pid,command=args,log=str(path))
state.write_text(json.dumps(workers,indent=2)+"\n")
print(json.dumps(workers,indent=2))
