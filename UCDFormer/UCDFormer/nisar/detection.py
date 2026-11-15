"""Bounded fuzzy clustering, masked adaptive labels and RF change extraction."""
import numpy as np
from scipy import ndimage
from sklearn.ensemble import RandomForestClassifier
from skimage.filters import threshold_otsu


def minmax(score,valid):
    result=np.full(score.shape,np.nan,np.float32)
    if not valid.any(): return result
    x=score[valid]; lo=float(x.min()); hi=float(x.max())
    result[valid]=(x-lo)/(hi-lo+np.exp(-10))
    return result


def fcm3(score,valid,seed=123,trace=None):
    """Scalar fuzzy c-means, m=2; fit capped sample, predict in vectorized form."""
    values=score[valid].astype(np.float64)
    if len(values)<3 or np.ptp(values)<1e-6:
        return np.zeros(score.shape,np.uint8),[float(values[0])]*3 if len(values) else [0,0,0]
    rng=np.random.default_rng(seed)
    sample=rng.choice(values,min(len(values),50000),replace=False)
    centers=np.quantile(sample,[.15,.5,.9])
    history=[centers.copy()]
    for _ in range(100):
        distances=np.maximum(abs(sample[:,None]-centers[None]),1e-8)
        membership=distances**-2; membership/=membership.sum(1,keepdims=True)
        weight=membership**2
        new=(weight*sample[:,None]).sum(0)/weight.sum(0)
        history.append(new.copy())
        if np.max(abs(new-centers))<1e-6: centers=new; break
        centers=new
    centers.sort()
    labels=np.zeros(score.shape,np.uint8)
    labels[valid]=abs(values[:,None]-centers[None]).argmin(1)
    if trace is not None:
        trace["fcm_center_history"]=np.asarray(history)
        trace["fcm_clusters"]=np.where(valid,labels,np.nan)
        trace["fcm_high_binary"]=(labels==2)&valid
        trace["fcm_low_binary"]=(labels==0)&valid
        distances=np.maximum(abs(values[:,None]-centers[None]),1e-8)
        u=distances**-2; u/=u.sum(1,keepdims=True)
        for i in range(3):
            layer=np.full(score.shape,np.nan,np.float32); layer[valid]=u[:,i]
            trace[f"fcm_membership_{i}"]=layer
    return labels,centers.tolist()


def clean(mask,valid,min_pixels,connectivity=4):
    # No closing across invalid gaps; remove only physically small components.
    if connectivity not in (4,8):raise ValueError("connectivity must be 4 or 8")
    labels,n=ndimage.label(mask&valid,structure=ndimage.generate_binary_structure(2,1 if connectivity==4 else 2))
    sizes=np.bincount(labels.ravel()); keep=sizes>=min_pixels; keep[0]=False
    return keep[labels]&valid


def pseudo_labels(score,valid,pixel_size=20,sigma_m=1000,seed=123,trace=None):
    normalized=minmax(score,valid)
    output=np.full(score.shape,-1,np.int8)
    if not valid.any(): return output,dict(reason="no valid score")
    if np.ptp(normalized[valid])<1e-6:
        output[valid]=0
        return output,dict(reason="constant score; no supported changed seeds",fcm_centers=[0,0,0])
    clusters,centers=fcm3(normalized,valid,seed,trace)
    sigma=max(1,sigma_m/pixel_size)
    numerator=ndimage.gaussian_filter(np.where(valid,normalized,0),sigma)
    denominator=ndimage.gaussian_filter(valid.astype(np.float32),sigma)
    local=numerator/np.maximum(denominator,1e-8)
    adaptive=(normalized>2*local)&valid
    if trace is not None:
        trace.update(normalized_feature_score=normalized,gaussian_local_mean=local,
                     gaussian_threshold=2*local,gaussian_adaptive_raw=adaptive.copy())
    adaptive=clean(adaptive,valid,4)
    if trace is not None: trace["gaussian_adaptive_clean"]=adaptive.copy()
    output[(clusters==2)&adaptive&valid]=1
    output[(clusters==0)&~adaptive&valid]=0
    if trace is not None: trace["combined_seed_labels"]=output.copy()
    return output,dict(fcm_centers=centers,adaptive_sigma_m=sigma_m,
                       formula="changed=highFCM AND adaptive; unchanged=lowFCM AND NOT adaptive",
                       changed_seeds=int((output==1).sum()),unchanged_seeds=int((output==0).sum()),
                       uncertain=int(((output==-1)&valid).sum()))


def classify(pre,post,score,valid,seed=123,pixel_size=20,sigma_m=1000,trace=None):
    labels,diagnostics=pseudo_labels(score,valid,pixel_size,sigma_m,seed,trace)
    x=np.concatenate([pre,post],axis=0).transpose(1,2,0)
    negatives=np.flatnonzero(labels.ravel()==0); positives=np.flatnonzero(labels.ravel()==1)
    rng=np.random.default_rng(seed)
    if not len(negatives) or not len(positives):
        # Do not claim a fitted RF or fabricate changed examples.
        finite=score[valid]
        threshold=float(threshold_otsu(finite)) if len(finite) and np.ptp(finite)>1e-6 else float("inf")
        mask=(score>threshold)&valid
        return mask,labels,None,dict(**diagnostics,classifier="not fitted; empty seed class",fallback="score Otsu",threshold=threshold if np.isfinite(threshold) else None)
    count=min(len(negatives),len(positives),20000)
    indices=np.concatenate([rng.choice(negatives,count,replace=False),rng.choice(positives,count,replace=False)])
    forest=RandomForestClassifier(n_estimators=150,max_depth=20,min_samples_leaf=3,n_jobs=4,random_state=seed)
    flat=x.reshape(-1,x.shape[-1]); forest.fit(flat[indices],labels.ravel()[indices])
    mask=labels==1
    uncertain=np.flatnonzero((labels.ravel()==-1)&valid.ravel())
    for start in range(0,len(uncertain),50000):
        ids=uncertain[start:start+50000]; mask.ravel()[ids]=forest.predict(flat[ids])==1
    if trace is not None: trace["rf_raw_mask"]=mask.copy()
    diagnostics.update(classifier="RandomForestClassifier",samples_per_class=count,random_state=seed,
                       uncertain_predicted=len(uncertain))
    return mask,labels,forest,diagnostics
