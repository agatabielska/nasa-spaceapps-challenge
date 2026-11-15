"""Windowed GCOV reader, paired normalization and spatially separated patches."""
import json
from pathlib import Path
import h5py
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import transform_bounds, reproject, Resampling
from scipy import ndimage
import torch
from torch.utils.data import Dataset


POL={"HH":"HHHH","HV":"HVHV","VH":"VHVH","VV":"VVVV"}


def read_gcov(path,bbox,channels=("HH","HV")):
    with h5py.File(path,"r") as f:
        g=f["science/LSAR/GCOV/grids/frequencyA"]
        available=[p for p,key in POL.items() if key in g]
        if not set(channels)<=set(available): raise ValueError(f"Missing {channels}; available {available}")
        x=g["xCoordinates"][:]; y=g["yCoordinates"][:]
        dx=float(g["xCoordinateSpacing"][()]); dy=float(g["yCoordinateSpacing"][()])
        if dx<=0 or dy>=0 or not np.allclose(np.diff(x),dx) or not np.allclose(np.diff(y),dy):
            raise ValueError("Reader requires regular north-up grid; refusing implicit orientation change")
        crs=CRS.from_epsg(int(g["projection"][()]))
        left,bottom,right,top=transform_bounds("EPSG:4326",crs,*bbox,densify_pts=21)
        cols=np.flatnonzero((x>=left)&(x<=right)); rows=np.flatnonzero((y>=bottom)&(y<=top))
        if not len(cols) or not len(rows): raise ValueError("AOI does not intersect raster centers")
        r0,r1=int(rows[0]),int(rows[-1])+1; c0,c1=int(cols[0]),int(cols[-1])+1
        values=np.stack([g[POL[p]][r0:r1,c0:c1] for p in channels]).astype(np.float32)
        # A declared fill may be positive, so a >0 power test alone is insufficient.
        declared_fill=np.zeros(values.shape[1:],bool)
        fill_metadata={}
        for p,band in zip(channels,values):
            fills=[]
            for name in ("_FillValue","missing_value"):
                if name not in g[POL[p]].attrs: continue
                for value in np.asarray(g[POL[p]].attrs[name]).ravel():
                    value=float(value)
                    if np.isfinite(value):
                        declared_fill |= band==np.float32(value)
                        fills.append(value)
            fill_metadata[p]=fills
        mask=g["mask"][r0:r1,c0:c1]
        n=int(g["numberOfSubSwaths"][()])
        valid=(mask>0)&(mask<=n)&np.all(np.isfinite(values)&(values>0),axis=0)&~declared_fill
        if "inputDataExceptionMask" in g:
            valid &= g["inputDataExceptionMask"][r0:r1,c0:c1]==0
        affine=Affine(dx,0,float(x[c0]-dx/2),0,dy,float(y[r0]-dy/2))
        attrs={k:str(v) for k,v in g["mask"].attrs.items() if k!="DIMENSION_LIST"}
        metadata=dict(file=str(Path(path).resolve()),channels=list(channels),available=available,
                      frequency="A",crs=crs.to_string(),transform=list(affine)[:6],shape=list(valid.shape),
                      native_window=[r0,c0,r1,c1],pixel_spacing=[dx,dy],mask_attributes=attrs,
                      declared_fill_values=fill_metadata,declared_fill_pixels=int(declared_fill.sum()),
                      positive_valid_fraction=float(valid.mean()))
    return values,valid,affine,crs,metadata


