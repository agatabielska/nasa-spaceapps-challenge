"""Geospatial science outputs and presentation assets; invalid stays explicit."""
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform,reproject,Resampling,transform_bounds
from PIL import Image
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt


def write_tif(path,values,meta,nodata):
    transform=Affine(*meta["transform"])
    with rasterio.open(path,"w",driver="GTiff",height=values.shape[0],width=values.shape[1],count=1,
                       dtype=values.dtype,crs=meta["crs"],transform=transform,nodata=nodata,
                       compress="deflate",tiled=True) as dst:
        dst.write(values,1)


def rgba(image,valid):
    rgb=(np.clip(image.transpose(1,2,0),0,1)*255).astype(np.uint8)
    return np.dstack([rgb,(valid*255).astype(np.uint8)])


def export(out,pre,post,valid,score,mask,labels,meta,method,details):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    feature_description=" / ".join(meta.get("feature_names",["co-pol","cross-pol","log-pol ratio"]))
    science_mask=np.where(valid,mask,255).astype(np.uint8)
    write_tif(out/"change_mask.tif",science_mask,meta,255)
    write_tif(out/"valid_mask.tif",valid.astype(np.uint8),meta,None)
    write_tif(out/"change_score.tif",np.where(valid,score,np.nan).astype(np.float32),meta,np.nan)
    before=rgba(pre,valid); after=rgba(post,valid)
    Image.fromarray(before).save(out/"before.png"); Image.fromarray(after).save(out/"after.png")
    overlay=after.copy(); color=np.array([255,45,30],np.float32)
    overlay[mask&valid,:3]=(overlay[mask&valid,:3]*.45+color*.55).astype(np.uint8)
    Image.fromarray(overlay).save(out/"overlay.png")
    mask_rgba=np.zeros((*mask.shape,4),np.uint8); mask_rgba[mask&valid]=[255,45,30,200]
    Image.fromarray(mask_rgba).save(out/"mask.png")
    pseudo=np.zeros((*mask.shape,4),np.uint8); pseudo[valid]=[180,180,50,255]
    pseudo[(labels==0)&valid]=[30,80,160,255]; pseudo[(labels==1)&valid]=[250,50,30,255]
    Image.fromarray(pseudo).save(out/"pseudo_labels.png")
    fig,axes=plt.subplots(2,2,figsize=(10,10))
    for ax,im,title in zip(axes.flat,[before,after,np.ma.masked_invalid(score),overlay],
                           ["Before: "+feature_description,"After: same feature scaling","Continuous change score","Binary surface-change overlay"]):
        ax.imshow(im,cmap="magma" if im.ndim==2 else None); ax.set_title(title); ax.axis("off")
    fig.suptitle(method+" — unvalidated SAR adaptation"); fig.tight_layout(); fig.savefig(out/"overview.png",dpi=140); plt.close(fig)
    # Geographic display assets have a separate, explicit grid suitable for web bounds.
    src_transform=Affine(*meta["transform"])
    bounds=rasterio.transform.array_bounds(*mask.shape,src_transform)
    dst_transform,w,h=calculate_default_transform(meta["crs"],"EPSG:4326",mask.shape[1],mask.shape[0],*bounds,
        dst_width=mask.shape[1],dst_height=mask.shape[0])
    for name,array in [("overlay",overlay),("before",before),("after",after),("mask",mask_rgba)]:
        dest=np.zeros((4,h,w),np.uint8)
        for band in range(4):
            reproject(array[:,:,band],dest[band],src_transform=src_transform,src_crs=meta["crs"],
                      dst_transform=dst_transform,dst_crs="EPSG:4326",resampling=Resampling.nearest)
        Image.fromarray(dest.transpose(1,2,0)).save(out/(name+"_wgs84.png"))
    west,south,east,north=rasterio.transform.array_bounds(h,w,dst_transform)
    # Keep ordinary PNGs at native aspect; geographic cells may be non-square in degrees.
    # The affine/bounds, not assumptions about square degree pixels, define placement.
    Image.fromarray(np.where(valid,np.where(mask,255,0),127).astype(np.uint8)).save(out/"binary_mask_grayscale.png")
    Image.fromarray((valid*255).astype(np.uint8)).save(out/"valid_coverage.png")
    provenance=("This mask is physical SAR log-change plus Otsu thresholding; no neural model is used."
                if method=="SAR log-change + Otsu" else
                "This mask uses frozen VGG features with physical gating and a pseudo-label-trained random forest; the trained translator is not applied."
                if method=="VGG SAR features without translation" else
                "This final mask combines trained UCDFormer translation features, physical change gates and a pseudo-label-trained random forest.")
    (out/"README.md").write_text("# "+method+"\n\n"
        "Start with `overview.png` or `overlay.png` (native projected geometry).\n\n"
        "| File | Meaning |\n|---|---|\n"
        "| before.png / after.png | Shared-scale co-pol / cross-pol / log polarization-ratio false-color composites; not optical photos. |\n"
        "| mask.png | Final binary change mask as a transparent red overlay; not pseudo-labels. |\n"
        "| binary_mask_grayscale.png | White: changed; black: unchanged; gray: unsupported. |\n"
        "| overlay.png | Final mask over the after composite. |\n"
        "| valid_coverage.png | White: scored; black: unsupported. |\n"
        "| pseudo_labels.png | Training seeds: red changed, blue unchanged, yellow uncertain. |\n"
        "| *_wgs84.png | Reprojected geographic overlays; use bounds in study.json. Native aspect preserved using non-square degree pixels. |\n"
        "| change_mask.tif | Georeferenced scientific mask: 0 unchanged, 1 changed, 255 nodata. |\n"
        "| change_score.tif | Continuous feature score, not a probability. |\n"
        "| study.json | Dates, CRS, bounds, area, algorithm and limitations. |\n"
        "| baseline/ | Physical difference plus threshold; no neural model. |\n"
        "| no_translation/ | Frozen VGG feature comparison, without trained translator. |\n\n"
        +provenance+" Accuracy is unvalidated.\n")
    readme=out/"README.md"
    text=readme.read_text()+"\n## Images\n\n"
    for name,description in [
        ("overview.png","Overview of both acquisitions, continuous score and final overlay."),
        ("before.png","Before: shared-scale co-pol / cross-pol / log polarization-ratio SAR composite."),
        ("after.png","After: same channels and scaling as before."),
        ("overlay.png","Final detected change in red over the after acquisition."),
        ("mask.png","Final binary overlay: red changed; otherwise transparent."),
        ("binary_mask_grayscale.png","White changed, black unchanged, gray unsupported."),
        ("valid_coverage.png","White scored; black unsupported."),
        ("pseudo_labels.png","Automatic seed labels: red changed, blue unchanged, yellow uncertain; not ground truth.")]:
        text+=description+"\n\n!["+description+"]("+name+")\n\n"
    text=text.replace("co-pol / cross-pol / log polarization-ratio",feature_description)
    readme.write_text(text)
    area=abs(src_transform.a*src_transform.e)
    report=dict(method=method,status="complete",input_features=meta.get("feature_names"),third_channel=meta.get("third_channel","ratio"),before=Path(meta["before"]["file"]).stem,
                after=Path(meta["after"]["file"]).stem,crs=meta["crs"],transform=meta["transform"],
                wgs84_bounds=[west,south,east,north],display_crs="EPSG:4326",display_transform=list(dst_transform)[:6],
                display_shape=[h,w],display_grid="native image aspect; non-square degree pixels",
                valid_pixels=int(valid.sum()),valid_area_km2=float(valid.sum()*area/1e6),
                changed_pixels=int((mask&valid).sum()),changed_area_km2=float((mask&valid).sum()*area/1e6),
                changed_fraction=float((mask&valid).sum()/max(1,valid.sum())),details=details,
                assets={key:f"{key}_wgs84.png" for key in ["before","after","mask","overlay"]},
                limitations=["No independent reference labels; accuracy not established",
                             "Change score is not a calibrated probability",
                             "Generic backscatter change does not establish a disaster category",
                             "Optical pretrained feature suitability for SAR remains unvalidated",
                             "Independent subpixel co-registration has not been verified; geometry and terrain can cause apparent changes"])
    (out/"study.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    with rasterio.open(out/"change_mask.tif") as check:
        assert check.crs==rasterio.crs.CRS.from_string(meta["crs"])
        assert set(np.unique(check.read(1)))<={0,1,255}
        assert check.nodata==255
    return report
