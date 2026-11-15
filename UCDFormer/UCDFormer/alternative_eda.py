"""Non-dB companion views. Physical power remains separate from display scaling."""
import argparse
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
from scipy import ndimage
from nisar.data import align_pair
from nisar.export import write_tif
from make_eda import common_channels


def process(event):
    out=ROOT/"outputs/eda"/event
    info=json.loads((out/"eda.json").read_text())
    manifests=json.loads((ROOT/"data/download_manifest.json").read_text())["pairs"]
    extra=ROOT/"data/extra_eda_pairs.json"
    if extra.exists(): manifests+=json.loads(extra.read_text())
    pair=next(p for p in manifests if p["event"]==event)
    a=ROOT/"data/raw"/(pair["before"]+".h5"); b=ROOT/"data/raw"/(pair["after"]+".h5")
    channels=common_channels(a,b)
    pre,post,valid,meta=align_pair(a,b,info["bbox_wgs84"],channels)
    support=ndimage.uniform_filter(valid.astype(np.float32),3,mode="constant")
    good=valid&(support>.999)
    if not good.any(): raise ValueError("No fully supported 3x3 neighborhoods")
    fig,axes=plt.subplots(len(channels),3,figsize=(16,5*len(channels)),squeeze=False)
    details=[]
    for i,p in enumerate(channels):
        def smooth(x):
            return ndimage.uniform_filter(np.where(valid,x,0),3,mode="constant")/np.maximum(support,1e-8)
        x,y=smooth(pre[i]),smooth(post[i])
        relative=(y-x)/np.maximum(x+y,np.finfo(np.float32).tiny)
        difference=y-x
        # Shared amplitude display stretch: brightness changes are not independently normalized away.
        amp0,amp1=np.sqrt(np.maximum(x,0)),np.sqrt(np.maximum(y,0))
        lo,hi=np.percentile(np.concatenate([amp0[good],amp1[good]]),[1,99])
        first=np.clip((amp0-lo)/max(hi-lo,1e-8),0,1)
        second=np.clip((amp1-lo)/max(hi-lo,1e-8),0,1)
        rgb=np.dstack([second,first,first,np.where(good,1,0)])
        axes[i,0].imshow(rgb); axes[i,0].set_title(p+" temporal composite\nred: stronger after | cyan: weaker after | gray: similar")
        im=axes[i,1].imshow(np.ma.array(relative,mask=~good),cmap="RdBu_r",vmin=-.6,vmax=.6)
        axes[i,1].set_title(p+" normalized relative change\n(after − before) / (after + before)")
        cb=fig.colorbar(im,ax=axes[i,1],shrink=.75,ticks=[-.6,-1/3,0,1/3,.6])
        cb.ax.set_yticklabels(["¼×","½×","1× same","2×","4×"]); cb.set_label("Equivalent after / before return strength")
        limit=max(float(np.percentile(abs(difference[good]),98)),1e-8)
        im=axes[i,2].imshow(np.ma.array(difference,mask=~good),cmap="RdBu_r",vmin=-limit,vmax=limit)
        axes[i,2].set_title(p+" absolute power change\n(after − before), linear gamma-0 power")
        fig.colorbar(im,ax=axes[i,2],shrink=.75,label="Gamma-0 power difference (dimensionless)")
        for ax in axes[i]: ax.set_xlabel("Column"); ax.set_ylabel("Row")
        write_tif(out/(p+"_normalized_change.tif"),np.where(good,relative,np.nan).astype(np.float32),meta,np.nan)
        write_tif(out/(p+"_linear_change.tif"),np.where(good,difference,np.nan).astype(np.float32),meta,np.nan)
        details.append(dict(polarization=p,normalized_change_range=[-1,1],display_clip=[-.6,.6],
                            power_display_clip=[-limit,limit],median_normalized_change=float(np.median(relative[good])),
                            amplitude_stretch_shared=[float(lo),float(hi)],
                            low_combined_signal_p01=float(np.percentile((x+y)[good],1))))
    fig.suptitle(event+" | non-dB views | 3×3 linear-power mean, shared date scaling\nColor means return-strength change, not a disaster class or probability",fontsize=13)
    fig.tight_layout(rect=[0,0,1,.95]); fig.savefig(out/"non_db_changes.png",dpi=150); plt.close(fig)
    (out/"non_db_metadata.json").write_text(json.dumps(dict(formula="(post-pre)/(post+pre)",
       smoothing="3x3 linear-power mean; full-valid neighborhood only; EDA only",
       source_dates=[info["before"],info["after"]],channels=details,
       limitations=["Ratios unstable near noise floor; no instrument noise floor estimated here",
                    "Relative score is mathematically related to log-ratio; not new independent evidence",
                    "Linear difference emphasizes bright scatterers; display is clipped but GeoTIFF retains values",
                    "Speckle, moisture, terrain and misregistration can cause colors"]),indent=2)+"\n")
    readme=out/"README.md"; text=readme.read_text()
    marker="\n## Non-dB companion views\n"
    text=text.split(marker)[0]
    text+=marker+"\n![Temporal composite, normalized relative change and linear-power difference](non_db_changes.png)\n\n"
    text+="These use a 3×3 mean of linear power before comparison; model inputs and prior results are unchanged. Relative-map ticks show fold change: ½× means half the pre-image return; 2× means twice. The score is bounded, not a probability. Very dark pixels remain susceptible to relative-change noise. Linear-change GeoTIFFs retain the full unclipped values. Red/cyan are explicitly assigned and must not be interpreted as fire/flood labels.\n\n"
    text+="[Numerical display metadata](non_db_metadata.json). Method rationale: [ASF SAR scale guide](https://hyp3-docs.asf.alaska.edu/hyp3-docs/guides/introduction_to_sar/) and [ESA-supported SAR temporal-composite service](https://docs.mcube.terradue.com/services/sar-change/service-specs/). Our red/cyan assignment is post/pre, and is the reverse of services that assign pre-image to red.\n"
    readme.write_text(text)
    print("NON_DB_EDA_DONE",event,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("events",nargs="+")
    for event in parser.parse_args().events: process(event)
