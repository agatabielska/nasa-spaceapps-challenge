"""Review-only: exclude GCOV nodata from every GUNW field and derived value.

No GUNW thresholding, RF changes or production pipeline integration is executed.
"""
import sys,json,html,os
os.environ.setdefault("MPLCONFIGDIR","/tmp/nisar-gunw-mask-review")
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject,Resampling
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap
from nisar.data import align_pair
from experiments.gunw_rasuwagadhi.visualize import OUT as ORIGINAL,panel,extent,summary
OUT=ORIGINAL/'gcov_mask_review'


def project_gcov_valid(valid,source_meta,target_meta):
    """Require fully valid GCOV coverage of each coarse GUNW pixel footprint.

    Zero padding participates in area averaging so outside coverage is invalid,
    not silently dropped from the denominator. Invalid pixels are never nodata
    for this reprojection: their zero values must count against coverage.
    """
    src=Affine(*source_meta['transform']);dst=Affine(*target_meta['transform'])
    ratio=max(abs(dst.a),abs(dst.e))/min(abs(src.a),abs(src.e))
    pad=int(np.ceil(ratio))+2
    padded=np.pad(valid.astype(np.float32),pad,constant_values=0)
    fraction=np.zeros(target_meta['shape'],np.float32)
    reproject(padded,fraction,src_transform=src*Affine.translation(-pad,-pad),src_crs=source_meta['crs'],
              dst_transform=dst,dst_crs=target_meta['crs'],resampling=Resampling.average,
              src_nodata=None,dst_nodata=None)
    return fraction>=1-1e-6,fraction


def apply_gcov_valid(arrays,gunw_valid,gcov_projected):
    valid=gunw_valid&gcov_projected
    return {key:np.where(valid,array,np.nan) for key,array in arrays.items()},valid


def write_grid(path,values,meta,nodata):
    with rasterio.open(path,'w',driver='GTiff',width=values.shape[1],height=values.shape[0],count=1,
                       dtype=values.dtype,crs=meta['crs'],transform=Affine(*meta['transform']),nodata=nodata,compress='deflate') as dst:
        dst.write(values,1)