def align_pair(a,b,bbox,channels=("HH","HV")):
    pre,v0,t0,c0,m0=read_gcov(a,bbox,channels)
    post,v1,t1,c1,m1=read_gcov(b,bbox,channels)
    reprojection=False
    if pre.shape!=post.shape or c0!=c1 or not t0.almost_equals(t1):
        # Masked linear-power resampling; invalid neighbors cannot brighten valid values.
        target=np.full_like(pre,np.nan)
        source=np.where(v1[None],post,np.nan)
        for channel in range(len(post)):
            reproject(source[channel],target[channel],src_transform=t1,src_crs=c1,
                      dst_transform=t0,dst_crs=c0,src_nodata=np.nan,dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
        warped=np.zeros(v0.shape,np.uint8)
        reproject(v1.astype(np.uint8),warped,src_transform=t1,src_crs=c1,
                  dst_transform=t0,dst_crs=c0,resampling=Resampling.nearest)
        v1=(warped==1)&np.all(np.isfinite(target)&(target>0),axis=0)
        post=target; reprojection=True
    valid=v0&v1
    pre=np.where(valid[None],pre,np.nan); post=np.where(valid[None],post,np.nan)
    return pre,post,valid,dict(before=m0,after=m1,bbox_wgs84=bbox,transform=list(t0)[:6],
                              crs=c0.to_string(),shape=list(valid.shape),reprojected_after=reprojection,
                              registration_status="same-track geocoded grids; no independent subpixel registration truth")


def select_polarizations(before,after):
    common=None
    for path in (before,after):
        with h5py.File(path,'r') as source:
            group=source['science/LSAR/GCOV/grids/frequencyA']
            available={p for p,key in POL.items() if key in group}
            common=available if common is None else common&available
    if {'HH','HV'}<=common:return ('HH','HV')
    raise ValueError(f'Pipeline requires HH and HV in frequencyA at both dates; common channels: {sorted(common)}')


def physical_features(power):
    if power.shape[0]!=2:raise ValueError('Feature adapter requires HH/HV power')
    db=10*np.log10(power)
    return np.stack([db[0],db[1],db[0]-db[1]]).astype(np.float32)


def filter_pair_power(a,b,valid,size):
    """Same masked linear-power mean at both dates; exclude incomplete support.

    Reflect padding at the crop's outer edge is an explicit boundary assumption.
    Missing interior observations are never made valid by filtering.
    """
    if size==1: return a,b,valid.copy()
    if size<1 or size%2!=1: raise ValueError("Power filter width must be a positive odd integer")
    support=ndimage.uniform_filter(valid.astype(np.float64),size=size,mode="reflect")
    good=valid&(support>=1-1e-8)
    def apply(x):
        values=np.stack([ndimage.uniform_filter(np.where(valid,c,0).astype(np.float64),size=size,mode="reflect")/
                         np.maximum(support,1e-12) for c in x]).astype(np.float32)
        return np.where(good[None],values,np.nan)
    return apply(a),apply(b),good


def fit_scaler(a,b,mask):
    if not mask.any(): raise ValueError("No valid scaler samples")
    bounds=[]
    for x,y in zip(a,b):
        values=np.concatenate([x[mask],y[mask]])
        lo,hi=np.percentile(values,[1,99]); bounds.append([float(lo),float(max(hi,lo+1e-4))])
    return np.asarray(bounds,np.float32)


def apply_scaler(features,bounds):
    result=(features-bounds[:,0,None,None])/(bounds[:,1,None,None]-bounds[:,0,None,None])
    return np.nan_to_num(np.clip(result,0,1),nan=0).astype(np.float32)


def fit_standardization(pre,post,mask):
    """Fit population statistics after percentile scaling, on both training dates."""
    if not mask.any(): raise ValueError("No valid standardization samples")
    values=np.concatenate([pre[:,mask],post[:,mask]],axis=1).astype(np.float64)
    if not np.isfinite(values).all(): raise ValueError("Nonfinite standardization samples")
    return dict(method="nisar_pair_channel_zscore_v1",input="percentile_scaled_0_1",
                fit="both dates, training support only",ddof=0,std_floor=1e-6,
                mean=values.mean(axis=1).tolist(),
                std=np.maximum(values.std(axis=1),1e-6).tolist())


def positions(length,size,stride):
    if length<size: return []
    result=list(range(0,length-size+1,stride))
    if result[-1]!=length-size: result.append(length-size)
    return result


def spatial_split(valid,train_size=256,val_size=128):
    """North training strip and south validation strip, separated by an explicit moat.

    On ~10 km / 20 m AOIs, 128-pixel validation preserves disjoint spatial support.
    Validation resolution is unchanged; only its field of view is smaller.
    """
    h,w=valid.shape
    train_rows=train_size
    val_y=h-val_size
    gap=val_y-train_rows
    train=[(0,x,train_size) for x in positions(w,train_size,64)
           if valid[:train_size,x:x+train_size].all()]
    validation=[(val_y,x,val_size) for x in positions(w,val_size,val_size)
                if valid[val_y:val_y+val_size,x:x+val_size].all()]
    if gap<64 or not train or not validation:
        # Prefer larger fully measured crops, then smaller ones; preserve the moat.
        # Search both axes so narrow/tall scenes do not require special settings.
        integral=np.pad(valid.astype(np.int64),((1,0),(1,0))).cumsum(0).cumsum(1)
        for n in (128,64,32):
            step=max(8,n//4)
            candidates=[]
            for y in positions(h,n,step):
                for x in positions(w,n,step):
                    count=integral[y+n,x+n]-integral[y,x+n]-integral[y+n,x]+integral[y,x]
                    if count==n*n:candidates.append((y,x,n))
            choices=[]
            for axis,length in ((0,h),(1,w)):
                for boundary in range(n,length-n-64+1,step):
                    tr=[t for t in candidates if t[axis]+n<=boundary]
                    va=[t for t in candidates if t[axis]>=boundary+64]
                    if tr and va:choices.append((min(len(tr),32)+min(len(va),8),axis,boundary,tr,va))
            if not choices:continue
            _,axis,boundary,train,validation=max(choices,key=lambda c:c[0])
            def sample(windows,count):
                return [windows[i] for i in np.linspace(0,len(windows)-1,min(count,len(windows)),dtype=int)]
            train=sample(train,32);validation=sample(validation,8)
            fit_mask=np.zeros_like(valid)
            for y,x,size in train:fit_mask[y:y+size,x:x+size]=True
            return train,validation,fit_mask,dict(split_axis='rows' if axis==0 else 'columns',
                train_extent=[0,boundary],validation_extent=[boundary+64,h if axis==0 else w],
                gap_pixels=64,train_patch_size=n,val_patch_size=n,train_windows=len(train),
                validation_windows=len(validation),fallback='automatic fully valid crops; no inpainting in training')
        raise ValueError(f'Scene {h}x{w} has insufficient fully valid spatially separated training/validation support '
                         '(minimum 32-pixel patches with a 64-pixel moat). Use a larger AOI or another pair; '
                         'missing observations are not training data.')
    fit_mask=np.zeros_like(valid); fit_mask[:train_size]=valid[:train_size]
    return train,validation,fit_mask,dict(train_rows=[0,train_rows],validation_rows=[val_y,h],
                                        gap_pixels=gap,train_patch_size=train_size,val_patch_size=val_size,
                                        train_windows=len(train),validation_windows=len(validation))


class PairedChangeDataset(Dataset):
    def __init__(self,pre,post,valid,windows):
        self.pre=pre; self.post=post; self.valid=valid; self.windows=windows

    def __len__(self): return len(self.windows)

    def __getitem__(self,index):
        y,x,n=self.windows[index]
        v=self.valid[y:y+n,x:x+n]
        if not v.all(): raise ValueError("Translation loss currently accepts fully valid patches only")
        return {"pre":torch.from_numpy(self.pre[:,y:y+n,x:x+n].copy()),
                "post":torch.from_numpy(self.post[:,y:y+n,x:x+n].copy()),
                "valid":torch.from_numpy(v.copy()),"window":(y,x,n)}


def prepare(config,out):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    channels=select_polarizations(config["before"],config["after"])
    a,b,valid,meta=align_pair(config["before"],config["after"],config["bbox"],channels)
    if not CRS.from_string(meta['crs']).is_projected:
        raise ValueError('Model processing requires a projected metric GCOV grid')
    trace={} if config.get("visualize_steps") else None
    if trace is not None:
        trace.update(aligned_raw_power_pre=a.copy(),aligned_raw_power_post=b.copy(),raw_valid=valid.copy())
    filter_size=int(config.get("power_mean_filter_size",1))
    a,b,valid=filter_pair_power(a,b,valid,filter_size)
    if not valid.any(): raise ValueError("No common valid observations remain after preprocessing")
    train,val,fit_mask,split=spatial_split(valid)
    f0,f1=physical_features(a),physical_features(b)
    bounds=fit_scaler(f0,f1,fit_mask)
    pre,post=apply_scaler(f0,bounds),apply_scaler(f1,bounds)
    standardization=fit_standardization(pre,post,fit_mask)
    if trace is not None:
        mean=np.asarray(standardization["mean"])[:,None,None]
        std=np.asarray(standardization["std"])[:,None,None]
        trace.update(filtered_power_pre=a,filtered_power_post=b,filtered_valid=valid,
                     physical_features_pre=f0,physical_features_post=f1,
                     percentile_scaled_pre=pre,percentile_scaled_post=post,
                     vgg_input_pre=np.where(valid[None],(pre-mean)/std,np.nan),
                     vgg_input_post=np.where(valid[None],(post-mean)/std,np.nan),
                     standardization_fit_support=fit_mask)
        folder=out/"steps"; folder.mkdir(exist_ok=True)
        np.savez_compressed(folder/"01_preprocessing.npz",**trace)
    meta.update(feature_names=[f"{channels[0]}_dB",f"{channels[1]}_dB",
                               f"{channels[0]}_dB_minus_{channels[1]}_dB"],
                third_channel="ratio",normalization_bounds=bounds.tolist(),
                normalization_fit="both dates, training strip only",split=split,
                vgg_standardization=standardization,visualize_steps=bool(config.get("visualize_steps")),
                valid_fraction=float(valid.mean()),train_windows=train,validation_windows=val,
                speckle_filter="none; native GCOV multilooking retained" if filter_size==1 else
                    f"{filter_size}x{filter_size} masked linear-power mean, reflect crop boundary; incomplete interior support excluded",
                power_mean_filter_size=filter_size)
    np.savez_compressed(out/"pair.npz",pre=pre,post=post,valid=valid,physical_pre=f0,physical_post=f1)
    acquisitions={key:meta[key] for key in ('before','after','bbox_wgs84')}
    (out/"acquisition_metadata.json").write_text(json.dumps(acquisitions,indent=2)+"\n")
    processing={key:value for key,value in meta.items() if key not in acquisitions}
    (out/"preprocessing.json").write_text(json.dumps(processing,indent=2)+"\n")
    # Compatibility assembly for existing export and EDA helpers; primary records above are separated.
    (out/"pair_metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    return pre,post,valid,meta
