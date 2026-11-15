"""Separate GCOV validity, phase unwrapping support and display cutoff."""
import sys,os,json
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-gunw-exclusion-reasons')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from experiments.gunw_rasuwagadhi.visualize import extent
OUT=ROOT/'outputs/experiments/gunw_rasuwagadhi/gcov_mask_review'


def main():
    metadata=json.loads((OUT.parent/'report.json').read_text())
    with np.load(OUT/'wrapped_masked.npz') as data:
        valid20=data['combined_valid']&np.isfinite(data['coherenceMagnitude'])
    with np.load(OUT/'unwrapped_masked.npz') as data:
        gcov=data['gcov_valid'].copy();combined=data['combined_valid'].copy()
        cc=data['connectedComponents'];coh=data['coherenceMagnitude'];phase=data['unwrappedPhase']
        coherence_ok=combined&np.isfinite(coh)&(coh>=0)&(coh<=1)
        phase_ok=combined&np.isfinite(phase)&np.isfinite(cc)&(cc>0)&(cc!=65535)
        displayed=phase_ok&(coh>=.3)
        reasons=dict(gcov_holes_or_partial_footprint=~gcov,
                     additional_phase_component_exclusion=combined&~phase_ok,
                     additional_display_coherence_exclusion=phase_ok&~displayed)
    report={key:dict(pixels=int(value.sum()),percent=float(value.mean()*100)) for key,value in reasons.items()}
    report['coherence_rule']='Only GCOV/native validity and finite [0,1] coherence. No minimum coherence and no phase-component requirement.'
    report['phase_rule']='Unwrapped phase needs its own component validity. The extra 0.3 threshold was display-only.'
    report['pipeline_effect']='None: optional GUNW integration has not been implemented. Planned pre-RF coherence support must use coherence validity, not phase validity.'
    report['coherence_80m_included_percent']=float(coherence_ok.mean()*100)
    fig,axes=plt.subplots(2,2,figsize=(13,13))
    cmap=ListedColormap(['black','white']);norm=BoundaryNorm([-.5,.5,1.5],2)
    for ax,valid,meta,title in [
       (axes[0,0],valid20,metadata['wrapped_grid'],'A. Coherence 20 m: approved validity mask'),
       (axes[0,1],coherence_ok,metadata['unwrapped_grid'],'B. Coherence 80 m: no phase-quality restrictions'),
       (axes[1,0],phase_ok,metadata['unwrapped_grid'],'C. Unwrapped phase 80 m: additionally require valid component'),
       (axes[1,1],displayed,metadata['unwrapped_grid'],'D. Previous phase display: additionally require coherence ≥0.3')]:
        ax.imshow(valid,extent=extent(meta),interpolation='nearest',origin='upper',cmap=cmap,norm=norm)
        ax.set_title(title+'\n'+f'{100*(~valid).mean():.2f}% excluded',fontsize=11)
        ax.set_xlabel('UTM easting (km)');ax.set_ylabel('UTM northing (km)')
    fig.suptitle('WHITE = included | BLACK = excluded — these are eligibility maps, not change masks\nCoherence support uses A (20 m). Phase-specific exclusions in C/D must not remove coherence evidence.',fontsize=13)
    fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(OUT/'04_exclusion_reasons.png',dpi=145);plt.close(fig)
    np.savez_compressed(OUT/'exclusion_reasons.npz',coherence_valid20=valid20,coherence_valid80=coherence_ok,
                        phase_component_valid80=phase_ok,phase_display_valid80=displayed,**reasons)
    (OUT/'exclusion_reasons.json').write_text(json.dumps(report,indent=2)+'\n')
    text='\n## Why phase excludes more than coherence\n\nThe previous right-hand map included unwrapped-phase connected-component rejection and an extra coherence ≥0.3 display cutoff. These are not GCOV nodata. Phase support and coherence support must remain separate. For optional coherence-based integration, keep finite valid coherence even when it is low or when unwrapped phase is unsupported. Do not restore unreliable phase values or call them displacement.\n\n![Separate coherence and phase exclusion rules](04_exclusion_reasons.png)\n\n[Counts by exclusion reason](exclusion_reasons.json)\n'
    path=OUT/'README.md';old=path.read_text();marker='## Why phase excludes more than coherence'
    if marker in old:old=old[:old.index(marker)]
    path.write_text(old+text)
    path=OUT/'index.html';old=path.read_text();marker='<section id="phase-exclusion-reasons">'
    if marker in old:old=old[:old.index(marker)]
    path.write_text(old+marker+'<h2>Why phase excludes more than coherence</h2><p>The previous right-hand map included phase-component validity and a display-only coherence cutoff. They are not GCOV holes. Coherence support must not inherit these phase-specific restrictions. Integration has not been implemented.</p><img src="04_exclusion_reasons.png"></section>')
    # Actual derived coherence remains available independently of phase quality.
    assert np.all(phase_ok[combined&~phase_ok]==False)
    assert np.all(coherence_ok[combined&np.isfinite(coh)&(coh<.3)])
    assert np.all(~coherence_ok[~gcov])
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
