"""Strict data inputs, shared processing policy and per-pair runtime derivation."""
import json
from pathlib import Path
from datetime import datetime
import math

ROOT=Path(__file__).resolve().parent.parent
INPUT_KEYS={'study_id','before','after','bbox','previous_bbox','metadata'}


def load_inputs(path):
    path=Path(path)
    if not path.is_absolute():path=ROOT/path
    data=json.loads(path.read_text())
    unknown=[key for key in data if key not in INPUT_KEYS and not key.startswith('_comment')]
    if unknown:raise ValueError(f'Data input contains processing settings/unknown fields: {unknown}; use the shared pipeline settings file')
    for key in ('study_id','before','after','bbox'):
        if key not in data:raise ValueError(f'Missing data field: {key}')
    identifier=data['study_id']
    if not isinstance(identifier,str) or not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identifier):
        raise ValueError('study_id must be a filename-safe identifier')
    box=data['bbox']
    if len(box)!=4 or not all(math.isfinite(float(x)) for x in box) or not (-180<=box[0]<box[2]<=180 and -90<=box[1]<box[3]<=90):
        raise ValueError('bbox must be ordered WGS84 [west,south,east,north]')
    return data


def resolve_config(input_path,settings_path='configs/pipeline.json',output=None,gunw=None):
    data=load_inputs(input_path)
    settings_path=Path(settings_path)
    if not settings_path.is_absolute():settings_path=ROOT/settings_path
    settings=json.loads(settings_path.read_text())
    if 'third_channel' in settings:raise ValueError('VV experiment removed; use HH/HV and their dB difference')
    if INPUT_KEYS.intersection(settings) or 'output' in settings or 'gunw' in settings:
        raise ValueError('Shared pipeline settings must not contain acquisition or output fields')
    if gunw is not None:
        from nisar.gunw import POLICY
        path=Path(gunw)
        if not path.is_absolute():path=ROOT/path
        if not path.is_file():raise ValueError(f'GUNW file not found: {path}')
        data=dict(data,gunw=str(path.resolve()))
        settings=dict(settings,gunw_support_policy=dict(POLICY))
    out=Path(output) if output else ROOT/'outputs/runs'/(data['study_id']+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if not out.is_absolute():out=ROOT/out
    config=dict(settings,**{key:data[key] for key in ('study_id','before','after','bbox')},output=str(out))
    if gunw is not None:config['gunw']=data['gunw']
    return config,data,settings


def scene_settings(config,meta,shape):
    """Same deterministic geometry rules for every pair; no location-name branches."""
    pixel_size=abs(float(meta['transform'][0]))
    patch=min(int(config['inference_patch']),min(shape)//8*8)
    if patch<32:raise ValueError('Scene is too small: model inference requires at least 32 x 32 pixels')
    # Local physical neighborhood retains comparable ground extent across grids.
    window=max(3,int(round(config.get('pseudo_local_window_m',600)/pixel_size)))
    if window%2==0:window+=1
    return dict(inference_patch=patch,inference_stride=max(8,patch//2),pseudo_local_window=window,
                pixel_area_m2=abs(meta["transform"][0]*meta["transform"][4]-meta["transform"][1]*meta["transform"][3]),
                input_polarizations=meta.get("before",{}).get("channels",["HH","HV"]))