def holes_panel(ax,valid,meta,title):
    cmap=ListedColormap(['#ffffff','#d62f35'])
    ax.imshow((~valid).astype(np.uint8),extent=extent(meta),cmap=cmap,vmin=0,vmax=1,interpolation='nearest')
    ax.set_title(title+'\nred = excluded; white = eligible',fontsize=10)
    ax.set_xlabel('UTM easting (km)');ax.set_ylabel('UTM northing (km)')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original=json.loads((ORIGINAL/'report.json').read_text())
    inputs=json.loads((ROOT/'configs/nepal_rasuwagadhi_run.json').read_text())
    if inputs['bbox']!=original['bbox']:raise ValueError('AOI changed: regenerate isolated GUNW visualization first')
    _,_,gcov_valid,gcov_meta=align_pair(inputs['before'],inputs['after'],inputs['bbox'])
    wm=original['wrapped_grid'];um=original['unwrapped_grid']
    wprojected,wfraction=project_gcov_valid(gcov_valid,gcov_meta,wm)
    uprojected,ufraction=project_gcov_valid(gcov_valid,gcov_meta,um)
    with np.load(ORIGINAL/'wrappedInterferogram_crop.npz') as data:
        wvalid=data['valid'].copy();wrapped={key:data[key].copy() for key in data.files if key not in ('mask','valid')}
    with np.load(ORIGINAL/'unwrappedInterferogram_crop.npz') as data:
        uvalid=data['valid'].copy();unwrapped={key:data[key].copy() for key in data.files if key not in ('mask','valid')}
    wmasked,wcombined=apply_gcov_valid(wrapped,wvalid,wprojected)
    umasked,ucombined=apply_gcov_valid(unwrapped,uvalid,uprojected)
    coherence_before=wrapped['coherenceMagnitude']
    coherence_after=wmasked['coherenceMagnitude']
    coherence_before=np.where((coherence_before>=0)&(coherence_before<=1),coherence_before,np.nan)
    coherence_after=np.where((coherence_after>=0)&(coherence_after<=1),coherence_after,np.nan)
    incoherence=1-coherence_after # NaN holes stay NaN; they must never turn into score=1.
    def phase_view(arrays):
        cc=arrays['connectedComponents'];coh=arrays['coherenceMagnitude'];phase=arrays['unwrappedPhase']
        return np.where((cc>0)&(cc!=65535)&(coh>=.3),phase,np.nan)
    before_phase=phase_view(unwrapped);after_phase=phase_view(umasked)
    phase_limits=np.nanpercentile(before_phase,[2,98])
    assert np.isnan(coherence_after[~wprojected]).all()
    assert np.isnan(incoherence[~wprojected]).all()
    assert np.isnan(after_phase[~uprojected]).all()
    fig,axes=plt.subplots(2,3,figsize=(17,11))
    holes_panel(axes[0,0],gcov_valid,gcov_meta,'GCOV common HH/HV validity at both dates (10 m)')
    panel(axes[0,1],1-coherence_before,wm,'Previous GUNW incoherence view','magma',[0,1])
    panel(axes[0,2],incoherence,wm,'GUNW incoherence with GCOV holes excluded (20 m)','magma',[0,1])
    holes_panel(axes[1,0],uprojected,um,'GCOV validity projected conservatively onto 80 m GUNW')
    panel(axes[1,1],before_phase,um,'Previous unwrapped-phase view (rad, coherence ≥0.3)','coolwarm',phase_limits)
    panel(axes[1,2],after_phase,um,'Phase with GCOV holes excluded (80 m)','coolwarm',phase_limits)
    fig.suptitle('Review GCOV nodata exclusion before any GUNW thresholding or mask fusion\nGray in GUNW panels = excluded, never changed/unchanged; scales are identical before and after masking',fontsize=14)
    fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(OUT/'01_holes_review.png',dpi=145);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(17,5.5))
    holes_panel(axes[0],gcov_valid,gcov_meta,'GCOV holes to exclude (10 m)')
    panel(axes[1],1-coherence_before,wm,'Before exclusion: interval incoherence','magma',[0,1])
    panel(axes[2],incoherence,wm,'After exclusion: gray is not considered','magma',[0,1])
    fig.suptitle('GCOV holes excluded from GUNW — no threshold or fused change mask has been produced')
    fig.tight_layout(rect=[0,0,1,.92]);fig.savefig(OUT/'02_holes_summary.png',dpi=145);plt.close(fig)
    for name,arrays,valid,projected,fraction in [
        ('wrapped_masked',wmasked,wcombined,wprojected,wfraction),
        ('unwrapped_masked',umasked,ucombined,uprojected,ufraction)]:
        np.savez_compressed(OUT/(name+'.npz'),**arrays,combined_valid=valid,gcov_valid=projected,gcov_valid_fraction=fraction)
    write_grid(OUT/'gcov_common_valid_10m.tif',gcov_valid.astype(np.uint8),gcov_meta,None)
    write_grid(OUT/'gcov_valid_on_gunw_20m.tif',wprojected.astype(np.uint8),wm,None)
    write_grid(OUT/'gcov_valid_on_gunw_80m.tif',uprojected.astype(np.uint8),um,None)
    write_grid(OUT/'gunw_coherence_masked_20m.tif',coherence_after.astype(np.float32),wm,np.nan)
    write_grid(OUT/'gunw_incoherence_masked_20m.tif',incoherence.astype(np.float32),wm,np.nan)
    write_grid(OUT/'gunw_phase_masked_80m.tif',after_phase.astype(np.float32),um,np.nan)
    report=dict(bbox=inputs['bbox'],before=inputs['before'],after=inputs['after'],
      gcov_mask_definition='Valid only where BOTH HH/HV channels at BOTH dates pass GCOV quality, fill, positive-power and finite checks; no morphology/filter/guard expansions used',
      projection_policy='Area-weighted GCOV validity with zero-padded footprint; a GUNW cell is eligible only at 100% GCOV valid coverage (tolerance 1e-6)',
      mixed_pixel_policy='Conservative: exclude any 20/80 m GUNW footprint overlapping a GCOV hole. Coarse boundaries can therefore expand slightly.',
      derived_policy='Apply combined GCOV/GUNW validity before phase, 1-coherence, statistics or future threshold fitting. NaNs never become zero coherence.',
      gcov_shape=list(gcov_valid.shape),gcov_nodata_pixels=int((~gcov_valid).sum()),gcov_nodata_fraction=float((~gcov_valid).mean()),
      gunw20_excluded_by_gcov=int((wvalid&~wprojected).sum()),gunw20_total=int(wvalid.size),
      gunw80_excluded_by_gcov=int((uvalid&~uprojected).sum()),gunw80_total=int(uvalid.size),
      coherence_before=summary(coherence_before),coherence_after=summary(coherence_after),
      pipeline_changed=False,gunw_thresholding_executed=False,rf_integration_executed=False,
      next_step='User review of exclusion mask; then optional pre-RF physical-candidate support, as requested')
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    text='# GCOV holes excluded from GUNW — review before integration\n\n'
    text+='Red in the source mask marks GCOV nodata in either HH/HV channel at either date. Gray in the corrected GUNW images is excluded, not change. Every GUNW field is masked before derived calculations; validity is intersected with GUNW native quality flags too.\n\n'
    text+='At 20 m and 80 m, a cell is excluded if any part of its footprint overlaps a GCOV hole. This conservative rule prevents nearest-neighbor resampling from overlooking small holes. It can make exclusions slightly larger on the coarser grids. No extra closing, dilation, or inference-context guard was applied to the source GCOV mask.\n\n'
    text+='The previous bright areas were low-coherence/incoherence observations, not a generated GUNW change mask. No GUNW thresholding, fused mask or RF integration has been run. The requested next integration point is before RF; implementation is pending confirmation that this exclusion is correct. Original reports and production pipeline remain unchanged.\n\n'
    text+='![GCOV holes and before/after exclusion](01_holes_review.png)\n\n[Numeric report](report.json)\n'
    (OUT/'README.md').write_text(text)
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>GCOV nodata exclusion review</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto}img{max-width:100%}pre{white-space:pre-wrap}</style><h1>GCOV holes excluded from GUNW</h1><p>Red = excluded GCOV observations. Gray in GUNW = excluded, never classified. Conservative full-footprint validity on 20/80 m grids.</p><img src="01_holes_review.png"><p>Production pipeline unchanged. No threshold/fusion/RF integration executed; waiting for visual confirmation.</p><pre>'+html.escape(json.dumps(report,indent=2))+'</pre>')
    print(json.dumps(report,indent=2));print('REVIEW',OUT/'index.html')


if __name__=='__main__':main()
