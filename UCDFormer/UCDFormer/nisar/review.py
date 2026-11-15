"""Legended seed/final-mask review: uncertain labels are not the final change map."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from PIL import Image


def pseudo_review(out,pre,post,valid,labels,mask,extras,details):
    out=Path(out)
    cmap=ListedColormap(["#d5d5d5","#287eb8","#f34f22"])
    norm=BoundaryNorm([-.5,.5,1.5,2.5],3)
    classes=np.where(labels==-1,0,np.where(labels==0,1,2))
    background=post[0]
    fig,axes=plt.subplots(2,3,figsize=(14,9))
    im=axes[0,0].imshow(np.ma.array(extras["physical_score"],mask=~valid),cmap="magma",vmin=0,vmax=.5)
    axes[0,0].set_title("Filtered physical change score\nmean absolute co/cross-pol normalized difference")
    fig.colorbar(im,ax=axes[0,0],shrink=.7,label="Relative score; not probability")
    axes[0,1].imshow(np.ma.array(classes,mask=~valid),cmap=cmap,norm=norm)
    axes[0,1].set_title("NEW pseudo-labels: training seeds only")
    axes[0,1].legend(handles=[Patch(color="#f34f22",label="Changed seed"),Patch(color="#287eb8",label="Unchanged seed"),
                              Patch(color="#d5d5d5",label="Uncertain / excluded from fitting")],fontsize=8,loc="lower left")
    axes[0,2].imshow(np.ma.array(mask,mask=~valid),cmap="gray",vmin=0,vmax=1)
    axes[0,2].set_title("NEW final binary mask\nwhite = change; invalid transparent")
    for ax,selected,title,color in [(axes[1,0],labels==1,"Changed seeds over after-image",[1,.2,.05]),
                                    (axes[1,1],labels==0,"Unchanged seeds over after-image",[.1,.5,1]),
                                    (axes[1,2],extras["candidate_support"]==1,"Weak physical support connected to changed seeds",[1,.65,0])]:
        ax.imshow(np.ma.array(background,mask=~valid),cmap="gray",vmin=0,vmax=1)
        layer=np.zeros((*mask.shape,4)); layer[selected&valid,:3]=color; layer[selected&valid,3]=.75
        ax.imshow(layer); ax.set_title(title)
    for ax in axes.flat: ax.axis("off")
    fig.suptitle(f'{out.name} | {details["changed_seeds"]:,} changed seeds | {details["unchanged_seeds"]:,} unchanged seeds | '
                 f'{details["uncertain"]:,} uncertain\nPseudo-labels train the RF; they are not independently verified ground truth',fontsize=13)
    fig.tight_layout(rect=[0,0,1,.92]); fig.savefig(out/"pseudo_labels_review.png",dpi=150); plt.close(fig)
    gray=np.where(valid,np.where(mask,255,0),127).astype(np.uint8)
    Image.fromarray(gray).save(out/"binary_mask_grayscale.png")
