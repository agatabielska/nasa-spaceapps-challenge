"""Full-granule geographic context, decimated for viewing rather than measurement."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps")); os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import h5py
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Polygon
from rasterio.warp import transform

d=json.loads((ROOT/"data/download_manifest.json").read_text())
p=next(p for p in d["pairs"] if p["event"]=="mozambique")
arrays=[]; masks=[]; coordinates=[]
step=16
for role in ["before","after"]:
    with h5py.File(ROOT/"data/raw"/(p[role]+".h5")) as f:
        g=f["science/LSAR/GCOV/grids/frequencyA"]
        values=np.stack([g[key][::step,::step] for key in ["HHHH","HVHV"]])
        m=g["mask"][::step,::step]; n=int(g["numberOfSubSwaths"][()])
        valid=(m>0)&(m<=n)&np.all(np.isfinite(values)&(values>0),axis=0)
        if "inputDataExceptionMask" in g: valid &= g["inputDataExceptionMask"][::step,::step]==0
        arrays.append(values); masks.append(valid)
        x=g["xCoordinates"][:]; y=g["yCoordinates"][:]
        coordinates.append((x,y)); epsg=int(g["projection"][()])
        print("READ_CONTEXT",role,"shape",values.shape,flush=True)
if not all(np.array_equal(a,b) for a,b in zip(coordinates[0],coordinates[1])):
    raise ValueError("Full context grids differ; explicit reprojection required")
valid=masks[0]&masks[1]; a,b=arrays
def scale_pair(x,y):
    lo,hi=np.percentile(np.concatenate([x[valid],y[valid]]),[1,99])
    return np.clip((x-lo)/max(1e-8,hi-lo),0,1),np.clip((y-lo)/max(1e-8,hi-lo),0,1)
components=[]
for aa,bb in [(np.sqrt(a[0]),np.sqrt(b[0])),(np.sqrt(a[1]),np.sqrt(b[1])),
              (np.sqrt(a[0]/np.maximum(a[1],1e-20)),np.sqrt(b[0]/np.maximum(b[1],1e-20)))]:
    components.append(scale_pair(aa,bb))
rgb0=np.dstack([components[i][0] for i in range(3)]+[valid.astype(float)])
rgb1=np.dstack([components[i][1] for i in range(3)]+[valid.astype(float)])
temporal=np.dstack([components[0][1],components[0][0],components[0][0],valid.astype(float)])
x,y=coordinates[0]; extent=[float(x[0]-5),float(x[-1]+5),float(y[-1]-5),float(y[0]+5)]
fig,axes=plt.subplots(1,3,figsize=(21,8))
for ax,image,title in zip(axes,[rgb0,rgb1,temporal],
                         ["January 5 — HH / HV / polarization ratio","January 17 — same shared scales","Temporal HH: red increase / cyan decrease"]):
    ax.imshow(np.nan_to_num(image),extent=extent); ax.set_title(title); ax.set_xlabel("UTM easting (m)"); ax.set_ylabel("UTM northing (m)")
    for box,color,label in [([32.9506007754,-24.6449155587,33.0493992246,-24.5550844413],"yellow","Original ~10 km crop"),
                            ([32.75,-24.85,33.25,-24.35],"white","Regional ~50 km crop")]:
        west,south,east,north=box
        px,py=transform("EPSG:4326",f"EPSG:{epsg}",[west,east,east,west],[south,south,north,north])
        ax.add_patch(Polygon(list(zip(px,py)),closed=True,fill=False,edgecolor=color,lw=1.5,label=label))
    ax.legend(loc="lower left",fontsize=8)
fig.suptitle("Mozambique: complete downloaded GCOV frame, not a complete flood perimeter\nNearest-sample display decimation 16× (~160 m); nodata transparent. January 17 is during-flood, not recession.",fontsize=14)
fig.tight_layout(rect=[0,0,1,.93])
out=ROOT/"outputs/eda/mozambique_regional"; out.mkdir(parents=True,exist_ok=True)
fig.savefig(out/"full_granule_context.png",dpi=140); plt.close(fig)
(out/"context_metadata.json").write_text(json.dumps(dict(native_shape=[32040,33120],display_step=step,
      display_sampling="nearest decimation, viewing only; no flood area measurement",crs=f"EPSG:{epsg}",
      native_frame_extent=extent,limitation="Flood may extend beyond acquisition footprint. This figure does not delineate its complete boundary."),indent=2)+"\n")
with (out/"README.md").open("a") as stream:
    stream.write("\n## Full downloaded acquisition context\n\n![Full frame and crop boundaries](full_granule_context.png)\n\nYellow outlines the original crop; white outlines the wider regional crop. This view shows the complete downloaded frame using nearest-sample decimation for display. It is not a mapped flood perimeter, and floodwater may extend outside the acquisition footprint. Polarization-composite colors describe scattering; temporal red/cyan indicates relative increases/decreases, not a flood class.\n")
print("MOZAMBIQUE_FULL_CONTEXT_DONE",flush=True)
