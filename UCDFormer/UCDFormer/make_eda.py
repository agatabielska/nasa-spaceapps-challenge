"""Per-polarization real-raster EDA with sourced event chronology and shared scales.

--watch processes each authorized shortlist pair as its two downloads complete.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/".deps"))
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"outputs/.matplotlib"))
import h5py
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt,dates as mdates
from scipy import ndimage
from nisar.data import align_pair,POL


CONTEXT={
    "etna":dict(anchor="2026-07-30",end="2026-08-16",status="Documented eruptive phases; not a single disaster onset",
                source="https://ingvvulcani.com/2026/08/22/etna-la-calda-estate-del-2026/",
                note="July 23 precedes selected late-July/August phases, but Etna was already active earlier in July. August 16 captures part of a multi-phase interval, not necessarily its end."),
    "spain_burgohondo":dict(anchor="2026-07-22",status="NASA first fire observations July 22/23; exact ignition time unverified",
                source="https://science.nasa.gov/earth/earth-observatory/destructive-fires-char-western-europe/",
                note="Pair brackets the first NASA observations near Burgohondo. Town-centered AOI is not a verified fire perimeter; post-image may be during continuing fires."),
    "nepal_shyar_khola":dict(anchor="2026-10-11",status="Event date independently documented",
                source="https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-the-day/landslide-triggered-flash-flood-sweeps-through-nepals-himalayan-valleys",
                note="October 11 avalanche/debris-flow/flood cascade. River deposits, snow and terrain can produce different radar signatures."),
    "nepal_rasuwagadhi":dict(anchor="2026-08-26",status="Event date independently documented",
                source="https://sentinel-asia.org/EO/2026/article20260826NP.html",
                note="Box covers a settlement/river corridor, not the verified source failure. Flood changes and terrain artifacts must be distinguished."),
    "mozambique":dict(anchor="2026-01-17",status="NASA-documented pre/during observation dates; flood onset not fixed here",
                source="https://svs.gsfc.nasa.gov/5661",
                note="NASA compares January 5 and January 17. Flooding developed over a longer rainfall interval: January 5 is the comparison image, not proven entirely pre-flood. January 17 is a during-flood acquisition; Beta calibration caveats apply."),
    "hubbard":dict(anchor="2025-12-06",status="Earthquake date independently documented",
                source="https://science.nasa.gov/earth/earth-observatory/landslide-and-avalanche-debris-litter-hubbard-glacier/",
                note="November 26/December 8 bracket the earthquake. Snow, ice motion and terrain can mimic deposit-related backscatter change; Beta data."),
}
CONTEXT["nepal_quad"]=CONTEXT["nepal_shyar_khola"]
CONTEXT["spain_navaluenga_corrected"]=dict(CONTEXT["spain_burgohondo"],
    status="Official CEMS/EFFIS-mapped fire region; late-post acquisition after August 5 reference imagery",
    source="https://mapping.emergency.copernicus.eu/activations/EMSR900/",
    note="Corrected Navaluenga south AOI selected with independently mapped fire geometry, not just the town name. July 2/August 19 use same track/frame/CRID and near-real-time orbit class. The longer interval also includes non-fire seasonal/moisture changes. CEMS August 5 optical-derived burn polygons are contextual references, not exhaustive generic-change labels.")
CONTEXT["mozambique_regional"]=dict(CONTEXT["mozambique"],
    note=CONTEXT["mozambique"]["note"]+" This is a wider geographic context crop; it does not establish the complete flood extent.")


def common_channels(a,b):
    with h5py.File(a) as f,h5py.File(b) as g:
        x=f["science/LSAR/GCOV/grids/frequencyA"]; y=g["science/LSAR/GCOV/grids/frequencyA"]
        return [p for p,key in POL.items() if key in x and key in y]


def date_of(granule):
    for token in granule.split("_"):
        if len(token)==15 and token[8]=="T" and token[:8].isdigit():
            return dt.datetime.strptime(token,"%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
    raise ValueError("Acquisition timestamp absent from NISAR ID")


def process(pair,bbox):
    key=pair["event"]; out=ROOT/"outputs/eda"/key; out.mkdir(parents=True,exist_ok=True)
    a=ROOT/"data/raw"/(pair["before"]+".h5"); b=ROOT/"data/raw"/(pair["after"]+".h5")
    channels=common_channels(a,b)
    pre,post,valid,meta=align_pair(a,b,bbox,channels)
    if valid.sum()<100: raise ValueError("Insufficient common valid pixels in EDA AOI")
    db0=10*np.log10(pre); db1=10*np.log10(post); diff=db1-db0
    before=date_of(pair["before"]); after=date_of(pair["after"])
    context=CONTEXT[key]; anchor=dt.datetime.fromisoformat(context["anchor"]).replace(tzinfo=dt.timezone.utc)
    extent=[meta["transform"][2],meta["transform"][2]+valid.shape[1]*meta["transform"][0],
            meta["transform"][5]+valid.shape[0]*meta["transform"][4],meta["transform"][5]]
    c=len(channels); fig,axes=plt.subplots(c,4,figsize=(19,4.5*c),squeeze=False)
    stats=[]
    for i,p in enumerate(channels):
        values=np.concatenate([db0[i][valid],db1[i][valid]])
        lo,hi=np.percentile(values,[2,98]); limit=max(.1,float(np.percentile(abs(diff[i][valid]),98)))
        columns=[(db0[i],"Before gamma-0 (dB)","gray",lo,hi),(db1[i],"After gamma-0 (dB)","gray",lo,hi),
                 (diff[i],"Signed: after − before (dB)","RdBu_r",-limit,limit),
                 (abs(diff[i]),"Absolute difference (dB)","magma",0,limit)]
        for ax,(data,title,cmap,vmin,vmax) in zip(axes[i],columns):
            image=ax.imshow(np.ma.array(data,mask=~valid),cmap=cmap,vmin=vmin,vmax=vmax,extent=extent)
            ax.set_title(p+" | "+title); ax.set_xlabel("Easting (m)"); ax.set_ylabel("Northing (m)")
            fig.colorbar(image,ax=ax,shrink=.75,label="dB")
        stats.append(dict(polarization=p,shared_display_db=[float(lo),float(hi)],
                          pre_median_db=float(np.median(db0[i][valid])),post_median_db=float(np.median(db1[i][valid])),
                          signed_median_db=float(np.median(diff[i][valid])),
                          absolute_median_db=float(np.median(abs(diff[i][valid]))),
                          absolute_p95_db=float(np.percentile(abs(diff[i][valid]),95))))
    fig.suptitle(f'{key} | {before:%Y-%m-%d %H:%M UTC} → {after:%Y-%m-%d %H:%M UTC}\nShared date scaling per polarization; no histogram matching; {meta["crs"]}',fontsize=14)
    fig.tight_layout(rect=[0,0,1,.95]); fig.savefig(out/"polarization_changes.png",dpi=150); plt.close(fig)
    fig,axes=plt.subplots(c,2,figsize=(12,3.5*c),squeeze=False)
    for i,p in enumerate(channels):
        lo,hi=stats[i]["shared_display_db"]; bins=np.linspace(lo,hi,100)
        axes[i,0].hist(db0[i][valid],bins,density=True,histtype="step",label="Before")
        axes[i,0].hist(db1[i][valid],bins,density=True,histtype="step",label="After")
        axes[i,0].set_title(p+" gamma-0 distributions"); axes[i,0].set_xlabel("dB"); axes[i,0].legend()
        delta=diff[i][valid]; cap=float(np.percentile(abs(delta),99))
        axes[i,1].hist(delta,bins=np.linspace(-max(.1,cap),max(.1,cap),100),density=True)
        axes[i,1].axvline(0,color="black",lw=1); axes[i,1].set_title(p+" signed change distribution"); axes[i,1].set_xlabel("After − before (dB)")
    fig.tight_layout(); fig.savefig(out/"distributions.png",dpi=150); plt.close(fig)
    fig,axes=plt.subplots(1,c,figsize=(5*c,4),squeeze=False)
    for i,p in enumerate(channels):
        support=ndimage.uniform_filter(valid.astype(np.float32),3,mode="constant")
        def filtered(x):
            z=ndimage.uniform_filter(np.where(valid,x,0),3,mode="constant")/np.maximum(support,1e-8)
            return z
        smooth=10*np.log10(np.maximum(filtered(post[i]),1e-20))-10*np.log10(np.maximum(filtered(pre[i]),1e-20))
        good=valid&(support>.999)
        cap=max(.1,float(np.percentile(abs(smooth[good]),98)))
        im=axes[0,i].imshow(np.ma.array(smooth,mask=~good),cmap="RdBu_r",vmin=-cap,vmax=cap,extent=extent)
        axes[0,i].set_title(p+" signed dB change\n3×3 linear-power mean before log")
        fig.colorbar(im,ax=axes[0,i],label="dB")
    fig.tight_layout(); fig.savefig(out/"speckle_sensitivity.png",dpi=150); plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,3))
    ax.plot([before,after],[0,0],"o-",lw=2)
    ax.axvline(anchor,color="firebrick",ls="--",label=context["status"])
    if "end" in context:
        end=dt.datetime.fromisoformat(context["end"]).replace(tzinfo=dt.timezone.utc)
        ax.axvspan(anchor,end,color="orange",alpha=.15,label="Documented multi-phase interval (date precision)")
    ax.annotate(f"Before\n{before:%Y-%m-%d %H:%M UTC}",(before,0),xytext=(0,20),textcoords="offset points",ha="center")
    ax.annotate(f"After\n{after:%Y-%m-%d %H:%M UTC}",(after,0),xytext=(0,20),textcoords="offset points",ha="center")
    ax.set_ylim(-.2,.5); ax.set_yticks([]); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d")); ax.legend(loc="lower center",fontsize=8)
    ax.set_title(key+" — acquisition chronology, event date ≠ inferred mask"); fig.tight_layout(); fig.savefig(out/"timeline.png",dpi=150); plt.close(fig)
    report=dict(event=key,before=before.isoformat(),after=after.isoformat(),event_context=context,
                brackets_anchor_date=before.date()<anchor.date()<after.date(),
                same_day_after=after.date()==anchor.date(),bbox_wgs84=bbox,
                channels=channels,crs=meta["crs"],shape=list(valid.shape),valid_fraction=float(valid.mean()),
                native_grid_reprojection=meta["reprojected_after"],statistics=stats,
                limitations=["Backscatter differences are observations, not verified disaster extent",
                             "Shared display clipping is for visualization, not threshold selection",
                             "Speckle/terrain/geometry/moisture can produce differences"])
    (out/"eda.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=[f'# {key}: before/after NISAR EDA',"",f'Before: **{before:%Y-%m-%d %H:%M:%S UTC}**. After: **{after:%Y-%m-%d %H:%M:%S UTC}**.',"",
           f'Event context: [{context["status"]}]({context["source"]}).',"",context["note"],"",
           f'Proposed bbox `[west,south,east,north]`: `{bbox}`. Common valid pixels: {valid.mean():.2%}. Frequency A; {meta["crs"]}.',"",
           'These are measured polarization-intensity comparisons, not RGB photographs or validated event masks. Each polarization uses exactly the same dB display limits at both dates. Red signed differences mean stronger post-event returns; blue means weaker. Both signs can represent change.',"",
           '![Acquisition timeline](timeline.png)',"",'![Per-polarization comparisons](polarization_changes.png)',"",
           '![Distribution comparisons](distributions.png)',"",'![Sensitivity to small speckle filter](speckle_sensitivity.png)',"",
           'The filtered figure averages 3×3 linear-power neighborhoods before taking logarithms; it is an EDA sensitivity check, not a hidden change to model inputs.',"",
           'Statistics and chronology checks: [eda.json](eda.json). No accuracy metric or calibrated change probability is inferred from these figures.']
    (out/"README.md").write_text("\n".join(lines)+"\n")
    print("EDA_DONE",key,"polarizations",channels,"shape",valid.shape,flush=True)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--watch",action="store_true"); parser.add_argument("--event")
    args=parser.parse_args(); os.chdir(ROOT)
    manifest=json.loads((ROOT/"data/download_manifest.json").read_text())
    candidates=json.loads((ROOT/"planning/nisar_pair_candidates.json").read_text())
    boxes={e["id"]:e["bbox_wgs84"] for e in candidates["events"]}
    boxes["nepal_quad"]=boxes["nepal_shyar_khola"]
    pairs=[p for p in manifest["pairs"] if not args.event or p["event"]==args.event]
    extra=ROOT/"data/extra_eda_pairs.json"
    if extra.exists():
        pairs += [p for p in json.loads(extra.read_text()) if not args.event or p["event"]==args.event]
    deadline=time.monotonic()+10*3600
    while True:
        pending=[]; errors=[]
        for pair in pairs:
            output=ROOT/"outputs/eda"/pair["event"]/"eda.json"
            if output.exists(): continue
            paths=[ROOT/"data/raw"/(pair[r]+".h5") for r in ["before","after"]]
            if not all(p.exists() for p in paths): pending.append(pair["event"]); continue
            try: process(pair,pair["bbox"] if "bbox" in pair else boxes[pair["event"]])
            except Exception as exc:
                errors.append(dict(event=pair["event"],error=type(exc).__name__,message=str(exc)))
                print("EDA_ERROR",pair["event"],type(exc).__name__,str(exc),flush=True)
        index=ROOT/"outputs/eda/README.md"; index.parent.mkdir(parents=True,exist_ok=True)
        completed=sorted(p.parent.name for p in index.parent.glob("*/eda.json"))
        index.write_text("# NISAR before/after EDA\n\n"+"\n".join(
            f'- [{name}]({name}/README.md)' for name in completed)+"\n\n"+"\n".join(
            f'- {p["event"]}: waiting for download or report generation' for p in pairs if p["event"] not in completed)+
            "\n\nOriginal spain_burgohondo is retained as an exploratory town crop; use spain_navaluenga_corrected for the source-backed fire-region comparison.\n")
        (index.parent/"status.json").write_text(json.dumps(dict(pending_downloads=pending,errors=errors),indent=2)+"\n")
        if not args.watch or (not pending and not errors) or time.monotonic()>deadline: break
        time.sleep(30)


if __name__=="__main__": main()
