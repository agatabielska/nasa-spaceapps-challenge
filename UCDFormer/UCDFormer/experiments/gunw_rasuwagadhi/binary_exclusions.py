"""Binary eligibility views from the actual masked GUNW output rasters."""
import os,sys,json
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/nisar-gunw-binary')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'.deps'),str(ROOT)]
import numpy as np
import rasterio
from PIL import Image
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
OUT=ROOT/'outputs/experiments/gunw_rasuwagadhi/gcov_mask_review'


def main():
    layers=[];report={}
    specs=[('coherence_20m','gunw_incoherence_masked_20m.tif','GUNW coherence / incoherence — 20 m',
            'GCOV holes + native GUNW invalid/nonfinite samples'),
           ('phase_80m','gunw_phase_masked_80m.tif','GUNW phase as currently displayed — 80 m',
            'GCOV holes + native phase/component validity + display coherence ≥ 0.3')]
    for key,filename,title,rule in specs:
        with rasterio.open(OUT/filename) as src:
            values=src.read(1)
            valid=(src.read_masks(1)>0)&np.isfinite(values)
            profile=src.profile.copy();bounds=src.bounds
        png=OUT/(key+'_binary_valid.png')
        Image.fromarray(valid.astype(np.uint8)*255).save(png)
        with Image.open(png) as image:
            assert set(np.unique(np.asarray(image)))<={0,255}
        profile.update(dtype='uint8',nodata=None)
        with rasterio.open(OUT/(key+'_binary_valid.tif'),'w',**profile) as dst:dst.write(valid.astype(np.uint8),1)
        report[key]=dict(included_pixels=int(valid.sum()),excluded_pixels=int((~valid).sum()),
                         excluded_percent=float((~valid).mean()*100),shape=list(valid.shape),
                         source=filename,rule=rule,legend={'0':'excluded','1':'included'})
        layers.append((valid,[bounds.left/1000,bounds.right/1000,bounds.bottom/1000,bounds.top/1000],title,rule,key))
    fig,axes=plt.subplots(1,2,figsize=(14,7))
    cmap=ListedColormap(['black','white']);norm=BoundaryNorm([-.5,.5,1.5],2)
    for ax,(valid,bounds,title,rule,key) in zip(axes,layers):
        ax.imshow(valid.astype(np.uint8),extent=bounds,origin='upper',interpolation='nearest',cmap=cmap,norm=norm)
        ax.set_title(title+'\n'+f"{report[key]['excluded_percent']:.2f}% excluded",fontsize=12)
        ax.set_xlabel('UTM easting (km)');ax.set_ylabel('UTM northing (km)')
        ax.text(.5,-.15,rule,transform=ax.transAxes,ha='center',fontsize=9,wrap=True)
    fig.suptitle('GUNW eligibility only: WHITE = INCLUDED | BLACK = EXCLUDED\nThis does not show detected change',fontsize=15)
    fig.legend(handles=[Patch(facecolor='white',edgecolor='black',label='Included in this GUNW view'),
                        Patch(facecolor='black',edgecolor='black',label='Excluded from this GUNW view')],loc='lower center',ncol=2)
    fig.tight_layout(rect=[0,.09,1,.91]);fig.savefig(OUT/'03_binary_exclusions.png',dpi=160);plt.close(fig)
    (OUT/'binary_exclusions.json').write_text(json.dumps(report,indent=2)+'\n')
    paragraph='\n## Binary eligibility check\n\nWhite = included, black = excluded. These maps show eligibility only, not detected change. The phase map reproduces the current displayed/exported phase view, including the extra coherence ≥0.3 display filter; low-coherence exclusion there is not necessarily missing GCOV data.\n\n![Binary included/excluded GUNW masks](03_binary_exclusions.png)\n\n[Native 20 m binary image](coherence_20m_binary_valid.png) · [Native 80 m binary image](phase_80m_binary_valid.png) · [Counts and rules](binary_exclusions.json)\n'
    readme=OUT/'README.md';text=readme.read_text()
    if '## Binary eligibility check' in text:text=text[:text.index('## Binary eligibility check')]
    readme.write_text(text+paragraph)
    page=OUT/'index.html';text=page.read_text();marker='<section id="binary-exclusions">'
    if marker in text:text=text[:text.index(marker)]
    page.write_text(text+marker+'<h2>Binary eligibility: white included, black excluded</h2><p>Eligibility only, not change. The 80 m phase view also excludes coherence below the existing 0.3 display threshold.</p><img src="03_binary_exclusions.png"><p><a href="coherence_20m_binary_valid.png">Native binary 20 m image</a> | <a href="phase_80m_binary_valid.png">Native binary 80 m image</a></p></section>')
    print(json.dumps(report,indent=2));print(OUT/'03_binary_exclusions.png')


if __name__=='__main__':main()
