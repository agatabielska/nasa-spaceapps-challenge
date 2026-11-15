"""Diagnostic threshold/denoising ablations; preserves v1 model and mask."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps")); os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import numpy as np
import rasterio
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from nisar.detection import minmax,clean
from nisar.export import write_tif,export

source=ROOT/"outputs/etna"; out=source/"refinement"; out.mkdir(exist_ok=True)
data=np.load(source/"pair.npz"); metadata=json.loads((source/"pair_metadata.json").read_text())
with rasterio.open(source/"change_score.tif") as f: score=f.read(1)
with rasterio.open(source/"change_mask.tif") as f: rf=f.read(1)==1
with rasterio.open(source/"pseudo_labels.tif") as f: labels=f.read(1)
valid=np.isfinite(score)&data["valid"]; n=minmax(score,valid)
sigma=1000/abs(metadata["transform"][0])
background=ndimage.gaussian_filter(np.where(valid,n,0),sigma)/np.maximum(ndimage.gaussian_filter(valid.astype(float),sigma),1e-8)
adaptive=clean((n>2*background)&valid,valid,4)
native=data["valid"]; support=ndimage.uniform_filter(native.astype(float),3,mode="constant")
good=valid&(support>.999)
power0=10**(data["physical_pre"][:2]/10); power1=10**(data["physical_post"][:2]/10)
def relative(a,b): return (b-a)/np.maximum(a+b,1e-20)
raw_relative=np.abs(relative(power0,power1)).mean(0)
def smooth(x):
    return np.stack([ndimage.uniform_filter(np.where(native,c,0),3,mode="constant")/np.maximum(support,1e-8) for c in x])
filtered_relative=np.abs(relative(smooth(power0),smooth(power1))).mean(0)

def local_threshold(values,mask,size=31,k=3,floor=0):
    # Nearest valid values only for window statistics, never as output labels.
    indices=ndimage.distance_transform_edt(~mask,return_distances=False,return_indices=True)
    filled=np.where(mask,values,values[tuple(indices)])
    center=ndimage.median_filter(filled,size=size,mode="reflect")
    residual=ndimage.median_filter(abs(filled-center),size=size,mode="reflect")
    threshold=np.maximum(center+k*1.4826*np.maximum(residual,.001),floor)
    # This is a local-residual MAD proxy, not a calibrated significance test.
    enough=ndimage.uniform_filter(mask.astype(float),size=size,mode="reflect")>=.9
    return (values>threshold)&mask&enough,threshold

feature_local,t0=local_threshold(n,valid,k=3)
physical_raw,t1=local_threshold(raw_relative,good,k=3,floor=.1)
physical_filtered,t2=local_threshold(filtered_relative,good,k=3,floor=.1)
physical_filtered4,t3=local_threshold(filtered_relative,good,k=4,floor=.1)
valid=good  # All variants compared on the same fully supported physical/model grid.
variants={"v1_final_rf":rf&valid,"strict_changed_seeds":(labels==1)&valid,
          "gaussian_adaptive_only":adaptive,"feature_local_residual_k3":feature_local,
          "physical_unfiltered_local_k3":physical_raw,"physical_3x3_local_k3":physical_filtered,
          "physical_3x3_local_k4":physical_filtered4,
          "rf_and_gaussian_support":rf&adaptive&valid,
          "rf_and_physical_local_support":rf&physical_filtered&good}
fig,axes=plt.subplots(3,3,figsize=(12,12))
results={}
for ax,(name,mask) in zip(axes.flat,variants.items()):
    mask=mask&valid
    mask=clean(mask,valid,4) if name not in ["v1_final_rf","strict_changed_seeds"] else mask
    fraction=float(mask.sum()/valid.sum())
    results[name]=dict(changed_pixels=int(mask.sum()),fraction_of_v1_support=fraction)
    write_tif(out/(name+".tif"),np.where(valid,mask,255).astype(np.uint8),metadata,255)
    ax.imshow(np.ma.array(mask,mask=~valid),cmap="gray",vmin=0,vmax=1)
    ax.set_title(name.replace("_"," ")+f"\n{fraction:.2%} of common support",fontsize=9); ax.axis("off")
fig.suptitle("Etna refinement diagnostics: mask size is not accuracy\nSame original checkpoint; physical-filter variants do not retrain or replace UCDFormer",fontsize=13)
fig.tight_layout(rect=[0,0,1,.94]); fig.savefig(out/"threshold_comparison.png",dpi=150); plt.close(fig)
record=dict(variants=results,model_updated=False,selected_final_variant=None,
            physical_score="mean absolute per-polarization normalized difference (post-pre)/(post+pre)",
            threshold="local median + k*1.4826*median-filtered absolute local residual; min residual .001; physical score floor .1",
            window_pixels=31,window_meters=31*abs(metadata["transform"][0]),physical_mean_filter_pixels=3,
            caveats=["Local-residual statistic is a MAD proxy, not exact center-wise MAD or a calibrated significance test",
                     "No accuracy ranking without independent event/reference evidence",
                     "Large true changes can be absorbed into local background",
                     "Physical-filter score is a separate ablation, not denoised UCDFormer training",
                     "Mask intersection gates intentionally change the classifier semantics"])
(out/"comparison.json").write_text(json.dumps(record,indent=2)+"\n")
candidate=clean(variants["rf_and_physical_local_support"],valid,4)
export(out/"conservative_candidate",data["pre"],data["post"],valid,filtered_relative,candidate,labels,
       metadata,"UCDFormer RF + conservative physical support gate",
       dict(status="unvalidated candidate; not selected as most accurate",model_retrained=False,
            gate="RF positive AND physical 3x3-power normalized-change local-residual threshold",
            physical_relative_score_floor=.1,local_window_m=620,k=3,
            continuous_score="mean absolute HH/HV normalized physical return difference; NOT VGG score or probability",
            pseudo_labels="original v1 seeds displayed as context; not new ground truth",
            limitation="Conservative intersection can miss true changes; no accuracy ranking established"))
seeds=int(((labels==1)&valid).sum()); predictions=int((rf&valid).sum())
(out/"README.md").write_text(f'''# Etna threshold and denoising ablations

These diagnostics preserve v1 outputs and the trained checkpoint. The original RF expands {seeds} confident positive seeds to {predictions} changed pixels. That expansion, feature-domain mismatch and terrain shifts are plausible causes of broad detections; speckle is not the only hypothesis.

![Mask comparisons](threshold_comparison.png)

No variant is designated the most accurate. Smaller maps are not automatically better. Physical variants compare unfiltered and 3×3 linear-power mean inputs using a normalized relative-change score; their local windows span 620 m. The robust threshold uses a local-residual MAD approximation and is not a statistical p-value. The physical score floor 0.1 is a sensitivity parameter, not a learned or validated decision boundary. Maps use the common v1 support so counts can be compared. Raw GeoTIFFs and [parameters/counts](comparison.json) are retained.

RF intersection variants are conservative gates that may reduce false alarms but can also remove genuine changes. A new filtered UCDFormer input pipeline would require consistent re-adaptation, not just these post-hoc maps. Next review the actual event structure, seed geography, registration and residual images before selecting a v2 output. See [literature applicability review](../../../SAR_DENOISING_REVIEW.md).

An app-ready [conservative candidate](conservative_candidate/study.json) is exported separately with its physical score, gate parameters, mask and geographic overlays. It is explicitly unvalidated and does not replace the original model result or establish the best threshold.
''')
print(json.dumps(results,indent=2),flush=True)
