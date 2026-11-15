"""Offline visual report for opt-in pipeline traces; no model execution here."""
import html
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

DESCRIPTIONS={
 '00_physical_baseline': 'Independent physical baseline: absolute co/cross-pol dB changes divided by their valid-area 75th-percentile scales (floor 0.1 dB), averaged across polarizations, then a global Otsu threshold. No VGG, FCM or random forest is used in this baseline.',
 '01_preprocessing': 'Aligned frequency-A co/cross-pol gamma-0 power → masked linear-power mean → 10 log10(power) → co-pol dB, cross-pol dB, their dB difference → shared per-channel 1st/99th percentile scaling → NISAR channel z-scores. Statistics use both dates on training support only. Alignment is grid reprojection when needed, not independently verified subpixel registration.',
 '02a_training_targets': 'First fully valid training patch at initialization. Initial feature difference is min-max scaled to a mixing weight. The style target mixes normalized post and pre as (1−weight) × post + weight × pre; content features come from pre. These are fixed cached targets, not predictions of ground truth.',
 '02_vgg_example_patch': 'One inference patch only, at the saved pixel origin. Inputs are NISAR-normalized. VGG block means and first four activation channels are illustrative summaries, not complete feature tensors. Translated output is in normalized network coordinates, not measured backscatter. VGG weights remain frozen. Score inputs additionally show the first three upsampled activation channels after per-date, per-channel minimum/95th-percentile saturation. Their L2 difference across all feature channels yields the patch score; these activation percentiles are separate from input standardization.',
 '03_detection': 'Full-area blended VGG scores, FCM memberships, adaptive thresholds, seed agreement, RF votes, physical support gates and component removal. comparison_strict_* shows the older Gaussian rule score > 2 × masked Gaussian local mean, with high/low FCM agreement. It is a diagnostic comparison, not an additional gate in the refined detector. Refined thresholds use local median + k × 1.4826 × local residual MAD proxy, bounded below by the configured floor. FCM memberships and RF votes are not calibrated probabilities. Raw FCM class 2 is only the highest relative score cluster. fcm_spatially_supported applies membership, margin and neighborhood agreement before physical seed selection. Physical high/weak masks are closed then component-filtered. final_closing_added marks inferred connections inside supported regions; these additions are not certain training seeds and need not pass the RF vote threshold. Gray nodata is never filled.'
}

def bounds(values):
    finite=np.asarray(values)[np.isfinite(values)]
    if not finite.size:return 0.,1.
    lo,hi=np.percentile(finite,[1,99])
    return float(lo),float(hi if hi>lo else lo+1)


