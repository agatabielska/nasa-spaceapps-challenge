"""Inspect source structure without reading image rasters."""
from pathlib import Path
import json
import h5py
import numpy as np
HERE=Path(__file__).resolve().parent
manifest=json.loads((HERE/'download_manifest.json').read_text())
def serial(value):
 if isinstance(value,complex):return {"real":value.real,"imag":value.imag}
 if isinstance(value,h5py.Reference):return "HDF5 object reference"
 if isinstance(value,(list,tuple)):return [serial(v) for v in value]
 if isinstance(value,bytes):return value.decode(errors='replace')
 if isinstance(value,np.ndarray):return [serial(v) for v in value.tolist()] if value.ndim else serial(value.item())
 if isinstance(value,np.generic):return serial(value.item())
 return value
rows=[]
with h5py.File(manifest['file'],'r') as f:
 print('Identification:')
 g=f['science/LSAR/identification']
 identification={k:serial(v[()]) for k,v in g.items() if isinstance(v,h5py.Dataset) and v.size<20}
 print(json.dumps(identification,indent=2))
 def visit(name,obj):
  if isinstance(obj,h5py.Dataset) and 'grids' in name:
   row=dict(path=name,shape=list(obj.shape),dtype=str(obj.dtype),attrs={k:serial(v) for k,v in obj.attrs.items() if k!='DIMENSION_LIST'})
   if obj.ndim==0:row['value']=serial(obj[()])
   rows.append(row)
   print(name,obj.shape,str(obj.dtype))
 f.visititems(visit)
(HERE/'schema.json').write_text(json.dumps(dict(identification=identification,datasets=rows),indent=2)+'\n')
