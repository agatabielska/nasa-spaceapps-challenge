#!/usr/bin/env python3
"""Reproducible real-GCOV preprocessing, bounded UCDFormer adaptation and exports."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps"))
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import numpy as np
import torch
from torch.utils.data import DataLoader
from scipy import ndimage
from skimage.filters import threshold_otsu
import joblib
from nisar.data import prepare,PairedChangeDataset,positions
from nisar.model import SARUCDFormer
from nisar.config import resolve_config,scene_settings
from nisar.detection import classify,clean,minmax
from nisar.export import export,write_tif


def log(out,event,**values):
    record=dict(time_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),event=event,**values)
    line=json.dumps(record,allow_nan=False)
    print(line,flush=True)
    with (out/"run.jsonl").open("a") as stream: stream.write(line+"\n")


def load_pair(out):
    data=np.load(out/"pair.npz")
    return data["pre"],data["post"],data["valid"],json.loads((out/"pair_metadata.json").read_text())


def baseline(out,pre,post,valid,meta):
    data=np.load(out/"pair.npz")
    delta=np.abs(data["physical_post"][:2]-data["physical_pre"][:2])
    scale=np.nanpercentile(delta[:,valid],75,axis=1).clip(.1)
    score=(delta/scale[:,None,None]).mean(0)
    values=score[valid]; threshold=float(threshold_otsu(values)) if np.ptp(values)>1e-6 else None
    mask=(score>threshold)&valid if threshold is not None else np.zeros_like(valid)
    labels=np.full(valid.shape,-1,np.int8)
    report=export(out/"baseline",pre,post,valid,score,mask,labels,meta,"SAR log-change + Otsu",
                  dict(threshold=threshold,per_pol_scale_db=scale.tolist(),training="none"))
    if meta.get("visualize_steps",False):
        (out/"steps").mkdir(exist_ok=True)
        np.savez_compressed(out/"steps/00_physical_baseline.npz",physical_abs_db_change=delta,
                            baseline_score=score,baseline_mask=mask,model_support=valid,
                            otsu_threshold=np.array([threshold if threshold is not None else np.nan]))
    log(out,"baseline_complete",changed_fraction=report["changed_fraction"],threshold=threshold)


def initialize(config,device,meta):
    if "vgg_standardization" not in meta:
        raise ValueError("Prepared pair lacks NISAR statistics; prepare and retrain in a new output directory")
    model=SARUCDFormer(config["vgg"],config["generator"],meta["vgg_standardization"]).to(device)
    model.initialization["input_features"]=meta.get("feature_names",model.initialization["input_features"])
    return model


def train(config,out,pre,post,valid,meta,device):
    model=initialize(config,device,meta)
    (out/"initialization.json").write_text(json.dumps(model.initialization,indent=2)+"\n")
    optimizer=torch.optim.Adam(list(model.translator.parameters())+list(model.decoder.parameters()),
                               lr=config["learning_rate"],betas=(.8,.999),weight_decay=1e-4,amsgrad=True)
    trainset=PairedChangeDataset(pre,post,valid,meta["train_windows"])
    valset=PairedChangeDataset(pre,post,valid,meta["validation_windows"])
    def cache(dataset):
        result=[]
        for index,item in enumerate(DataLoader(dataset,batch_size=1,num_workers=0)):
            trace={} if config.get("visualize_steps") and dataset is trainset and index==0 else None
            result.append(model.target(item["pre"].to(device),item["post"].to(device),trace=trace))
            if trace is not None:
                (out/"steps").mkdir(exist_ok=True)
                np.savez_compressed(out/"steps/02a_training_targets.npz",**trace)
        return result
    log(out,"caching_fixed_targets",train=len(trainset),validation=len(valset),device=str(device))
    train_targets=cache(trainset); val_targets=cache(valset)
    rng=np.random.default_rng(config["seed"])
    def validate(step):
        model.eval(); rows=[]; healthy=True
        with torch.no_grad():
            for target in val_targets:
                total,style,content,translated=model.objective(target)
                row=[float(total),float(style),float(content),float(translated.std())]
                healthy &= bool(np.isfinite(row).all() and row[-1]>1e-4)
                rows.append(row)
        value=np.asarray(rows).mean(0)
        log(out,"validation",step=step,total=float(value[0]),style=float(value[1]),
            content=float(value[2]),output_std=float(value[3]),healthy=healthy)
        return float(value[0]),healthy
    def save(name,step,metric):
        target=out/(name+".pt"); temporary=target.with_suffix(".tmp")
        torch.save(dict(translator=model.translator.state_dict(),decoder=model.decoder.state_dict(),
                        optimizer=optimizer.state_dict(),step=step,val_translation_loss=metric,
                        config=config,seed=config["seed"],vgg_standardization=meta["vgg_standardization"],
                        selection="held-out translation objective; NOT detection accuracy"),temporary)
        temporary.replace(target)
    initial,healthy=validate(0)
    if not healthy: raise RuntimeError("Initialization failed health checks")
    best=initial; last_metric=initial; save("initial",0,initial); save("best",0,best)
    stale=0; best_step=0; started=time.monotonic(); step=0
    for step in range(1,config["max_updates"]+1):
        if time.monotonic()-started>config["max_train_seconds"]: break
        model.train(); optimizer.zero_grad(set_to_none=True)
        target=train_targets[int(rng.integers(len(train_targets)))]
        total,style,content,translated=model.objective(target)
        if not torch.isfinite(total): raise RuntimeError("Nonfinite translation objective")
        total.backward()
        norm=torch.nn.utils.clip_grad_norm_(list(model.translator.parameters())+list(model.decoder.parameters()),100.)
        if not torch.isfinite(norm): raise RuntimeError("Nonfinite gradients")
        optimizer.step()
        if step==1 or step%20==0:
            log(out,"training",step=step,total=float(total.detach()),style=float(style.detach()),
                content=float(content.detach()),gradient_norm=float(norm),
                elapsed_seconds=round(time.monotonic()-started,2),
                peak_cuda_gb=round(torch.cuda.max_memory_allocated()/1e9,3) if device.type=="cuda" else None)
        if step%config["validate_every"]==0 or step==config["max_updates"]:
            metric,healthy=validate(step)
            last_metric=metric
            if healthy and metric<best*(1-1e-4):
                best=metric; best_step=step; stale=0; save("best",step,best)
            else: stale+=1
            if stale>=config["patience"]:
                log(out,"early_stopping",step=step,reason="no held-out objective improvement")
                break
    save("last",step,last_metric)
    result=dict(updates=step,best_step=best_step,initial_validation=initial,best_validation=best,
                elapsed_seconds=time.monotonic()-started,training_patch_size=meta["split"]["train_patch_size"],validation_patch_size=meta["split"]["val_patch_size"],
                selection="translation objective only, no independent change labels",gradient_clip_norm=100.)
    (out/"training_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    log(out,"training_complete",**result)


def infer(config,out,pre,post,valid,meta,device):
    model=initialize(config,device,meta)
    state=torch.load(out/"best.pt",map_location=device,weights_only=True)
    if state.get("vgg_standardization")!=meta["vgg_standardization"]:
        raise ValueError("Checkpoint normalization differs from prepared pair; retrain with NISAR statistics")
    model.translator.load_state_dict(state["translator"],strict=True)
    model.decoder.load_state_dict(state["decoder"],strict=True); model.eval()
    n=config["inference_patch"]; stride=config["inference_stride"]
    accumulated=np.zeros(valid.shape,np.float64); weights=np.zeros(valid.shape,np.float64)
    raw=np.zeros(valid.shape,np.float64)
    blend=np.outer(np.hanning(n),np.hanning(n)).clip(.01)
    # Fill network context only; filled pixels never become valid predictions.
    # A small exclusion halo replaces dropping an entire 256-pixel tile.
    indices=ndimage.distance_transform_edt(~valid,return_distances=False,return_indices=True)
    pre_context=pre[:,indices[0],indices[1]]
    post_context=post[:,indices[0],indices[1]]
    guard=int(config.get("invalid_context_guard",8))
    safe=valid & ~ndimage.binary_dilation(~valid,iterations=guard) if guard else valid.copy()
    windows=[(y,x) for y in positions(valid.shape[0],n,stride) for x in positions(valid.shape[1],n,stride)
             if valid[y:y+n,x:x+n].mean()>=config.get("minimum_tile_valid_fraction",.5)]
    if not windows: raise RuntimeError("No sufficiently valid inference tiles")
    log(out,"inference_device",device=str(device),model_device=str(next(model.parameters()).device),
        gpu_name=torch.cuda.get_device_name(device) if device.type=='cuda' else None,
        feature_scoring="on tensor device; shared pre/post encodings; linear 95th-percentile kthvalue",
        tiles=len(windows),tile_shape=[n,n])
    if device.type=='cuda':torch.cuda.synchronize(device)
    tiled_started=time.perf_counter()
    for index,(y,x) in enumerate(windows):
        started=time.perf_counter()
        a=torch.from_numpy(pre_context[:,y:y+n,x:x+n].copy())[None].to(device)
        b=torch.from_numpy(post_context[:,y:y+n,x:x+n].copy())[None].to(device)
        tile_valid=valid[y:y+n,x:x+n]
        first={} if index==0 and config.get('visualize_steps') else None
        score,untranslated=model.score_pair(a,b,valid=tile_valid,trace=first)
        if not np.isfinite(score).all() or not np.isfinite(untranslated).all():
            raise RuntimeError('Nonfinite feature score')
        scored=time.perf_counter()
        if first is not None:
            first.update(patch_valid=tile_valid,patch_origin_yx=np.array([y,x]),translated_patch_score=score)
            (out/'steps').mkdir(exist_ok=True)
            np.savez_compressed(out/'steps/02_vgg_example_patch.npz',**first)
        accumulated[y:y+n,x:x+n]+=score*blend;raw[y:y+n,x:x+n]+=untranslated*blend
        weights[y:y+n,x:x+n]+=blend
        log(out,"inference_tile",completed=index+1,total=len(windows),
            network_and_score_seconds=round(scored-started,4),
            trace_and_assembly_seconds=round(time.perf_counter()-scored,4),
            peak_cuda_gb=round(torch.cuda.max_memory_allocated(device)/1e9,3) if device.type=='cuda' else None)
    tile_summary=dict(device=str(device),tiles=len(windows),elapsed_seconds=time.perf_counter()-tiled_started,
                      feature_scoring='tensor-device percentile/saturation/L2',encoder_passes_per_tile=3)
    (out/'inference_performance.json').write_text(json.dumps(tile_summary,indent=2)+'\n')
    log(out,'inference_tiles_complete',**tile_summary)
    supported=safe&(weights>0)
    score=np.full(valid.shape,np.nan,np.float32); no_translation=score.copy()
    score[supported]=accumulated[supported]/weights[supported]
    no_translation[supported]=raw[supported]/weights[supported]
    pixel_size=abs(meta["transform"][0])
    refined=config.get("pseudo_method") in ("physical_feature_v2","physical_feature_v3")
    gunw=None
    if config.get('gunw'):
        if not refined:raise ValueError('--gunw requires the refined physical-feature detector')
        from nisar.gunw import load_gunw
        log(out,'gunw_preparing',path=config['gunw'])
        gunw,gunw_details,native_gunw=load_gunw(config['gunw'],config,meta)
        (out/'gunw_metadata.json').write_text(json.dumps(gunw_details,indent=2)+'\n')
        np.savez_compressed(out/'gunw_native_masked.npz',**native_gunw)
        from PIL import Image
        Image.fromarray(native_gunw['valid'].astype(np.uint8)*255).save(out/'gunw_native_valid_binary.png')
        for name in ('coherence','valid','candidate'):
            values=gunw[name]
            write_tif(out/('gunw_'+name+'.tif'),np.where(supported,values,np.nan).astype(np.float32),meta,np.nan)
        log(out,'gunw_ready',native_usable_pixels=gunw_details['native_usable_pixels'],
            incoherence_threshold=gunw_details['threshold_fit']['threshold'])
    def detect(scores,trace=None):
        if refined:
            from nisar.refined_detection import refined_classify
            data=np.load(out/"pair.npz")
            return refined_classify(data["physical_pre"],data["physical_post"],scores,supported,config,trace,gunw=gunw)
        return (*classify(pre,post,scores,supported,config["seed"],pixel_size,config["adaptive_sigma_m"],trace),{})
    log(out,"classification_start",variant="translated",valid_pixels=int(supported.sum()))
    trace={} if config.get("visualize_steps") else None
    if trace is not None:
        trace.update(model_support=supported,input_valid=valid,guard_safe=safe,overlap_weight_sum=weights,translated_score=score,no_translation_score=no_translation)
    if trace is not None:
        from nisar.detection import pseudo_labels
        comparison={}
        pseudo_labels(score,supported,pixel_size,config["adaptive_sigma_m"],config["seed"],comparison)
        trace.update({"comparison_strict_"+key:value for key,value in comparison.items()})
    try:
        mask,labels,forest,details,extras=detect(score,trace)
    finally:
        if trace is not None:
            np.savez_compressed(out/"steps/03_detection.npz",**trace)
    log(out,"classification_complete",variant="translated",changed_pixels=int(mask.sum()))
    raw_mask=mask.copy()
    # Convert physical area to a pixel count without rounding the minimum down.
    transform=meta["transform"]
    pixel_area=abs(transform[0]*transform[4]-transform[1]*transform[3])
    from nisar.morphology import final_cleanup
    allowed=(extras['candidate_support'].astype(bool)&(labels!=0)) if refined else supported
    mask,closed_mask,cleanup=final_cleanup(raw_mask,supported,config,pixel_area,allowed)
    baseline_gunw_mask=None
    if gunw is not None:
        baseline_gunw_mask,_,_=final_cleanup(extras['mask_without_gunw'].astype(bool),supported,config,pixel_area,
            extras['candidate_support_without_gunw'].astype(bool)&(labels!=0))
        write_tif(out/'change_mask_without_gunw.tif',np.where(supported,baseline_gunw_mask,255).astype(np.uint8),meta,255)
        from nisar.gunw import save_review
        save_review(out,gunw,supported,baseline_gunw_mask,mask,extras['gunw_added_support'].astype(bool))
    min_component_pixels=cleanup['min_pixels']
    if trace is not None:
        trace.update(final_mask=mask,pseudo_labels=labels,final_mask_closed=closed_mask,
                     final_closing_added=closed_mask&~raw_mask,morphology_removed=closed_mask&~mask)
        if baseline_gunw_mask is not None:
            trace.update(final_mask_without_gunw=baseline_gunw_mask,
                         final_added_with_gunw=mask&~baseline_gunw_mask,
                         final_removed_with_gunw=baseline_gunw_mask&~mask)
        if forest is not None:
            trace["rf_feature_importance"]=forest.feature_importances_
            details["rf_feature_importance_names"]=details.get("rf_features",["pre_HH_scaled","pre_HV_scaled","pre_ratio_scaled","post_HH_scaled","post_HV_scaled","post_ratio_scaled"])
        np.savez_compressed(out/"steps/03_detection.npz",**trace)
        (out/"steps/detection_details.json").write_text(json.dumps(details,indent=2)+"\n")
    if forest is not None: joblib.dump(forest,out/"random_forest.joblib")
    write_tif(out/"change_mask_closed.tif",np.where(supported,closed_mask,255).astype(np.uint8),meta,255)
    write_tif(out/"change_mask_raw.tif",np.where(supported,raw_mask,255).astype(np.uint8),meta,255)
    write_tif(out/"no_translation_score.tif",no_translation,meta,np.nan)
    write_tif(out/"pseudo_labels.tif",np.where(supported,labels, -2).astype(np.int8),meta,-2)
    details.update(checkpoint_step=state["step"],val_translation_loss=state["val_translation_loss"],
                   native_valid_fraction=float(valid.mean()),model_supported_fraction=float(supported.mean()),
                   inference_context_policy="nearest valid context only; filled pixels excluded; saturation fitted on valid pixels",
                   invalid_context_guard_pixels=guard,
                   feature_score="original per-date 95th-percentile feature saturation + L2; overlap averaged before labeling",
                   area_filter_m2=config["morphology_min_area_m2"],
                   area_filter_min_pixels=min_component_pixels,
                   area_filter_connectivity=config.get('morphology_connectivity',4),
                   final_closing_radius_pixels=cleanup['radius_pixels'],
                   final_closing_added_pixels=cleanup['added_pixels'],
                   final_closing_policy="Short gaps may be added inside seed-connected physical support, excluding unchanged seeds and neighborhoods of nodata; additions need not pass the RF vote gate",
                   final_area_filter_removed_pixels=cleanup['removed_pixels'],
                   area_filter_removed_pixels=int((raw_mask&~mask).sum()),
                   pseudo_label_legend={"-2":"invalid","-1":"uncertain","0":"unchanged seed","1":"changed seed"})
    if not refined:
        details["final_classifier"]="RF on paired physical-feature adapter values; confident assignments retained"
    details["input_power_filter"]=meta.get("speckle_filter")
    report=export(out,pre,post,supported,score,mask,labels,meta,"UCDFormer SAR adaptation",details)
    if refined:
        from nisar.review import pseudo_review
        for name,values in extras.items():
            write_tif(out/(name+".tif"),np.where(supported,values,np.nan).astype(np.float32),meta,np.nan)
        pseudo_review(out,pre,post,supported,labels,mask,extras,details)
    log(out,"classification_start",variant="no_translation")
    no_mask,no_labels,_,no_details,no_extras=detect(no_translation)
    no_allowed=(no_extras['candidate_support'].astype(bool)&(no_labels!=0)) if refined else supported
    no_mask,_,no_cleanup=final_cleanup(no_mask,supported,config,pixel_area,no_allowed)
    no_details['final_cleanup']=no_cleanup
    export(out/"no_translation",pre,post,supported,no_translation,no_mask,no_labels,meta,"VGG SAR features without translation",no_details)
    log(out,"inference_complete",changed_fraction=report["changed_fraction"],supported_fraction=float(supported.mean()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",default="configs/etna_run.json")
    parser.add_argument("--settings",default="configs/pipeline.json")
    parser.add_argument("--gunw",help="Optional GUNW HDF5 for pre-RF coherence support; omitted = original pipeline")
    parser.add_argument("--output",help="New output directory; required to reuse prepared data for train/infer")
    parser.add_argument("--visualize-steps",action="store_true")
    parser.add_argument("--stage",choices=["prepare","train","infer","all"],default="all")
    parser.add_argument("--max-updates",type=int)
    parser.add_argument("--device",default="cuda")
    args=parser.parse_args(); os.chdir(ROOT)
    config,inputs,settings=resolve_config(args.config,args.settings,args.output,args.gunw)
    if args.stage in ("train","infer") and not args.output:
        parser.error("--output is required for train/infer to select the prepared run")
    config["visualize_steps"]=args.visualize_steps
    if args.max_updates is not None: config["max_updates"]=args.max_updates
    out=Path(config["output"])
    if args.stage in ("prepare","all") and out.exists() and any(p.name!="pipeline.log" for p in out.iterdir()):
        parser.error("Preparation requires a new or empty output directory")
    if args.stage in ("train","infer"):
        if not (out/"input.json").exists() or json.loads((out/"input.json").read_text())!=inputs:
            parser.error("Prepared run acquisition inputs do not match; prepare a fresh run")
        if not (out/"pipeline_settings.json").exists() or json.loads((out/"pipeline_settings.json").read_text())!=settings:
            parser.error("Prepared run processing settings do not match; prepare a fresh run")
    out.mkdir(parents=True,exist_ok=True)
    (out/"input.json").write_text(json.dumps(inputs,indent=2)+"\n")
    (out/"pipeline_settings.json").write_text(json.dumps(settings,indent=2)+"\n")
    (out/"effective_config.json").write_text(json.dumps(config,indent=2)+"\n")
    np.random.seed(config["seed"]); torch.manual_seed(config["seed"]); torch.set_num_threads(4)
    try:
        log(out,"start",stage=args.stage,torch=torch.__version__,numpy=np.__version__)
        if args.stage in ["prepare","all"]:
            pre,post,valid,meta=prepare(config,out)
            baseline(out,pre,post,valid,meta)
            log(out,"preprocessing_complete",shape=list(valid.shape),valid_fraction=float(valid.mean()),split=meta["split"])
        else: pre,post,valid,meta=load_pair(out)
        derived=scene_settings(config,meta,valid.shape)
        config.update(derived)
        (out/"derived_settings.json").write_text(json.dumps(derived,indent=2)+"\n")
        (out/"effective_config.json").write_text(json.dumps(config,indent=2)+"\n")
        if args.stage in ["train","infer","all"]:
            device=torch.device(args.device)
            if device.type=="cuda" and not torch.cuda.is_available(): raise RuntimeError("CUDA unavailable; no silent CPU fallback")
            if args.stage in ["train","all"]: train(config,out,pre,post,valid,meta,device)
            if args.stage in ["infer","all"]: infer(config,out,pre,post,valid,meta,device)
        log(out,"stage_complete",stage=args.stage)
    except Exception as exc:
        log(out,"failed",error=type(exc).__name__,message=str(exc)); raise


if __name__=="__main__": main()
