#!/usr/bin/env python3
"""A browsable catalog, retaining existing experiments and their provenance."""
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'

def main():
    catalog=OUT/'results';catalog.mkdir(exist_ok=True)
    rows=[]
    for run in sorted((OUT/'runs').iterdir()):
        if not run.is_dir():continue
        dst=catalog/run.name;dst.mkdir(exist_ok=True)
        if not (run/'study.json').exists():
            (dst/'README.md').write_text(f'# {run.name}\n\nRun incomplete. Inspect ../../runs/{run.name}/console.log. No result is being presented as successful.\n');continue
        study=json.loads((run/'study.json').read_text())
        for name in ['overview.png','before.png','after.png','overlay.png','mask.png','binary_mask_grayscale.png','valid_coverage.png','pseudo_labels.png','pseudo_labels_review.png']:
            if (run/name).exists():shutil.copy2(run/name,dst/name)
        import re
        from datetime import datetime
        def date(granule):
            return datetime.strptime(re.search(r'\d{8}T\d{6}',granule).group(),'%Y%m%dT%H%M%S').strftime('%Y-%m-%d %H:%M:%S UTC')
        text=f"# {run.name.replace('_',' ')}\n\nBefore: **{date(study['before'])}**. After: **{date(study['after'])}**.\n\n"
        text+="Pair-specific UCDFormer adaptation, physical-change gating and a pseudo-label-trained random forest produce the final mask. The score is not a calibrated probability; accuracy has not been independently measured.\n"

        eda=OUT/'eda'/run.name/'eda.json'
        if eda.exists():
            context=json.loads(eda.read_text()).get('event_context',{})
            if context.get('note'):text+=f"\nEvent context: {context['note']} [Source]({context['source']}).\n"
        text+=f'\n[Acquisition timeline and per-polarization EDA](../../eda/{run.name}/README.md).\n'
        text+='\n## Images\n\n'
        descriptions={
            'overview.png':'Overview: before, after, continuous feature score and final change overlay.',
            'before.png':'Before acquisition: HH / HV / log polarization-ratio false-color SAR composite.',
            'after.png':'After acquisition: identical channel scaling, so colors can be compared with before.',
            'overlay.png':'Final detected change shown in red over the after acquisition.',
            'mask.png':'Final binary change overlay: red means detected change; the remaining pixels are transparent.',
            'binary_mask_grayscale.png':'Final binary mask: white changed, black unchanged, gray unsupported.',
            'valid_coverage.png':'Model coverage: white scored, black excluded because valid context was unavailable.',
            'pseudo_labels.png':'Automatic seed labels: red changed, blue unchanged, yellow uncertain; not the final mask or ground truth.',
            'pseudo_labels_review.png':'Pseudo-label diagnostics: confident changed/unchanged seeds, uncertain pixels, physical-change support and final result. Seeds are automatically generated, not ground truth.'}
        for name,description in descriptions.items():
            if (dst/name).exists():text+=f'{description}\n\n![{description}]({name})\n\n'

        text+=f"\nBefore: `{study['before']}`\n\nAfter: `{study['after']}`\n\nScored area: {study['valid_area_km2']:.2f} km²; detected change: {study['changed_area_km2']:.3f} km². These are areas, not accuracy metrics.\n\n[Full run, geospatial files, checkpoint and diagnostics](../../runs/{run.name}/README.md).\n"
        if run.name=='etna':text+='\n[Your earlier preferred conservative mask](../../../old/outputs/etna/refinement/conservative_candidate/README.md) is preserved separately; it uses the earlier model run plus a physical-change gate.\n'
        if run.name=='mozambique':text+='\nThis model run covers the local training AOI. [Regional EDA](../../eda/mozambique_regional/README.md) covers the larger flood context; this local mask does not establish the full flood extent.\n'
        if run.name=='nepal_quad':text+='\nThe input HDF5 has HH/HV/VH/VV, but this adapter uses HH/HV and their log ratio. All measured polarizations remain available in the EDA.\n'
        text+='\n## Method comparison\n\n| Variant | Detected km² | Scored km² |\n|---|---:|---:|\n'
        for label,folder in [('Trained translation + physical gate + RF',run),('Physical threshold baseline; no neural model',run/'baseline'),('Frozen VGG + physical gate + RF; no translation',run/'no_translation')]:
            report=folder/'study.json'
            if report.exists():
                d=json.loads(report.read_text());text+=f"| {label} | {d['changed_area_km2']:.3f} | {d['valid_area_km2']:.2f} |\n"
        text+='\nAreas are algorithm outputs, not accuracy scores; the baseline can have different valid support. The conservative settings were reused from Etna for this first pass and may omit diffuse or low-contrast change. Full disaster extent and a benefit from neural translation have not been established.\n\n'
        for folder,caption in [('baseline','Physical threshold baseline: no neural model is used.'),('no_translation','Frozen VGG feature comparison with physical gating and RF; the trained translator is not applied.')]:
            if (run/folder/'overlay.png').exists():text+=f'{caption}\n\n![{caption}](../../runs/{run.name}/{folder}/overlay.png)\n\n'
        (dst/'README.md').write_text(text)
        rows.append(f"| [{run.name}]({run.name}/README.md) | {study['changed_area_km2']:.3f} | {study['valid_area_km2']:.2f} |")
    (catalog/'README.md').write_text('# Location results\n\nOpen a location, then `overview.png`, `overlay.png` or `binary_mask_grayscale.png`. Images here retain native projected proportions. Transparent red `mask.png` is intended for overlays.\n\n| Location | Detected change km² | Scored km² |\n|---|---:|---:|\n'+'\n'.join(rows)+'\n\nEach is a separate pair-specific UCDFormer adaptation, followed by physical gating and pseudo-label random-forest classification. No independent accuracy estimate is available. [Export checks](validation.json) verify geometry, mask values and image links; they do not measure detection accuracy.\n')
    from PIL import Image,ImageOps,ImageDraw
    previews=sorted(catalog.glob('*/overlay.png'))
    if previews:
        cols=3;size=360;rows_count=(len(previews)+cols-1)//cols
        sheet=Image.new('RGB',(cols*size,rows_count*(size+38)),'white')
        draw=ImageDraw.Draw(sheet)
        for i,path in enumerate(previews):
            x=(i%cols)*size;y=(i//cols)*(size+38)
            with Image.open(path) as image:
                background=Image.new('RGBA',image.size,'#eeeeee')
                background.alpha_composite(image.convert('RGBA'))
                image=ImageOps.contain(background.convert('RGB'),(size,size))
                sheet.paste(image,(x+(size-image.width)//2,y+(size-image.height)//2))
            draw.text((x+8,y+size+8),path.parent.name,fill='black')
        sheet.save(catalog/'all_locations.png')
        with (catalog/'README.md').open('a') as stream:
            stream.write('\nRed marks the final detected changes; light gray areas are unsupported. Open individual location READMEs for full resolution and acquisition dates.\n\n![Final change overlays for completed locations](all_locations.png)\n')
    (OUT/'README.md').write_text('# Output index\n\n- [Current location results](results/README.md): start here; readable PNGs and short descriptions.\n- [All run artifacts](runs/): checkpoints, logs, scientific GeoTIFFs, WGS84 app overlays and diagnostic comparisons.\n- [Data exploration](eda/README.md): polarization changes, distributions, acquisition dates and regional context.\n- [Original Etna](../old/outputs/etna/): preserved experiments, including your preferred `refinement/conservative_candidate/mask.png`.\n- [Earlier Etna v2](../old/outputs/etna_v2/README.md): preserved filtered-input experiment; superseded coverage behavior.\n- `jobs/`: download and EDA worker logs.\n\nPNG images are SAR composites, not optical photographs. Legacy and current WGS84 exports have been refreshed to retain native aspect, with geographic bounds and an explicit display transform in study.json. Use native PNGs for visual inspection.\n')
if __name__=='__main__':
    from refresh_run_reviews import main as refresh
    refresh()
    main()
    from embed_output_images import main as embed
    embed()
    from validate_outputs import main as validate
    validate()
