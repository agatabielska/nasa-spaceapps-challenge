"""Download only the explicitly requested GUNW; existing pipeline is untouched."""
import sys,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import requests
from dotenv import get_key
from download_nisar import EarthdataSession,download
GRANULE='NISAR_L2_PR_GUNW_028_098_A_016_029_4000_SH_20260819T233918_20260819T233953_20260831T233918_20260831T233952_X05026_N_F_J_001'
OUT=Path(__file__).resolve().parent
catalog=OUT/'catalog.json'
if catalog.exists():raw=json.loads(catalog.read_text())
else:
 response=requests.get('https://api.daac.asf.alaska.edu/services/search/param',params=dict(granule_list=GRANULE,output='geojson'),timeout=60)
 response.raise_for_status();raw=response.json();catalog.write_text(json.dumps(raw,indent=2)+'\n')
features=raw.get('features',[])
if len(features)!=1:raise RuntimeError(f'Expected one exact granule; found {len(features)}')
p=features[0]['properties']
if p.get('sceneName')!=GRANULE:raise RuntimeError('Catalog did not return the exact requested granule')
url=p.get('url')
if not url or not url.endswith('.h5'):raise RuntimeError('Missing HDF5 download URL')
size=sum(v.get('bytes',0) for k,v in (p.get('bytes') or {}).items() if k.endswith('.h5') and 'QA' not in k)
manifest=dict(granule=GRANULE,url=url,catalog_h5_bytes=size,source='ASF exact granule lookup',file=str(ROOT/'data/raw'/(GRANULE+'.h5')))
(OUT/'download_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest),flush=True)
if (ROOT/'data/raw'/(GRANULE+'.h5')).exists():print('Already downloaded',flush=True);sys.exit(0)
if size and shutil.disk_usage(ROOT/'data/raw').free<size+2_000_000_000:raise RuntimeError('Insufficient disk space')
login=os.environ.get('EARTHDATA_LOGIN') or get_key(ROOT.parents[1]/'.env','EARTHDATA_LOGIN')
password=os.environ.get('EARTHDATA_PASSWORD') or get_key(ROOT.parents[1]/'.env','EARTHDATA_PASSWORD')
if not login or not password:raise RuntimeError('Missing Earthdata credentials')
session=EarthdataSession();session.auth=(login,password)
session.headers['User-Agent']='NISAR-GUNW-isolated-visualization/1.0'
download(session,dict(id=GRANULE,url=url,event='nepal_rasuwagadhi',role='GUNW'),ROOT/'data/raw')
