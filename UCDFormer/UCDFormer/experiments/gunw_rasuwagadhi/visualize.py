"""Isolated GUNW interval EDA and comparison to existing step-03 masks.

No detector execution, mask fusion, model adaptation or pipeline edits.
"""
import sys,os,json,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-gunw-visualization')
import h5py
import numpy as np
import rasterio
from rasterio.transform import Affine,array_bounds
from rasterio.warp import transform_bounds,reproject,Resampling
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from nisar.data import align_pair
HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/experiments/gunw_rasuwagadhi';OUT.mkdir(parents=True,exist_ok=True)
SOURCE='https://nisar-docs.asf.alaska.edu/gunw/'


def decode_mask(values):
    """Interpret lower-byte decimal subswath digits and documented anomaly bytes."""
    code=values&255
    reference=(code%100)//10;secondary=code%10;water=code//100
    anomaly=(values>>8)&65535
    return (code!=255)&(reference>0)&(secondary>0)&(water<=1)&(anomaly==0)


def read_group(f,name,bbox):
    g=f['science/LSAR/GUNW/grids/frequencyA/'+name]
    crs=rasterio.crs.CRS.from_epsg(int(g['projection'][()]))
    x=g['xCoordinates'][:];y=g['yCoordinates'][:]
    dx=float(g['xCoordinateSpacing'][()]);dy=float(g['yCoordinateSpacing'][()])
    left,bottom,right,top=transform_bounds('EPSG:4326',crs,*bbox,densify_pts=21)
    cols=np.flatnonzero((x>=left)&(x<=right));rows=np.flatnonzero((y>=bottom)&(y<=top))
    if not len(cols) or not len(rows):raise ValueError('AOI outside GUNW grid')
    sl=(slice(rows[0],rows[-1]+1),slice(cols[0],cols[-1]+1))
    arrays={key:ds[sl] for key,ds in g['HH'].items() if isinstance(ds,h5py.Dataset) and ds.ndim==2}
    mask=g['mask'][sl];valid=decode_mask(mask)
    for key,array in arrays.items():
        fills=g['HH'][key].attrs.get('_FillValue',np.nan)
        good=valid&np.isfinite(array)
        if np.isfinite(fills):good &= array!=fills
        arrays[key]=np.where(good,array,np.nan)
    transform=Affine(dx,0,float(x[cols[0]]-dx/2),0,dy,float(y[rows[0]]-dy/2))
    meta=dict(crs=crs.to_string(),transform=list(transform)[:6],shape=list(mask.shape),pixel_size_m=[dx,dy],
              native_window=[int(rows[0]),int(cols[0]),int(rows[-1]+1),int(cols[-1]+1)],
              mask_values={str(int(k)):int(v) for k,v in zip(*np.unique(mask,return_counts=True))},
              anomaly_bits_policy='bits 8-23 excluded; reserved upper byte recorded without interpreting it as an anomaly',
              reserved_upper_byte_nonzero=int(((mask>>24)!=0).sum()))
    np.savez_compressed(OUT/(name+'_crop.npz'),**arrays,mask=mask,valid=valid)
    return arrays,meta,valid


def extent(meta):
    left,bottom,right,top=array_bounds(*meta['shape'],Affine(*meta['transform']))
    return [left/1000,right/1000,bottom/1000,top/1000]


def panel(ax,array,meta,title,cmap='viridis',limits=None):
    if limits is None:
        v=array[np.isfinite(array)]
        limits=np.percentile(v,[2,98]) if len(v) else [0,1]
        if limits[0]==limits[1]:limits=[limits[0],limits[0]+1]
    color=plt.get_cmap(cmap).with_extremes(bad='#d6d6d6')
    im=ax.imshow(np.ma.masked_invalid(array),extent=extent(meta),origin='upper',cmap=color,vmin=limits[0],vmax=limits[1],interpolation='nearest')
    ax.set_title(title,fontsize=10);ax.set_xlabel('UTM easting (km)');ax.set_ylabel('UTM northing (km)')
    plt.colorbar(im,ax=ax,shrink=.65)


def contour(ax,mask,meta):
    t=Affine(*meta['transform']);h,w=mask.shape
    x=(t.c+(np.arange(w)+.5)*t.a)/1000;y=(t.f+(np.arange(h)+.5)*t.e)/1000
    if mask.any() and not mask.all():ax.contour(x,y,mask.astype(float),levels=[.5],colors=['#00ffff'],linewidths=.6)