def build_report(out):
    out=Path(out);steps=out/'steps';steps.mkdir(parents=True,exist_ok=True)
    metadata_path=out/'pair_metadata.json'
    feature_labels=json.loads(metadata_path.read_text()).get('feature_names',['co-pol','cross-pol','co−cross']) if metadata_path.exists() else ['co-pol','cross-pol','co−cross']
    sections=[];manifest=[]
    for source in sorted(steps.glob('0*.npz')):
        cards=[]
        with np.load(source) as data:
            for key in data.files:
                values=data[key]
                if values.ndim not in (2,3) and key not in ('rf_feature_importance','otsu_threshold'):continue
                # Scalar invalid pixels must remain visibly excluded, not unchanged.
                support_key=next((name for name in ('model_support','filtered_valid','patch_valid') if name in data),None)
                support=data[support_key] if support_key is not None else None
                if key.startswith('aligned_raw') and 'raw_valid' in data:support=data['raw_valid']
                array=values.astype(float).copy()
                if support is not None and array.shape[-2:]==support.shape and key not in ('model_support','raw_valid','filtered_valid','standardization_fit_support','input_valid','guard_safe','overlap_weight_sum','patch_valid'):
                    array[...,~support.astype(bool)]=np.nan
                filename=f'{source.stem}_{key}.png'
                fig=None
                if array.ndim==1:
                    fig,ax=plt.subplots(figsize=(8,3));ax.bar(np.arange(len(array)),array)
                    ax.set(title=key,xlabel='Feature index (ordered names in diagnostics)' if key=='rf_feature_importance' else 'Index',ylabel='Value')
                elif key.endswith('fcm_center_history'):
                    fig,ax=plt.subplots(figsize=(7,3))
                    ax.plot(array);ax.set(xlabel='Iteration (0 = initialization)',ylabel='Center value',title=key)
                    ax.legend(['center trajectory 1','center trajectory 2','center trajectory 3'])
                else:
                    layers=array if array.ndim==3 else array[None]
                    fig,axes=plt.subplots(1,len(layers),figsize=(5*len(layers),4),squeeze=False)
                    # Match before/after scales for each channel; keep exact numeric arrays in NPZ.
                    partner=key[:-4]+'_post' if key.endswith('_pre') else key[:-5]+'_pre' if key.endswith('_post') else None
                    for channel,(ax,layer) in enumerate(zip(axes[0],layers)):
                        categorical=values.dtype.kind=='b' or any(word in key for word in ('clusters','seed_labels','pseudo_labels'))
                        sample=layer
                        if partner in data and data[partner].shape==values.shape:
                            other=data[partner][channel] if values.ndim==3 else data[partner]
                            if support is not None and other.shape==support.shape:other=np.where(support,other,np.nan)
                            sample=np.concatenate([layer.ravel(),other.ravel()])
                        lo,hi=bounds(sample)
                        if values.dtype.kind=='b' or 'membership' in key or key=='rf_votes':lo,hi=0,1
                        elif categorical:lo,hi=(-1,2)
                        cmap=plt.get_cmap('viridis' if not categorical else 'tab10').copy();cmap.set_bad('#dddddd')
                        image=ax.imshow(layer,cmap=cmap,vmin=lo,vmax=hi,interpolation='nearest')
                        names=feature_labels if len(layers)==3 and 'first_channels' not in key else ['co-pol','cross-pol'] if len(layers)==2 else None
                        ax.set_title(key+(f' / {names[channel]}' if names else f' / channel {channel}' if len(layers)>1 else ''),fontsize=9)
                        ax.set_axis_off();fig.colorbar(image,ax=ax,shrink=.75)
                fig.tight_layout();fig.savefig(steps/filename,dpi=110);plt.close(fig)
                finite=array[np.isfinite(array)]
                stats=dict(name=key,shape=list(values.shape),finite_count=int(finite.size),
                           minimum=float(finite.min()) if finite.size else None,
                           maximum=float(finite.max()) if finite.size else None)
                manifest.append(stats)
                if values.ndim==3 and source.stem=='01_preprocessing':
                    histname=f'{source.stem}_{key}_distribution.png'
                    fig,axes=plt.subplots(1,len(array),figsize=(5*len(array),3),squeeze=False)
                    for channel,(ax,layer) in enumerate(zip(axes[0],array)):
                        finite_layer=layer[np.isfinite(layer)]
                        if finite_layer.size:
                            ax.hist(finite_layer,bins=80)
                            ax.set_title(f'Channel {channel}: mean={finite_layer.mean():.3g}, std={finite_layer.std():.3g}')
                        ax.set(xlabel='Value',ylabel='Pixel count')
                    fig.tight_layout();fig.savefig(steps/histname,dpi=110);plt.close(fig)
                    cards.append(f'<figure><h3>{html.escape(key)} distributions over valid area</h3><p>These are whole valid-area summaries; fitted mean/std use training support only.</p><img loading="lazy" src="{histname}"></figure>')
                cards.append(f'<figure><h3>{html.escape(key)}</h3><img loading="lazy" src="{filename}"><figcaption>{html.escape(str(stats))}</figcaption></figure>')
        sections.append(f'<section><h2>{source.stem}</h2><p>{DESCRIPTIONS.get(source.stem, "")}</p>'+''.join(cards)+'</section>')
    logs=out/'run.jsonl'
    if logs.exists():
        records=[json.loads(line) for line in logs.read_text().splitlines() if line.strip()]
        fig,axes=plt.subplots(1,2,figsize=(12,4))
        for kind,ax in zip(['training','validation'],axes):
            rows=[r for r in records if r.get('event')==kind]
            for metric in ['total','style','content']:
                if rows:ax.plot([r['step'] for r in rows],[r[metric]*(1000 if metric=='content' else 1) for r in rows],label=metric+(' ×1000' if metric=='content' else ''))
            ax.set(title=kind+' translation objective',xlabel='Update');
            if rows:ax.legend()
        fig.tight_layout();fig.savefig(steps/'training.png',dpi=110);plt.close(fig)
        sections.insert(1,'<section><h2>Training</h2><p>Held-out translation objective selects the checkpoint; this is not detection accuracy.</p><img src="training.png"></section>')
    meta=out/'pair_metadata.json'
    metadata=json.loads(meta.read_text()) if meta.exists() else {}
    configuration=json.loads((out/'effective_config.json').read_text()) if (out/'effective_config.json').exists() else {}
    details=steps/'detection_details.json'
    diagnostics=json.loads(details.read_text()) if details.exists() else {}
    extras=''
    for relative in ['overview.png','baseline/overview.png','no_translation/overview.png','gunw_comparison.png','gunw_native_valid_binary.png','gunw_valid_binary.png']:
        if (out/relative).exists():extras+=f'<h3>{relative}</h3><img src="../{relative}">'
    contents='<p><strong>Actual input features:</strong> '+html.escape(', '.join(feature_labels))+'</p>'+''.join(sections)
    document='''<!doctype html><meta charset="utf-8"><title>NISAR algorithm steps</title><style>body{font:16px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;background:#fafafa;color:#222}img{max-width:100%;height:auto}figure,section{background:white;padding:16px;margin:18px 0;border:1px solid #ddd}pre{white-space:pre-wrap}h2{position:sticky;top:0;background:white;padding:10px}figcaption{font-size:12px}</style><h1>NISAR algorithm walkthrough</h1><p>Gray pixels are unsupported where a support mask is available. Continuous map displays use 1st/99th-percentile limits; paired before/after channels share limits. Exact unclipped values are in the downloadable NPZ files. Masks use 0/1; seeds use −1 uncertain, 0 unchanged, 1 changed; FCM labels use 0 low, 1 middle, 2 high. Spatial plots use raster pixel coordinates, not geographic axes. Changing color ranges is display-only.</p><p>Trace files may be partial if the run failed; see pipeline.log and run.jsonl. A smaller mask or lower loss does not establish better accuracy.</p>'''+contents+extras+'<h2>Configuration, fitted statistics and diagnostics</h2><pre>'+html.escape(json.dumps(dict(config=configuration,pair_metadata=metadata,detection=diagnostics),indent=2))+'</pre>'
    (steps/'index.html').write_text(document)
    (steps/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return steps/'index.html'
