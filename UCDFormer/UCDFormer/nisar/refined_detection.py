"""Explicit experimental pseudo-label/RF variant; original detector is preserved."""
import numpy as np
from scipy import ndimage
from sklearn.ensemble import RandomForestClassifier
from nisar.detection import fcm3,minmax,clean
from nisar.morphology import close_valid,spatial_fcm_candidates


def local_residual_threshold(values,valid,size=31,k=3,floor=.1):
    if not valid.any(): return np.full_like(values,np.nan)
    nearest=ndimage.distance_transform_edt(~valid,return_distances=False,return_indices=True)
    filled=np.where(valid,values,values[tuple(nearest)])
    median=ndimage.median_filter(filled,size=size,mode="reflect")
    residual=ndimage.median_filter(abs(filled-median),size=size,mode="reflect")
    return np.maximum(median+k*1.4826*np.maximum(residual,.001),floor).astype(np.float32)


def refined_classify(physical_pre,physical_post,score,valid,config,trace=None,gunw=None):
    pre=10**(physical_pre[:2]/10); post=10**(physical_post[:2]/10)
    relative=(post-pre)/np.maximum(post+pre,1e-20)
    physical=np.abs(relative).mean(0)
    feature=minmax(score,valid)
    physical_weight=float(config.get("physical_fusion_weight",0))
    if not np.isfinite(physical_weight) or not 0<=physical_weight<=1:
        raise ValueError("physical_fusion_weight must be between 0 and 1")
    # Fuse evidence before clustering; multiplying RF input columns cannot set
    # their importance because tree splits are invariant to positive scaling.
    normalized_physical=minmax(physical,valid)
    evidence=feature if physical_weight==0 else ((1-physical_weight)*feature+physical_weight*normalized_physical)
    _,centers=fcm3(evidence,valid,config["seed"],trace)
    size=int(config.get("pseudo_local_window",31))
    high=local_residual_threshold(physical,valid,size,config.get("pseudo_high_k",3),config.get("pseudo_high_floor",.1))
    low=local_residual_threshold(physical,valid,size,config.get("pseudo_low_k",1.5),config.get("pseudo_low_floor",.075))
    membership=np.zeros((*valid.shape,3),np.float32)
    distances=np.maximum(abs(evidence[valid,None]-np.array(centers)[None]),1e-8)
    u=distances**-2; u/=u.sum(1,keepdims=True); membership[valid]=u
    pixel_area=float(config.get('pixel_area_m2',400))
    spacing=np.sqrt(pixel_area)
    radius=int(np.ceil(config.get('physical_closing_radius_m',0)/spacing))
    connectivity=int(config.get('morphology_connectivity',4))
    minimum=max(1,int(np.ceil(config.get('physical_support_min_area_m2',0)/pixel_area)))
    high_raw=(physical>high)&valid;weak_raw=(physical>low)&valid
    high_closed=close_valid(high_raw,valid,radius)
    weak_closed=close_valid(weak_raw,valid,radius)
    high_clean=clean(high_closed,valid,minimum,connectivity)
    weak=clean(weak_closed,valid,minimum,connectivity)
    fcm_raw,fcm_supported,fcm_fraction=spatial_fcm_candidates(
        membership,valid,config.get('pseudo_changed_membership',.6),
        config.get('fcm_membership_margin',0),
        int(np.ceil(config.get('fcm_neighbor_radius_m',0)/spacing)),
        config.get('fcm_neighbor_fraction',0))
    labels=np.full(valid.shape,-1,np.int8)
    # Closed gaps are contextual support, never automatically certain seeds.
    positives=high_raw&high_clean&fcm_supported
    if trace is not None: trace['physical_fcm_agreement_raw']=positives.copy()
    seed_minimum=max(1,int(np.ceil(config.get('seed_min_area_m2',4*pixel_area)/pixel_area)))
    positives=clean(positives,valid,seed_minimum,connectivity)
    negatives=(physical<config.get('pseudo_unchanged_floor',.05))&(membership[:,:,0]>=.7)&valid&~weak
    labels[positives]=1;labels[negatives&~positives]=0
    components,_=ndimage.label(weak,structure=ndimage.generate_binary_structure(2,1 if connectivity==4 else 2))
    seeded=np.unique(components[positives]);seeded=seeded[seeded>0]
    support=np.isin(components,seeded)&valid
    baseline_support=None
    if gunw is not None:
        from nisar.gunw import augment_physical_support,POLICY
        baseline_support=support.copy()
        support,gunw_added,moderate=augment_physical_support(
            weak,physical,low,labels,positives,valid,gunw,connectivity,
            config.get('gunw_support_policy',POLICY))
        if trace is not None:
            trace.update(gunw_coherence=gunw['coherence'],gunw_valid=gunw['valid']&valid,
                         gunw_incoherence_threshold=np.where(gunw['valid']&valid,gunw.get('threshold',np.nan),np.nan),
                         gunw_incoherence=np.where(gunw['valid']&valid,1-gunw['coherence'],np.nan),
                         gunw_incoherence_candidate=gunw['candidate']&valid,
                         gunw_moderate_physical_candidate=moderate,
                         gunw_added_weak_candidate=gunw_added,
                         candidate_support_without_gunw=baseline_support,
                         gunw_added_connected_support=support&~baseline_support)
    if trace is not None:
        trace.update(normalized_feature_score=feature,physical_relative_per_pol=relative,
                     normalized_physical_score=normalized_physical,fused_clustering_score=evidence,
                     physical_score=physical,physical_high_threshold=high,physical_low_threshold=low,
                     physical_high_binary=high_raw,physical_weak_binary=weak_raw,
                     physical_high_closed=high_closed,physical_weak_closed=weak_closed,
                     physical_high_clean=high_clean,physical_weak_clean=weak,
                     fcm_confident_raw=fcm_raw,fcm_spatially_supported=fcm_supported,
                     fcm_neighbor_agreement=fcm_fraction,
                     physical_fcm_agreement_clean=positives,combined_seed_labels=labels.copy(),
                     connected_candidate_support=support)
    negative_ids=np.flatnonzero(labels.ravel()==0); positive_ids=np.flatnonzero(labels.ravel()==1)
    if not len(negative_ids) or not len(positive_ids):
        raise ValueError(f"Refined seeds lack a class: changed={len(positive_ids)}, unchanged={len(negative_ids)}; refusing silent relaxation")
    delta=physical_post[:2]-physical_pre[:2]
    x=np.concatenate([physical_pre[:2],physical_post[:2],delta,abs(delta),relative,evidence[None]],axis=0)
    flat=np.nan_to_num(x.transpose(1,2,0).reshape(-1,x.shape[0]),nan=0)
    rng=np.random.default_rng(config["seed"]); count=min(len(negative_ids),len(positive_ids),20000)
    ids=np.concatenate([rng.choice(negative_ids,count,replace=False),rng.choice(positive_ids,count,replace=False)])
    model=RandomForestClassifier(n_estimators=200,max_depth=12,min_samples_leaf=5,n_jobs=4,random_state=config["seed"])
    model.fit(flat[ids],labels.ravel()[ids])
    votes=np.full(valid.shape,np.nan,np.float32)
    all_ids=np.flatnonzero(valid)
    positive_column=int(np.flatnonzero(model.classes_==1)[0])
    for start in range(0,len(all_ids),50000):
        selected=all_ids[start:start+50000]
        votes.ravel()[selected]=model.predict_proba(flat[selected])[:,positive_column]
    threshold=config.get("rf_positive_vote",.8)
    mask=positives|((labels==-1)&support&(votes>=threshold)&valid)
    if trace is not None:
        trace.update(rf_votes=votes,rf_vote_binary=(votes>=threshold)&valid,rf_raw_mask=mask.copy())
    co,cross=config.get("input_polarizations",["HH","HV"])[:2]
    details=dict(pseudo_method="physical_local_spatial_fcm_morphology_v3",fcm_centers=centers,
                 physical_fusion_weight=physical_weight,
                 closing_radius_pixels=radius,physical_support_min_pixels=minimum,
                 seed_min_pixels=seed_minimum,connectivity=connectivity,
                 fcm_membership_margin=config.get('fcm_membership_margin',0),
                 fcm_neighbor_radius_m=config.get('fcm_neighbor_radius_m',0),
                 fcm_neighbor_fraction=config.get('fcm_neighbor_fraction',0),
                 fcm_input="VGG minmax" if physical_weight==0 else "(1-w)*VGG minmax + w*physical minmax; shared valid support",
                 changed_seeds=int((labels==1).sum()),unchanged_seeds=int((labels==0).sum()),
                 uncertain=int(((labels==-1)&valid).sum()),samples_per_class=count,
                 rf_features=[f"pre_{co}_dB",f"pre_{cross}_dB",f"post_{co}_dB",f"post_{cross}_dB",f"signed_{co}_dB_change",
                              f"signed_{cross}_dB_change",f"absolute_{co}_dB_change",f"absolute_{cross}_dB_change",
                              f"{co}_normalized_change",f"{cross}_normalized_change",
                              "physical_VGG_fused_score" if physical_weight else "VGG_score"],
                 final_classifier=f"temporal-feature RF; uncertain positives require >={threshold:g} vote and weak physical component connected to positive seed",
                 rf_positive_vote=threshold,local_window_pixels=size,
                 threshold_statistic="local residual MAD proxy; uncalibrated",
                 pseudo_changed_membership=config.get("pseudo_changed_membership",.6),
                 memberships_calibrated=False,raw_positive_seeds=int(positives.sum()),
                 weak_connected_support_pixels=int(support.sum()),
                 modification="new pseudo-label generator, temporal RF descriptors and hysteresis support; not exact original UCDFormer")
    extras=dict(physical_score=physical,high_threshold=high,low_threshold=low,rf_votes=votes,
                candidate_support=support.astype(np.uint8),feature_changed_membership=membership[:,:,2],
                physical_high_closed=high_closed,physical_weak_closed=weak_closed,
                physical_high_clean=high_clean,physical_weak_clean=weak,
                fcm_confident_raw=fcm_raw,fcm_spatially_supported=fcm_supported)
    if gunw is not None:
        details['gunw_support']=dict(mode='pre-RF uncertain physical-corridor support',
            incoherence_threshold=gunw.get('threshold'),
            original_support_pixels=int(baseline_support.sum()),
            added_weak_candidate_pixels=int(gunw_added.sum()),
            added_seed_connected_support_pixels=int((support&~baseline_support).sum()),
            training_seeds_changed=False,rf_features_changed=False,
            note='Coherence never labels a pixel changed by itself; existing RF and final morphology still apply')
        extras.update(gunw_coherence=np.where(gunw['valid']&valid,gunw['coherence'],np.nan),
                      gunw_valid=(gunw['valid']&valid).astype(np.uint8),
                      gunw_added_support=(support&~baseline_support).astype(np.uint8),
                      candidate_support_without_gunw=baseline_support.astype(np.uint8),
                      mask_without_gunw=(positives|((labels==-1)&baseline_support&(votes>=threshold)&valid)).astype(np.uint8))
    return mask,labels,model,details,extras