def summary(values):
    v=values[np.isfinite(values)]
    return dict(finite_pixels=int(len(v)),minimum=float(v.min()),maximum=float(v.max()),median=float(np.median(v)),q10=float(np.quantile(v,.1)),q90=float(np.quantile(v,.9))) if len(v) else dict(finite_pixels=0)


def main():
    manifest=json.loads((HERE/'download_manifest.json').read_text())
    inputs=json.loads((ROOT/'configs/nepal_rasuwagadhi_run.json').read_text());bbox=inputs['bbox']
    with h5py.File(manifest['file'],'r') as f:
        identification=f['science/LSAR/identification']
        times={key:identification[key][()].decode() for key in ['referenceZeroDopplerStartTime','secondaryZeroDopplerStartTime']}
        # Explicitly check the interval matches the GCOV pair being displayed.
        if '20260819T233918' not in inputs['before'] or '20260831T233918' not in inputs['after']:
            raise ValueError('This isolated experiment expects the matching August 19/31 GCOV pair')
        wrapped,wm,wvalid=read_group(f,'wrappedInterferogram',bbox)
        unw,um,uvalid=read_group(f,'unwrappedInterferogram',bbox)
    pre,post,valid,meta=align_pair(inputs['before'],inputs['after'],bbox)
    db0=10*np.log10(pre);db1=10*np.log10(post)
    lo,hi=np.nanpercentile(np.concatenate([db0[0].ravel(),db1[0].ravel()]),[2,98])
    coherence=wrapped['coherenceMagnitude']
    coherence=np.where((coherence>=0)&(coherence<=1),coherence,np.nan)
    wrapped_phase=np.where(abs(wrapped['wrappedInterferogram'])>0,np.angle(wrapped['wrappedInterferogram']),np.nan)
    components=unw['connectedComponents']
    phase_valid=uvalid&np.isfinite(components)&(components>0)&(components!=65535)&np.isfinite(unw['unwrappedPhase'])
    phase=np.where(phase_valid,unw['unwrappedPhase'],np.nan)
    phase_reliable=np.where(phase_valid&(unw['coherenceMagnitude']>=.3),phase,np.nan)
    physical=np.abs((post-pre)/np.maximum(post+pre,1e-20)).mean(0)
    phase_limits=np.nanpercentile(phase,[2,98])
    fig,axes=plt.subplots(3,3,figsize=(17,16))
    for ax,array,m,title,cmap,limits in [
      (axes[0,0],db0[0],meta,'GCOV before: Aug 19 HH dB (10 m)','gray',[lo,hi]),
      (axes[0,1],db1[0],meta,'GCOV after: Aug 31 HH dB (10 m)','gray',[lo,hi]),
      (axes[0,2],physical,meta,'GCOV physical interval difference (HH/HV)','magma',[0,.5]),
      (axes[1,0],wrapped_phase,wm,'GUNW wrapped phase: Aug 19 → 31 (20 m, rad)','twilight',[-np.pi,np.pi]),
      (axes[1,1],coherence,wm,'GUNW coherence over interval (20 m)','viridis',[0,1]),
      (axes[1,2],1-coherence,wm,'1 − coherence: interval incoherence, NOT change probability','magma',[0,1]),
      (axes[2,0],phase,um,'Unwrapped phase (80 m, valid components only, rad)','coolwarm',phase_limits),
      (axes[2,1],phase_reliable,um,'Same phase, coherence ≥0.3 display filter only','coolwarm',phase_limits),
      (axes[2,2],np.where(uvalid,components,np.nan),um,'Unwrapping components: 0 unreliable / 1 component','tab10',[0,1])]:
        panel(ax,array,m,title,cmap,limits)
    fig.suptitle('Rasuwagadhi: measured before/after GCOV plus GUNW interval observations\nGray = missing/excluded; phase is not corrected displacement; incoherence is not proof of event damage',fontsize=14)
    fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(OUT/'01_gcov_and_gunw_overview.png',dpi=145);plt.close(fig)
    candidates=[]
    for run in (ROOT/'outputs/walkthroughs').glob('nepal_rasuwagadhi_*'):
        if not (run/'steps/03_detection.npz').exists() or not (run/'input.json').exists():continue
        old=json.loads((run/'input.json').read_text())
        if all(old.get(key)==inputs[key] for key in ('before','after','bbox')) and (run/'change_mask.tif').exists():candidates.append(run)
    prior=max(candidates,key=lambda p:p.stat().st_mtime) if candidates else None
    association={}
    if prior:
        records=np.load(prior/'steps/03_detection.npz')
        prior_meta=json.loads((prior/'pair_metadata.json').read_text())
        if prior_meta['crs']!=wm['crs']:raise ValueError('Comparison plot requires matching projected CRS')
        with rasterio.open(prior/'change_mask.tif') as src:
            old_mask=src.read(1);old_valid=old_mask!=255
        fig,axes=plt.subplots(2,3,figsize=(17,11))
        for ax,key,title in [(axes[0,0],'physical_high_binary','Existing step 03: raw HIGH physical threshold'),(axes[0,1],'physical_weak_binary','Existing step 03: raw LOW physical threshold')]:
            layer=np.where(old_valid,records[key].astype(float),np.nan)
            panel(ax,layer,prior_meta,title,'gray',[0,1])
        panel(axes[0,2],np.where(old_valid,old_mask.astype(float),np.nan),prior_meta,'Existing final mask: unchanged','gray',[0,1])
        panel(axes[1,0],1-coherence,wm,'Interval incoherence + existing mask outline (cyan)','magma',[0,1]);contour(axes[1,0],old_mask==1,prior_meta)
        panel(axes[1,1],phase_reliable,um,'Usable phase + existing mask outline (cyan)','coolwarm');contour(axes[1,1],old_mask==1,prior_meta)
        panel(axes[1,2],physical,meta,'GCOV physical score + existing mask outline','magma',[0,.5]);contour(axes[1,2],old_mask==1,prior_meta)
        fig.suptitle('Diagnostic co-location only: no mask fusion or GUNW threshold applied\nGUNW native grids: coherence 20 m, phase 80 m; existing GCOV mask 10 m',fontsize=14)
        fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(OUT/'02_existing_step03_comparison.png',dpi=145);plt.close(fig)
        fig,axes=plt.subplots(1,3,figsize=(17,5.5))
        panel(axes[0],np.where(old_valid,records['physical_score'],np.nan),prior_meta,'Existing step-03 physical score','magma',[0,.5])
        panel(axes[1],1-coherence,wm,'GUNW interval incoherence (20 m)','magma',[0,1])
        panel(axes[2],phase_reliable,um,'Unwrapped phase (80 m, rad; coherence ≥0.3)','coolwarm',phase_limits)
        fig.suptitle('August 19 → 31, 2026: complementary observations, not a fused change mask')
        fig.tight_layout(rect=[0,0,1,.92]);fig.savefig(OUT/'04_summary.png',dpi=140);plt.close(fig)
        # Fractional coverage preserves partial 10 m mask coverage at native 20 m coherence pixels.
        fraction=np.full(coherence.shape,np.nan,np.float32)
        source=np.where(old_valid,(old_mask==1).astype(np.float32),np.nan)
        reproject(source,fraction,src_transform=Affine(*prior_meta['transform']),src_crs=prior_meta['crs'],
                  dst_transform=Affine(*wm['transform']),dst_crs=wm['crs'],src_nodata=np.nan,dst_nodata=np.nan,resampling=Resampling.average)
        common=np.isfinite(fraction)&np.isfinite(coherence)
        def weighted_mean(weight):
            weight=np.where(common,weight,0)
            return float((np.where(common,coherence,0)*weight).sum()/weight.sum()) if weight.sum()>0 else None
        association=dict(mean_coherence_weighted_by_existing_mask_fraction=weighted_mean(fraction),
                         mean_coherence_weighted_by_existing_unchanged_fraction=weighted_mean(1-fraction),
                         interpretation='Descriptive association only, not accuracy or independent event validation; no baseline coherence pair available')
    fig,axes=plt.subplots(1,3,figsize=(17,5))
    panel(axes[0],phase,um,'Unwrapped phase before extra corrections (rad)','coolwarm')
    panel(axes[1],unw['ionospherePhaseScreen'],um,'Supplied ionosphere phase screen (rad)','viridis')
    panel(axes[2],unw['ionospherePhaseScreenUncertainty'],um,'Supplied screen uncertainty (rad)','magma')
    fig.suptitle('Phase quality context: no corrections, ramp removal or displacement conversion applied')
    fig.tight_layout(rect=[0,0,1,.92]);fig.savefig(OUT/'03_phase_correction_context.png',dpi=145);plt.close(fig)
    details=dict(granule=manifest['granule'],file_bytes=Path(manifest['file']).stat().st_size,bbox=bbox,dates=times,
        wrapped_grid=wm,unwrapped_grid=um,coherence20=summary(coherence),coherence80=summary(unw['coherenceMagnitude']),
        valid_unwrapped_component_fraction=float(phase_valid.mean()),phase_display_coherence_threshold=.3,
        phase_above_display_coherence_fraction=float(np.isfinite(phase_reliable).mean()),
        existing_run=str(prior.relative_to(ROOT)) if prior else None,association=association,
        changes_to_pipeline='none',fused_masks_generated=False,
        warnings=['One GUNW represents the two-date interval, not two separate date images',
                  'Low coherence can arise from water, vegetation, geometry and noise; one interval cannot establish coherence loss relative to a pre-event baseline',
                  'Phase retains arbitrary reference and correction effects; no calibrated displacement or event attribution',
                  'Unwrapped connected components with label zero and fill labels are excluded from phase views',
                  '20/80 m GUNW maps must not be treated as independent 10 m observations',
                  'GCOV P05023 and GUNW X05026 are different processing releases; source acquisition times match but products need independent QA'])
    (OUT/'report.json').write_text(json.dumps(details,indent=2)+'\n')
    captions={'01_gcov_and_gunw_overview.png':'Measured GCOV dates and GUNW interval phase/coherence.',
              '02_existing_step03_comparison.png':'Existing physical high/low masks and final mask, compared spatially to GUNW. Cyan is the existing mask outline; no masks were changed.',
              '03_phase_correction_context.png':'Unwrapped phase and supplied ionospheric correction layers; corrections are not applied.'}
    md='# Isolated Rasuwagadhi GUNW review\n\nAugust 19–31, 2026; exact requested granule, 2.3446 GB. Existing pipeline, input configurations and masks are unchanged.\n\n'
    md+='This is one interval product. GCOV panels provide the actual before/after acquisitions; GUNW panels show inter-date phase and coherence. Neither phase nor low coherence is a flood/change probability. A second, pre-event GUNW interval is needed to estimate coherence loss relative to a baseline.\n\n'
    for warning in details['warnings']:md+='- '+warning+'\n'
    md+='\n'
    for name,caption in captions.items():
        if (OUT/name).exists():md+=caption+'\n\n!['+caption+']('+name+')\n\n'
    md+='## Next-step options (not implemented)\n\n1. **Optional corroboration after physical masks (recommended first):** compare/score existing physical candidates using coherence, retaining an explicit unchanged original mask and separate candidate result. Do not declare every low-coherence region changed.\n2. **Optional uncertain-region support:** use coherence to help keep weak physical components connected to reliable seeds, with fixed coverage and nodata rules. May recover continuity but can add vegetation/water noise.\n3. **Optional RF descriptor:** attach aligned coherence plus a validity indicator; requires new fitting and shared rules for missing GUNW. More flexible but harder to interpret.\n4. **Phase evidence:** use only after phase quality, reference and correction handling; unsuitable as a raw threshold/third channel at this stage.\n\nAll future integration must be opt-in, keep the current no-GUNW path identical, and record pair dates, QA, resampling and source release. No integration flag has been implemented pending user approval.\n\n[ASF GUNW guide]('+SOURCE+') · [Numeric report](report.json)\n'
    (OUT/'README.md').write_text(md)
    body='<h1>Isolated Rasuwagadhi GUNW review</h1><p>August 19–31, 2026. Pipeline unchanged; no fused mask generated.</p><p>'+html.escape(' '.join(details['warnings']))+'</p>'
    for name,caption in captions.items():
        if (OUT/name).exists():body+='<h2>'+html.escape(caption)+'</h2><a href="'+name+'"><img src="'+name+'" style="max-width:100%"></a>'
    body+='<h2>Numeric diagnostics</h2><pre>'+html.escape(json.dumps(details,indent=2))+'</pre><p><a href="README.md">Interpretation and integration options</a></p>'
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>GUNW interval review</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto}pre{white-space:pre-wrap}</style>'+body)
    print(json.dumps(details,indent=2));print('REPORT',OUT/'index.html')


if __name__=='__main__':main()
