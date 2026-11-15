"""Original StyleFormer/decoder with a SAR input boundary and explicit initialization."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("ucdformer_legacy_networks",ROOT/"UCDFormer/networks.py")
legacy=importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)


class Encoder(nn.Module):
    def __init__(self,path):
        super().__init__()
        state=torch.load(path,map_location="cpu",weights_only=True)
        network=copy.deepcopy(legacy.vgg16)
        for dest,source in zip(legacy.vgg_conv_list,legacy.vgg_model_conv_list):
            network[dest].weight=nn.Parameter(state[f"features.{source}.weight"].clone(),requires_grad=False)
            network[dest].bias=nn.Parameter(state[f"features.{source}.bias"].clone(),requires_grad=False)
        self.blocks=nn.ModuleList([network[:3],network[3:10],network[10:17],network[17:27]])
        self.requires_grad_(False)

    def forward(self,x):
        result=[]
        for block in self.blocks:
            x=block(x); result.append(x)
        return result


def stats(x):
    values=x.flatten(2)
    return values.mean(2),(values.var(2,unbiased=True)+1e-5).sqrt()


def content_loss(x,y):
    # Preserve the repository's actual raw-dot spatial affinity calculation.
    # Its function is named cosine distance but normalized vectors are unused there.
    def affinity(t):
        t=t.flatten(2)
        distances=1-t.transpose(1,2).bmm(t)
        denom=distances.sum(1,keepdim=True)
        denom=torch.where(denom.abs()<1e-8,torch.full_like(denom,1e-8),denom)
        return distances/denom
    return (affinity(x)-affinity(y)).abs().mean()


def feature_difference(a,b,valid=None,trace=None):
    """Original per-date per-band 95th-percentile saturation, streamed in channels.

    Raw L2 returned before any spatial min-max. Exactly the original interpolation
    convention; chunking avoids materializing both full 960-band mosaics.
    """
    if a[0].is_cuda:
        result,_=tensor_feature_scores(a,b,valid=valid,trace=trace)
        return result.cpu().numpy()
    shape=a[0].shape[-2:]
    score=np.zeros(shape,np.float64)
    with torch.no_grad():
        for block,(x,y) in enumerate(zip(a,b)):
            for start in range(0,x.shape[1],32):
                u=F.interpolate(x[:,start:start+32],size=shape,mode="bilinear",align_corners=True)[0].cpu().numpy().astype(np.float64)
                v=F.interpolate(y[:,start:start+32],size=shape,mode="bilinear",align_corners=True)[0].cpu().numpy().astype(np.float64)
                def saturate(t):
                    samples=t[:,valid] if valid is not None else t.reshape(t.shape[0],-1)
                    lo=samples.min(1)[:,None,None]
                    hi=np.percentile(samples,95,axis=1)[:,None,None]
                    return np.minimum((t-lo)/(hi-lo+np.exp(-10)),1)
                su,sv=saturate(u),saturate(v)
                if trace is not None and start==0:
                    trace[f"score_block_{block}_saturated_translated_first_channels"]=su[:3]
                    trace[f"score_block_{block}_saturated_post_first_channels"]=sv[:3]
                delta=su-sv
                score+=(delta*delta).sum(0)
    return np.sqrt(score).astype(np.float32)


@torch.no_grad()
def tensor_feature_scores(pre,post,translated=None,valid=None,trace=None):
    """Stream saturation and both L2 scores on the tensor device.

    Matches NumPy's linear 95th percentile using two order statistics, avoiding
    a full sort and feature transfers. Float64 retains the reference arithmetic.
    """
    shape=pre[0].shape[-2:];device=pre[0].device
    indices=None
    if valid is not None:
        if torch.is_tensor(valid):
            indices=torch.nonzero(valid.reshape(-1),as_tuple=False).flatten().to(device)
        else:
            indices=torch.as_tensor(np.flatnonzero(valid),device=device)
        if indices.numel()==0:raise ValueError('No valid samples for feature saturation')
    main=torch.zeros(shape,dtype=torch.float64,device=device)
    untranslated=torch.zeros_like(main)
    for block,(a,b) in enumerate(zip(pre,post)):
        for start in range(0,a.shape[1],32):
            def saturate(features):
                values=F.interpolate(features[:,start:start+32],size=shape,mode='bilinear',align_corners=True)[0].to(torch.float64)
                samples=values.flatten(1)
                if indices is not None:samples=samples.index_select(1,indices)
                rank=(samples.shape[1]-1)*.95
                low=int(np.floor(rank));high=int(np.ceil(rank))
                q0=samples.kthvalue(low+1,dim=1).values
                q1=samples.kthvalue(high+1,dim=1).values if high!=low else q0
                hi=(q0+(q1-q0)*(rank-low))[:,None,None]
                lo=samples.amin(1)[:,None,None]
                return ((values-lo)/(hi-lo+np.exp(-10))).clamp_max(1)
            u=saturate(a);v=saturate(b)
            untranslated.add_(((u-v)**2).sum(0))
            t=saturate(translated[block]) if translated is not None else u
            if translated is not None:main.add_(((t-v)**2).sum(0))
            if trace is not None and start==0:
                trace[f'score_block_{block}_saturated_translated_first_channels']=t[:3].cpu().numpy()
                trace[f'score_block_{block}_saturated_post_first_channels']=v[:3].cpu().numpy()
    untranslated=untranslated.sqrt().float()
    main=main.sqrt().float() if translated is not None else untranslated
    return main,untranslated


class SARUCDFormer(nn.Module):
    def __init__(self,vgg_path,generator_path,standardization):
        super().__init__()
        mean=torch.as_tensor(standardization["mean"],dtype=torch.float32)
        std=torch.as_tensor(standardization["std"],dtype=torch.float32)
        if (mean.shape!=(3,) or std.shape!=(3,) or not torch.isfinite(mean).all()
                or not torch.isfinite(std).all() or not (std>0).all()):
            raise ValueError("Expected three finite NISAR channel means and positive standard deviations")
        options=SimpleNamespace(luma_bins=4,channel_multiplier=1,spatial_bin=16,
                                n_input_channel=256,n_input_size=64,group_num=16,
                                alpha=1,selection="Ax+b",inter_selection="A1x+b2")
        self.encoder=Encoder(vgg_path)
        self.translator=legacy.StyleFormer(options)
        self.decoder=legacy.decoder(options)
        checkpoint=torch.load(generator_path,map_location="cpu",weights_only=True)
        for key,model in [("a",self.translator),("b",self.decoder)]:
            cleaned={k.removeprefix("module."):v for k,v in checkpoint[key].items()}
            model.load_state_dict(cleaned,strict=True)
        self.register_buffer("mean",mean.view(1,3,1,1))
        self.register_buffer("std",std.view(1,3,1,1))
        self.initialization=dict(vgg=str(vgg_path),generator=str(generator_path),
                                 loaded="all original translator/decoder tensors, strict=True",
                                 skipped=[],reinitialized=[],input_features=["HH_dB","HV_dB","log_pol_ratio"],
                                 vgg_standardization=standardization,
                                 original_content_loss="raw-dot affinity as executed in utils.py; near-zero denominator guarded")

    def normalize(self,x): return (x-self.mean)/self.std

    def encode(self,x): return self.encoder(self.normalize(x))

    def forward(self,pre,post):
        a=self.encode(pre); b=self.encode(post)
        return self.decoder(self.translator(b[-2],a[-2]))

    @torch.no_grad()
    def target(self,pre,post,trace=None):
        a=self.encode(pre); b=self.encode(post)
        prior,_=tensor_feature_scores(a,b)
        prior=(prior-prior.amin())/(prior.amax()-prior.amin()+np.exp(-10))
        mask=prior[None,None]
        mixed=(1-mask)*self.normalize(post)+mask*self.normalize(pre)
        if trace is not None:
            trace.update(initial_feature_difference=prior.cpu().numpy(),change_weight=mask[0,0].cpu().numpy(),
                         normalized_training_pre=self.normalize(pre)[0].cpu().numpy(),
                         normalized_training_post=self.normalize(post)[0].cpu().numpy(),
                         mixed_style_target= mixed[0].cpu().numpy(),
                         content_feature_channel_mean=a[-1][0].mean(0).cpu().numpy())
        style_stats=[stats(x) for x in self.encoder(mixed)]
        return dict(content=a[-2].detach(),style=b[-2].detach(),
                    content_loss_target=a[-1].detach(),style_stats=style_stats)

    def objective(self,target):
        output=self.decoder(self.translator(target["style"],target["content"]))
        feats=self.encoder(output)
        style=sum(F.mse_loss(a,c)+F.mse_loss(b,d) for (a,b),(c,d) in zip(map(stats,feats),target["style_stats"]))
        content=content_loss(feats[-1],target["content_loss_target"])
        total=style+1000*content
        return total,style,content,output

    @torch.inference_mode()
    def score_pair(self,pre,post,valid=None,trace=None):
        a=self.encode(pre);b=self.encode(post)
        output=self.decoder(self.translator(b[-2],a[-2]))
        translated=self.encoder(output)
        main,untranslated=tensor_feature_scores(a,b,translated,valid,trace)
        if trace is not None:
            trace.update(normalized_patch_pre=self.normalize(pre)[0].cpu().numpy(),
                         normalized_patch_post=self.normalize(post)[0].cpu().numpy(),
                         translated_patch=output[0].cpu().numpy())
            for date,blocks in [('pre',a),('post',b)]:
                for block,features in enumerate(blocks):
                    trace[f'vgg_{date}_block_{block}_channel_mean']=features[0].mean(0).cpu().numpy()
                    trace[f'vgg_{date}_block_{block}_first_channels']=features[0,:4].cpu().numpy()
        # Only the two finished scalar maps leave the GPU (plus opt-in traces).
        return main.cpu().numpy(),untranslated.cpu().numpy()

    @torch.no_grad()
    def score(self,pre,post,translate=True,valid=None,trace=None):
        if translate:
            output=self(pre,post)
            return feature_difference(self.encoder(output),self.encode(post),valid,trace)
        return feature_difference(self.encode(pre),self.encode(post),valid,trace)
