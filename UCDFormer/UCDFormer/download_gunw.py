#!/usr/bin/env python3
"""Fetch one exact GUNW granule without changing any pipeline configuration."""
import argparse,json,os,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import requests
from dotenv import get_key
from download_nisar import EarthdataSession,download


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--granule',required=True)
    args=parser.parse_args();granule=args.granule.removesuffix('.h5')
    if not re.fullmatch(r'NISAR_L2_[A-Z]+_GUNW_[A-Za-z0-9_]+',granule):parser.error('Expected a NISAR GUNW granule ID')
    directory=ROOT/'data/gunw_downloads'/granule;directory.mkdir(parents=True,exist_ok=True)
    catalog=directory/'catalog.json'
    if catalog.exists():raw=json.loads(catalog.read_text())
    else:
        response=requests.get('https://api.daac.asf.alaska.edu/services/search/param',params=dict(granule_list=granule,output='geojson'),timeout=60)
        response.raise_for_status();raw=response.json();catalog.write_text(json.dumps(raw,indent=2)+'\n')
    features=raw.get('features',[])
    if len(features)!=1 or features[0]['properties'].get('sceneName')!=granule:
        raise ValueError('ASF did not return one exact matching granule')
    p=features[0]['properties'];url=p.get('url','')
    if not url.endswith('.h5'):raise ValueError('Missing exact HDF5 URL')
    size=sum(v.get('bytes',0) for k,v in (p.get('bytes') or {}).items() if k==granule+'.h5')
    destination=ROOT/'data/raw';target=destination/(granule+'.h5')
    manifest=dict(granule=granule,url=url,catalog_bytes=size,file=str(target))
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest),flush=True)
    if target.exists():print('Already downloaded:',target,flush=True);return
    # Respect the existing 100 GB data + derived-artifact budget; environments are separate.
    used=sum(p.stat().st_size for name in ('data/raw','outputs','old','weights') for p in (ROOT/name).rglob('*') if p.is_file())
    partial=target.with_suffix('.h5.part');remaining=max(0,size-(partial.stat().st_size if partial.exists() else 0))
    print('Data/artifact bytes after download:',used+remaining,flush=True)
    if not size or used+remaining>100_000_000_000:raise RuntimeError('Download would exceed the 100 GB data/artifact budget, or size is unknown')
    if shutil.disk_usage(destination).free<remaining+1_000_000_000:raise RuntimeError('Insufficient disk headroom')
    login=os.environ.get('EARTHDATA_LOGIN') or get_key(ROOT.parents[1]/'.env','EARTHDATA_LOGIN')
    password=os.environ.get('EARTHDATA_PASSWORD') or get_key(ROOT.parents[1]/'.env','EARTHDATA_PASSWORD')
    if not login or not password:raise RuntimeError('Earthdata credentials missing')
    session=EarthdataSession();session.auth=(login,password)
    session.headers['User-Agent']='NISAR-isolated-GUNW-download/1.0'
    download(session,dict(id=granule,url=url,event='requested_pair',role='GUNW'),destination)


if __name__=='__main__':main()
