#!/usr/bin/env python3
"""Refresh legacy WGS84 PNGs at native aspect without changing native masks."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import json
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform,reproject,Resampling
from PIL import Image

def main():
    count=0
    for path in (ROOT/'outputs').rglob('study.json'):
        if 'runs' in path.parts or 'results' in path.parts:continue
        data=json.loads(path.read_text());out=path.parent
        if not (out/'before.png').exists():continue
        w,h=Image.open(out/'before.png').size
        source=Affine(*data['transform']);bounds=rasterio.transform.array_bounds(h,w,source)
        target,width,height=calculate_default_transform(data['crs'],'EPSG:4326',w,h,*bounds,dst_width=w,dst_height=h)
        for name in ['before','after','mask','overlay']:
            if not (out/f'{name}.png').exists():continue
            array=np.asarray(Image.open(out/f'{name}.png').convert('RGBA'))
            dest=np.zeros((4,height,width),np.uint8)
            for band in range(4):
                reproject(array[:,:,band],dest[band],src_transform=source,src_crs=data['crs'],dst_transform=target,dst_crs='EPSG:4326',resampling=Resampling.nearest)
            Image.fromarray(dest.transpose(1,2,0)).save(out/f'{name}_wgs84.png')
        data.update(wgs84_bounds=list(rasterio.transform.array_bounds(height,width,target)),display_transform=list(target)[:6],display_shape=[height,width],display_grid='native image aspect; non-square degree pixels')
        path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
        readme=out/'README.md'
        note='\nWGS84 PNG previews have been refreshed to preserve native image proportions, using non-square degree pixels. Use the updated bounds and display transform in study.json for geographic placement. Native mask.png is unchanged.\n'
        text=readme.read_text() if readme.exists() else '# '+out.name+'\n\nNative mask.png: final red change overlay; overlay.png: mask over after image; before.png and after.png: shared-scale SAR composites; pseudo_labels.png: seed labels, not final predictions.\n'
        if note not in text:readme.write_text(text+note)
        count+=1
    print(f'Refreshed {count} legacy export directories; native masks unchanged.')
if __name__=='__main__':main()
