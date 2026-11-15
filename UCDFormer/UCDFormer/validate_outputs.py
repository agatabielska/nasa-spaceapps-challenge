#!/usr/bin/env python3
"""Validate output geometry, mask semantics and embedded local image links."""
from pathlib import Path
import sys,json,re
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import numpy as np
import rasterio
from PIL import Image

def main():
 rows=[]
 for study_path in sorted((ROOT/'outputs/runs').glob('*/study.json')):
  out=study_path.parent;study=json.loads(study_path.read_text())
  with rasterio.open(out/'change_mask.tif') as src:
   mask=src.read(1);assert src.nodata==255
   assert src.crs.to_string()==study['crs']
   assert set(np.unique(mask))<={0,1,255}
  with rasterio.open(out/'valid_mask.tif') as src:valid=src.read(1).astype(bool)
  with rasterio.open(out/'change_score.tif') as src:score=src.read(1)
  assert np.array_equal(mask!=255,valid)
  assert np.isfinite(score[valid]).all() and np.isnan(score[~valid]).all()
  assert int(valid.sum())==study['valid_pixels']
  assert int((mask==1).sum())==study['changed_pixels']
  with Image.open(out/'before.png') as native,Image.open(out/'before_wgs84.png') as geo:
   assert native.size==geo.size==(mask.shape[1],mask.shape[0])
  meta=json.loads((out/'pair_metadata.json').read_text())
  train=np.zeros(mask.shape,bool);validation=train.copy()
  for windows,support in [(meta['train_windows'],train),(meta['validation_windows'],validation)]:
   for y,x,n in windows:support[y:y+n,x:x+n]=True
  assert not (train&validation).any()
  rows.append(dict(location=out.name,status='passed',changed_pixels=study['changed_pixels'],
                   coverage_fraction=float(valid.mean()),native_and_wgs84_shape=list(mask.shape)))
 broken=[]
 for readme in (ROOT/'outputs').rglob('README.md'):
  for ref in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',readme.read_text()):
   if not ref.startswith('http') and not (readme.parent/ref).is_file():broken.append([str(readme),ref])
 assert not broken,broken
 report=dict(runs=rows,broken_embedded_images=broken,accuracy='not evaluated: no independent reference masks')
 (ROOT/'outputs/results/validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
