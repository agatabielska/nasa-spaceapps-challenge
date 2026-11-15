#!/usr/bin/env python3
"""Apply one shared policy to any list of input pairs, without rewriting inputs."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
from nisar.config import load_inputs,resolve_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',nargs='+',help='Data-only JSON files; defaults to configs/*_run.json')
    parser.add_argument('--settings',default='configs/pipeline.json')
    parser.add_argument('--gunw',help='Optional GUNW HDF5; use with exactly one --inputs pair')
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--device',default='cuda')
    parser.add_argument('--visualize-steps',action='store_true')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.resume and args.output_root is None:parser.error('--resume requires --output-root')
    paths=[Path(p) for p in args.inputs] if args.inputs else sorted((ROOT/'configs').glob('*_run.json'))
    inputs=[(path,load_inputs(path)) for path in paths]
    if args.gunw and len(inputs)!=1:parser.error('--gunw requires exactly one input pair to avoid applying one interferogram to unrelated locations')
    identifiers=[data['study_id'] for _,data in inputs]
    if len(set(identifiers))!=len(identifiers):parser.error('Each input must have a unique study_id')
    root=args.output_root or ROOT/'outputs/batches'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    if not root.is_absolute():root=ROOT/root
    if root.exists() and any(root.iterdir()) and not args.resume:parser.error('Use an empty output root or --resume')
    root.mkdir(parents=True,exist_ok=True);rows=[]
    for path,data in inputs:
        out=root/data['study_id']
        if args.resume and (out/'run.jsonl').exists():
            _,expected_input,settings=resolve_config(path,args.settings,out,args.gunw)
            records=[json.loads(line) for line in (out/'run.jsonl').read_text().splitlines() if line.strip()]
            if (records and records[-1].get('event')=='stage_complete' and records[-1].get('stage')=='all'
                and (out/'input.json').exists() and json.loads((out/'input.json').read_text())==expected_input
                and (out/'pipeline_settings.json').exists() and json.loads((out/'pipeline_settings.json').read_text())==settings):
                rows.append(dict(study_id=data['study_id'],returncode=0,output=str(out),reused=True));continue
        if out.exists() and any(out.iterdir()):
            rows.append(dict(study_id=data['study_id'],returncode=1,output=str(out),error='Existing incomplete or incompatible run preserved; choose a new output root'));continue
        command=[sys.executable,'-u',str(ROOT/'run_nisar.py'),'--config',str(path),'--settings',args.settings,
                 '--output',str(out),'--stage','all','--device',args.device]
        if args.visualize_steps:command.append('--visualize-steps')
        if args.gunw is not None:command+=['--gunw',args.gunw]
        print('START',data['study_id'],flush=True)
        result=subprocess.run(command,cwd=ROOT)
        if args.visualize_steps:
            sys.path.insert(0,str(ROOT/'.deps'))
            from nisar.step_report import build_report
            print(build_report(out),flush=True)
        rows.append(dict(study_id=data['study_id'],returncode=result.returncode,output=str(out)))
        (root/'status.json').write_text(json.dumps(rows,indent=2)+'\n')
    (root/'status.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Batch status:',root/'status.json')
    return int(any(row['returncode'] for row in rows))


if __name__=='__main__':sys.exit(main())
