#!/usr/bin/env python3
"""Run an isolated NISAR experiment with an offline, step-by-step HTML report."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-step-matplotlib')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/etna_run.json')
    parser.add_argument('--settings',default='configs/pipeline.json')
    parser.add_argument('--gunw',help='Optional GUNW HDF5 for pre-RF coherence support')
    parser.add_argument('--output',help='New, empty output directory; existing artifacts are never overwritten')
    parser.add_argument('--device',default='cuda')
    parser.add_argument('--max-updates',type=int,help='Optional training budget override')
    parser.add_argument('--report-only',type=Path,metavar='RUN_DIRECTORY',help='Render existing trace files without running any algorithm')
    args=parser.parse_args()
    if args.report_only:
        from nisar.step_report import build_report
        print(build_report(args.report_only.resolve()));return 0
    config_path=Path(args.config)
    if not config_path.is_absolute():config_path=ROOT/config_path
    from nisar.config import load_inputs
    config=load_inputs(config_path)
    out=Path(args.output) if args.output else Path('outputs/walkthroughs')/(config['study_id']+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not out.is_absolute():out=ROOT/out
    if out.exists() and any(out.iterdir()):parser.error('Output must be a new or empty directory')
    if args.max_updates is not None and args.max_updates<1:parser.error('--max-updates must be positive')
    out.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-u',str(ROOT/'run_nisar.py'),'--config',str(config_path),
             '--settings',args.settings,'--output',str(out),'--visualize-steps',
             '--stage','all','--device',args.device]
    if args.max_updates is not None:command+=['--max-updates',str(args.max_updates)]
    if args.gunw is not None:command+=['--gunw',args.gunw]
    print('Running isolated experiment in',out,flush=True)
    code=1
    try:
        with (out/'pipeline.log').open('w') as stream:
            process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                for line in process.stdout:
                    print(line,end='',flush=True);stream.write(line);stream.flush()
                code=process.wait()
            except BaseException:
                process.terminate();process.wait();raise
    finally:
        from nisar.step_report import build_report
        print('Open the local report:',build_report(out),flush=True)
    return code


if __name__=='__main__':sys.exit(main())
