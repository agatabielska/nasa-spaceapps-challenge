"""Overlay independently mapped CEMS fire geometry on corrected NISAR EDA."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps")); os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from rasterio.features import bounds,rasterize
from rasterio.transform import Affine,from_bounds
from rasterio.warp import transform_geom
from scipy import ndimage
from nisar.data import align_pair

source=ROOT/"planning/spain_verification/CEMS_Piedralaves_observed_event.json"
reference=json.loads(source.read_text())
features=reference["features"]
box=[-4.70,40.29,-4.58,40.38]
files=json.loads((ROOT/"data/spain_correction_manifest.json").read_text())["files"]
paths={f["role"]:ROOT/"data/raw"/(f["id"]+".h5") for f in files}
pre,post,valid,meta=align_pair(paths["before"],paths["after"],box)
selected=[f for f in features if bounds(f["geometry"])[0]<box[2] and bounds(f["geometry"])[2]>box[0]
          and bounds(f["geometry"])[1]<box[3] and bounds(f["geometry"])[3]>box[1]]
projected=[transform_geom("EPSG:4326",meta["crs"],f["geometry"]) for f in selected]
burn=rasterize([(g,1) for g in projected],out_shape=valid.shape,transform=Affine(*meta["transform"]),fill=0).astype(bool)&valid
out=ROOT/"outputs/eda/spain_navaluenga_corrected"
support=ndimage.uniform_filter(valid.astype(np.float32),3,mode="constant")
fig,axes=plt.subplots(2,2,figsize=(12,10))
stats=[]
for i,p in enumerate(["HH","HV"]):
    def smooth(x): return ndimage.uniform_filter(np.where(valid,x,0),3,mode="constant")/np.maximum(support,1e-8)
    a,b=smooth(pre[i]),smooth(post[i]); delta=(b-a)/np.maximum(a+b,1e-20); good=valid&(support>.999)
    image=axes[i,0].imshow(np.ma.array(delta,mask=~good),cmap="RdBu_r",vmin=-.6,vmax=.6)
    axes[i,0].contour(burn.astype(float),levels=[.5],colors=["yellow"],linewidths=.6)
    axes[i,0].set_title(p+" normalized change + CEMS mapped burn boundary")
    cb=fig.colorbar(image,ax=axes[i,0],ticks=[-.6,-1/3,0,1/3,.6]); cb.ax.set_yticklabels(["¼×","½×","same","2×","4×"])
    inside=delta[good&burn]; outside=delta[good&~burn]
    axes[i,1].hist(inside,bins=np.linspace(-1,1,100),density=True,histtype="step",label="Inside mapped burn")
    axes[i,1].hist(outside,bins=np.linspace(-1,1,100),density=True,histtype="step",label="Outside polygons (not verified unchanged)")
    axes[i,1].set_xlabel("Normalized relative return change"); axes[i,1].set_ylabel("Density"); axes[i,1].legend(fontsize=8)
    axes[i,1].set_title(p+" conditional distributions; no accuracy claim")
    stats.append(dict(polarization=p,mapped_burn_median=float(np.median(inside)),outside_polygon_median=float(np.median(outside))))
fig.suptitle("July 2 → August 19 | CEMS reference from August 5 optical imagery\nMapped fire footprint gives spatial context; return changes can have other causes")
fig.tight_layout(rect=[0,0,1,.94]); fig.savefig(out/"mapped_burn_comparison.png",dpi=150); plt.close(fig)
overview_box=[-4.88,40.22,-4.28,40.53]
mapped=rasterize([(f["geometry"],1) for f in features],out_shape=(700,1200),transform=from_bounds(*overview_box,1200,700),fill=0)
fig,ax=plt.subplots(figsize=(12,7)); ax.imshow(mapped,cmap="Oranges",vmin=0,vmax=1,extent=[overview_box[0],overview_box[2],overview_box[1],overview_box[3]])
old=json.loads((ROOT/"outputs/eda/spain_burgohondo/eda.json").read_text())["bbox_wgs84"]
for b,color,label in [(old,"blue","Original town-centered crop"),(box,"red","Corrected Navaluenga south crop")]:
    ax.add_patch(Rectangle((b[0],b[1]),b[2]-b[0],b[3]-b[1],fill=False,edgecolor=color,lw=2,label=label))
ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.set_title("CEMS EMSR900 AOI04 mapped burns and the two NISAR crops\nWhite is outside mapped burn polygons, not verified unchanged ground")
ax.legend(); fig.tight_layout(); fig.savefig(out/"aoi_correction.png",dpi=150); plt.close(fig)
(out/"reference_comparison.json").write_text(json.dumps(dict(source=str(source),source_crs="CRS84 longitude,latitude",
    reference_acquisition="2026-08-05T07:32:00",reference_type="optical-derived CEMS mapped burnt area",
    mapped_burn_fraction=float(burn.sum()/valid.sum()),statistics=stats,
    caveat="Outside polygons may be unburned or incompletely mapped; these are not generic-change labels"),indent=2)+"\n")
readme=out/"README.md"
with readme.open("a") as stream:
    stream.write("\n## Independent mapped-fire context\n\n![Original and corrected crop locations](aoi_correction.png)\n\n![Mapped burn overlay and conditional distributions](mapped_burn_comparison.png)\n\nYellow outlines are CEMS optical-derived burn polygons from August 5 imagery. They provide independent context; outside polygons are not verified unchanged. See [reference comparison](reference_comparison.json).\n")
print("SPAIN_REFERENCE_EDA_DONE",float(burn.sum()/valid.sum()),flush=True)
