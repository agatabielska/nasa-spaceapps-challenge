"""Opt-in coherence corroboration; phase validity never gates coherence."""
from pathlib import Path
from datetime import datetime,timezone
import h5py
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform_bounds,reproject,Resampling
from scipy import ndimage

POLICY=dict(version='coherence_physical_support_v1',incoherence_floor=.5,robust_k=1.0,
            minimum_mad=.001,physical_low_fraction=.75)


def text(group,key):
    value=group[key][()]
    return value.decode() if isinstance(value,bytes) else value.item() if isinstance(value,np.generic) else value


def time(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def native_valid(mask):
    low=mask&255
    return (low!=255)&((low%100)//10>0)&(low%10>0)&(low//100<=1)&(((mask>>8)&65535)==0)


def project_valid(valid,source_meta,target_meta):
    """Only accept coarse footprints with complete measured GCOV coverage."""
    src=Affine(*source_meta['transform']);dst=Affine(*target_meta['transform'])
    pad=int(np.ceil(max(abs(dst.a),abs(dst.e))/min(abs(src.a),abs(src.e))))+2
    fraction=np.zeros(target_meta['shape'],np.float32)
    reproject(np.pad(valid.astype(np.float32),pad),fraction,
              src_transform=src*Affine.translation(-pad,-pad),src_crs=source_meta['crs'],
              dst_transform=dst,dst_crs=target_meta['crs'],resampling=Resampling.average,
              src_nodata=None,dst_nodata=None)
    return fraction>=1-1e-6,fraction


def incoherence_support(coherence,valid,policy):
    valid=valid&np.isfinite(coherence)&(coherence>=0)&(coherence<=1)
    values=(1-coherence)[valid]
    if not len(values):raise ValueError('No valid GUNW coherence remains after GCOV nodata exclusion')
    median=float(np.median(values));mad=float(np.median(abs(values-median)))
    threshold=max(policy['incoherence_floor'],median+policy['robust_k']*1.4826*max(mad,policy['minimum_mad']))
    return valid,((1-coherence)>threshold)&valid,dict(threshold=threshold,median=median,mad=mad,
           fitted_native_valid_pixels=int(valid.sum()),formula='max(floor, median(1-coherence) + k*1.4826*max(MAD, minimum_mad))')


def load_gunw(path,config,meta):
    """Read the native wrapped-interferogram coherence, mask first, then threshold."""
    from nisar.data import align_pair
    policy=dict(config.get('gunw_support_policy',POLICY))
    path=Path(path)
    if not path.is_file():raise ValueError(f'GUNW file not found: {path}')
    with h5py.File(path,'r') as f:
        ident=f['science/LSAR/identification']
        if text(ident,'productType')!='GUNW':raise ValueError('--gunw requires a GUNW product')
        gunw_id={key:text(ident,key) for key in ('trackNumber','frameNumber','lookDirection','orbitPassDirection',
                    'referenceZeroDopplerStartTime','secondaryZeroDopplerStartTime','compositeReleaseId')}
        dates=[]
        for source in (config['before'],config['after']):
            with h5py.File(source,'r') as gcov:
                source_id=gcov['science/LSAR/identification']
                for key in ('trackNumber','frameNumber','lookDirection','orbitPassDirection'):
                    if str(text(source_id,key)).lower()!=str(gunw_id[key]).lower():
                        raise ValueError(f'GUNW and GCOV mismatch: {key}')
                dates.append(text(source_id,'zeroDopplerStartTime'))
        start=time(gunw_id['referenceZeroDopplerStartTime']);end=time(gunw_id['secondaryZeroDopplerStartTime'])
        if not start<end or end<=time(dates[0]) or start>=time(dates[1]):
            raise ValueError('GUNW interval does not overlap the GCOV before/after interval')
        g=f['science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram']
        if 'HH' not in g:raise ValueError('GUNW requires HH coherence')
        crs=rasterio.crs.CRS.from_epsg(int(g['projection'][()]))
        x=g['xCoordinates'][:];y=g['yCoordinates'][:]
        dx=float(g['xCoordinateSpacing'][()]);dy=float(g['yCoordinateSpacing'][()])
        if dx<=0 or dy>=0:raise ValueError('GUNW requires a north-up grid')
        left,bottom,right,top=transform_bounds('EPSG:4326',crs,*config['bbox'],densify_pts=21)
        cols=np.flatnonzero((x>=left)&(x<=right));rows=np.flatnonzero((y>=bottom)&(y<=top))
        if not len(cols) or not len(rows):raise ValueError('GUNW does not cover the requested AOI')
        sl=(slice(rows[0],rows[-1]+1),slice(cols[0],cols[-1]+1))
        coherence=g['HH/coherenceMagnitude'][sl].astype(np.float32)
        native=native_valid(g['mask'][sl])
        fill=g['HH/coherenceMagnitude'].attrs.get('_FillValue',np.nan)
        if np.isfinite(fill):native &= coherence!=fill
        native_meta=dict(crs=crs.to_string(),shape=list(coherence.shape),
            transform=[dx,0,float(x[cols[0]]-dx/2),0,dy,float(y[rows[0]]-dy/2)])
    _,_,gcov_valid,gcov_meta=align_pair(config['before'],config['after'],config['bbox'])
    gcov_on_native,fraction=project_valid(gcov_valid,gcov_meta,native_meta)
    combined,candidate,stats=incoherence_support(coherence,native&gcov_on_native,policy)
    coherence=np.where(combined,coherence,np.nan)
    aligned=np.full(meta['shape'],np.nan,np.float32)
    aligned_valid=np.zeros(meta['shape'],np.uint8);aligned_candidate=aligned_valid.copy()
    kwargs=dict(src_transform=Affine(*native_meta['transform']),src_crs=native_meta['crs'],
                dst_transform=Affine(*meta['transform']),dst_crs=meta['crs'],resampling=Resampling.nearest)
    reproject(coherence,aligned,src_nodata=np.nan,dst_nodata=np.nan,**kwargs)
    reproject(combined.astype(np.uint8),aligned_valid,**kwargs)
    reproject(candidate.astype(np.uint8),aligned_candidate,**kwargs)
    good=(aligned_valid==1)&gcov_valid&np.isfinite(aligned)
    aligned=np.where(good,aligned,np.nan)
    result=dict(coherence=aligned,valid=good,candidate=(aligned_candidate==1)&good,threshold=stats['threshold'])
    details=dict(path=str(path.resolve()),file_bytes=path.stat().st_size,identification=gunw_id,gcov_dates=dates,
        same_acquisition_dates=all(abs((time(a)-time(b)).total_seconds())<1 for a,b in zip(dates,[gunw_id['referenceZeroDopplerStartTime'],gunw_id['secondaryZeroDopplerStartTime']])),
        native_grid=native_meta,policy=policy,threshold_fit=stats,
        native_excluded_by_gcov=int((native&~gcov_on_native).sum()),native_usable_pixels=int(combined.sum()),
        alignment='nearest-sample native coherence and binary support to GCOV grid; no new 10 m information',
        validity='GCOV HH/HV both dates + full coarse-footprint coverage + native GUNW mask + finite coherence in [0,1]',
        phase_used=False,phase_component_mask_used=False,minimum_coherence_cutoff_used=False,
        limitations=['Low coherence is supporting evidence, not an event probability',
                    'No pre-event coherence baseline; no claim of measured coherence loss',
                    'Different acquisition dates are allowed only with temporal overlap; this does not verify event bracketing',
                    'Outside valid GUNW coverage the original GCOV processing remains available'])
    return result,details,dict(coherence=coherence,valid=combined,candidate=candidate,gcov_valid=gcov_on_native,gcov_valid_fraction=fraction)


def augment_physical_support(weak,physical,low,labels,positives,valid,gunw,connectivity,policy):
    """Expand only physically plausible uncertain corridors connected to seeds."""
    moderate=(physical>policy['physical_low_fraction']*low)&valid
    added=moderate&gunw['valid']&gunw['candidate']&(labels==-1)&~weak
    candidate=weak|added
    structure=ndimage.generate_binary_structure(2,1 if connectivity==4 else 2)
    components,_=ndimage.label(candidate,structure=structure)
    seeds=np.unique(components[positives]);seeds=seeds[seeds>0]
    support=np.isin(components,seeds)&valid
    return support,added,moderate


def save_review(out,gunw,valid,baseline,result,added_support):
    """Compare opt-in effects using the same features/seeds/RF, not another run."""
    from matplotlib import pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    from PIL import Image
    out=Path(out)
    eligible=gunw['valid']&valid
    Image.fromarray(eligible.astype(np.uint8)*255).save(out/'gunw_valid_binary.png')
    fig,axes=plt.subplots(2,3,figsize=(14,9))
    gray=plt.get_cmap('gray').with_extremes(bad='#b0b0b0')
    views=[(axes[0,0],np.where(eligible,1-gunw['coherence'],np.nan),'GUNW incoherence: validity applied first','magma'),
           (axes[0,1],eligible.astype(float),'WHITE = usable GUNW | BLACK = excluded','gray'),
           (axes[0,2],np.where(valid,added_support.astype(float),np.nan),'Additional seed-connected physical support',gray),
           (axes[1,0],np.where(valid,baseline.astype(float),np.nan),'Original result without GUNW (same model/RF)',gray),
           (axes[1,1],np.where(valid,result.astype(float),np.nan),'Optional GUNW-supported result',gray)]
    for ax,values,title,cmap in views:
        if cmap=='magma':cmap=plt.get_cmap('magma').with_extremes(bad='#b0b0b0')
        ax.imshow(values,cmap=cmap,vmin=0,vmax=1,interpolation='nearest');ax.set_title(title,fontsize=10)
    change=np.where(result&~baseline,1,np.where(baseline&~result,-1,0)).astype(float)
    change[~valid]=np.nan
    cmap=ListedColormap(['#2b8cbe','#eeeeee','#e34a33']).with_extremes(bad='#999999')
    axes[1,2].imshow(change,cmap=cmap,norm=BoundaryNorm([-1.5,-.5,.5,1.5],3),interpolation='nearest')
    axes[1,2].set_title('Effect: red added | blue removed | light gray same',fontsize=10)
    for ax in axes.flat:ax.axis('off')
    fig.suptitle('Opt-in GUNW coherence support before RF — no phase cutoff; no changes to VGG inputs\nOutside usable GUNW coverage the original GCOV path remains available',fontsize=12)
    fig.tight_layout(rect=[0,0,1,.93]);fig.savefig(out/'gunw_comparison.png',dpi=140);plt.close(fig)
