#!/usr/bin/env python3
"""Embed local PNGs with captions in each artifact directory's README."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CAPTIONS={
 'all_locations':'Final detected-change overlays for all completed locations; red is flagged change, light gray is unsupported.',
 'aoi_correction':'Spain AOI correction: comparison of the earlier search box and the corrected fire-area box against mapped burn perimeters.',
 'mapped_burn_comparison':'Corrected Spain SAR changes compared with independently mapped burn perimeters; the perimeter is a contextual reference, not a pixel-perfect SAR label.',
 'full_granule_context':'Mozambique regional and local boxes within the available full-granule footprint; this explains the spatial crop and coverage.',
 'threshold_comparison':'Etna threshold ablation: original RF mask, confident seeds, adaptive feature/physical thresholds, and their intersections. The preferred conservative candidate intersects the RF result with filtered physical-change support.',
 'training_history':'Translation training and held-out objective over optimization steps; this is not a detection-accuracy curve.',
 'overview':'Both acquisitions, continuous change score and final detected-change overlay.',
 'before':'Before acquisition: shared-scale HH / HV / log-polarization-ratio SAR composite.',
 'after':'After acquisition: the same feature scaling as before for visual comparison.',
 'mask':'Final binary change overlay: red marks detected change; remaining pixels are transparent. Consult valid coverage to distinguish unchanged from unsupported.',
 'overlay':'Final detected-change mask in red over the after-acquisition composite.',
 'binary_mask_grayscale':'Final binary result: white changed, black unchanged, gray unsupported.',
 'valid_coverage':'Model coverage: white scored, black unsupported.',
 'pseudo_labels':'Automatically generated seed labels: red changed, blue unchanged, yellow uncertain. These are not ground-truth labels or the final mask.',
 'pseudo_labels_review':'Diagnostic comparison of automatic seeds, physical-change evidence, connected support and final classification.',
 'result_comparison':'Comparison of Etna experiments and the earlier visually preferred conservative mask; identical scene, different pipelines.',
 'timeline':'Acquisition dates compared with the documented event interval; this checks chronology, not detection accuracy.',
 'polarization_changes':'Before/after and signed change for each available measured polarization, with shared display scaling.',
 'distributions':'Per-polarization intensity distributions at both timestamps; differences can have multiple physical causes.',
 'speckle_sensitivity':'Sensitivity to a 3×3 linear-power speckle filter before difference calculation.',
 'non_db_changes':'Non-decibel change views: linear-power change and bounded normalized change, preserving increase/decrease information.',
}
def main():
 count=0
 for directory in sorted({p.parent for p in (ROOT/'outputs').rglob('*.png') if '.matplotlib' not in p.parts}):
  path=directory/'README.md'
  text=path.read_text() if path.exists() else '# '+directory.name+'\n'
  additions=[]
  for image in sorted(directory.glob('*.png')):
   if f']({image.name})' in text:continue
   key=image.stem.removesuffix('_wgs84')
   description=CAPTIONS.get(key,'Diagnostic visualization: '+key.replace('_',' ')+'. See the associated metadata for the method and thresholds.')
   if image.stem.endswith('_wgs84'):description+=' Geographic WGS84 export of the same result; use the bounds and display transform in study.json for map placement.'
   additions.append(f'**{image.name}** — {description}\n\n![{description}]({image.name})\n')
  if additions:
   path.write_text(text+'\n## Image gallery\n\n'+'\n'.join(additions));count+=1
 print('Embedded images in',count,'READMEs')
if __name__=='__main__':main()
