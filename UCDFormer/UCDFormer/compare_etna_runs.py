"""Show preserved preferred result against the original and completed rerun."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps")); os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

base=ROOT/"outputs/etna"; rerun=ROOT/"outputs/etna_v2"
pair=np.load(base/"pair.npz"); background=10**(pair["physical_post"][0]/20)
v=pair["valid"]; lo,hi=np.percentile(background[v],[1,99]); background=np.clip((background-lo)/(hi-lo),0,1)
fig,axes=plt.subplots(1,3,figsize=(16,6))
results=[]
for ax,path,title in zip(axes,[base,base/"refinement/conservative_candidate",rerun],
                        ["Original UCDFormer/RF","Your preferred conservative result","Separate v2 rerun: new pseudo-labels"]):
    report=json.loads((path/"study.json").read_text())
    with rasterio.open(path/"change_mask.tif") as f: values=f.read(1)
    valid=values!=255; mask=values==1
    ax.imshow(np.ma.array(background,mask=~valid),cmap="gray",vmin=0,vmax=1)
    rgba=np.zeros((*mask.shape,4)); rgba[mask]=[1,.15,.02,.85]; ax.imshow(rgba)
    ax.set_title(title+f'\n{report["changed_pixels"]:,} pixels | {report["changed_area_km2"]:.3f} km²',fontsize=11)
    ax.axis("off"); results.append(dict(name=title,path=str(path.relative_to(ROOT)),pixels=report["changed_pixels"],area_km2=report["changed_area_km2"]))
fig.suptitle("Etna: same observations, different decision pipelines\nRed = flagged change; white = unsupported. No independent accuracy ranking.",fontsize=13)
fig.tight_layout(rect=[0,0,1,.9]); fig.savefig(rerun/"result_comparison.png",dpi=150); plt.close(fig)
(rerun/"result_comparison.json").write_text(json.dumps(results,indent=2)+"\n")
report=json.loads((rerun/"study.json").read_text()); t=json.loads((rerun/"training_summary.json").read_text())
text=f'''# Etna v2: separate end-to-end rerun

The preferred display result remains [the conservative v1 mask](../etna/refinement/conservative_candidate/mask.png). This experiment does not replace it. Selection of the preferred mask reflects the user's visual preference, not measured accuracy.

## What changed

Applied a shared 3×3 masked mean to linear power at both dates before feature construction; incomplete interior support stays invalid and crop-edge reflection is recorded. Re-adapted the original pretrained translator/decoder with the same held-out spatial split, then regenerated all feature scores and pseudo-labels.

New changed seeds require strong physical normalized change, a local robust threshold and high FCM membership in the feature-score high cluster. Unchanged seeds require small physical change and high low-cluster membership. Everything else remains uncertain. New RF descriptors include explicit temporal differences and signed per-polarization normalized change. Uncertain positives require a vote fraction at least 0.8 plus weak physical support connected to a positive seed. Memberships/votes are not calibrated probabilities. This is an explicit UCDFormer extension, not exact paper reproduction.

## Executed result

- Training: {t["updates"]} updates; selected update {t["best_step"]} by held-out translation objective. Objective {t["initial_validation"]:.4f} → {t["best_validation"]:.4f}; this is not change-detection accuracy and is not directly comparable to the differently preprocessed v1 objective.
- New seeds: {report["details"]["changed_seeds"]:,} changed, {report["details"]["unchanged_seeds"]:,} unchanged, {report["details"]["uncertain"]:,} uncertain.
- Final mask: {report["changed_pixels"]:,} pixels, {report["changed_area_km2"]:.4f} km²; {report["changed_fraction"]:.2%} of model support.
- Model support: {report["details"]["model_supported_fraction"]:.2%}. Unsupported tiles near the native invalid samples remain nodata. No independent accuracy established.

![Result comparison](result_comparison.png)

## Pseudo-labels versus final output

Pseudo-labels are only the selected examples used to fit the final RF. Gray in the review figure means uncertain/excluded from fitting, not unchanged or changed. Red/orange and blue are changed/unchanged training examples. The final binary output is shown separately.

![New seeds and final mask](pseudo_labels_review.png)

- [Final mask overlay](mask.png) and [after-image overlay](overlay.png).
- [Grayscale binary display](binary_mask_grayscale.png): black unchanged, white flagged, gray unsupported.
- [Scientific GeoTIFF](change_mask.tif): 0/1/255 nodata.
- [study.json](study.json) and [effective config](effective_config.json) record the method and parameters.
- Physical teacher score, local thresholds, FCM changed membership, connected support and RF votes are exported as separate diagnostic GeoTIFFs. None is ground truth.

The previous conservative mask covers 0.224 km²; this rerun covers about 0.975 km². A larger/smaller mask is not automatically better. Both are retained for review; the preferred selection still points to the conservative result.
'''
(rerun/"README.md").write_text(text)
print(json.dumps(results,indent=2))
