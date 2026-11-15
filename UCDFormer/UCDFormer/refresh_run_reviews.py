#!/usr/bin/env python3
"""Refresh legended run reviews without rerunning training or classification."""
import os
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs/.matplotlib'))
import numpy as np
import rasterio
from nisar.review import pseudo_review

def main():
 for study in (ROOT/'outputs/runs').glob('*/study.json'):
  out=study.parent
  if not all((out/(name+'.tif')).exists() for name in ['physical_score','candidate_support']):continue
  def read(name):
   with rasterio.open(out/(name+'.tif')) as src:return src.read(1)
  data=np.load(out/'pair.npz');meta=json.loads(study.read_text())
  pseudo_review(out,data['pre'],data['post'],read('valid_mask').astype(bool),read('pseudo_labels'),read('change_mask')==1,
                {'physical_score':read('physical_score'),'candidate_support':read('candidate_support')},meta['details'])
  print('Refreshed',out.name)
if __name__=='__main__':main()
