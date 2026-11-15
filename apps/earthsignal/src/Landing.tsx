import {useContext,useEffect,useRef,useState,type CSSProperties,type PointerEvent as ReactPointerEvent,type ReactNode} from 'react';
import {Activity,ArrowDown,ArrowUpRight,ChevronLeft,ChevronRight,ChevronsDown,Flame,ImageOff,Mountain,Rocket,Snowflake,Sprout} from 'lucide-react';
import {Astronaut} from './Astronaut';
import EarthGlobe,{type GlobeView} from './EarthGlobe';
import Starfield from './Starfield';
import JourneyBar from './JourneyBar';
import {AutopilotContext,Journey,JourneyContext} from './journey/engine';
import {CLOSE_DEPTH} from './journey/path';
import {sky} from './journey/sky';
import {EXPLORER_PATH} from './routes';
import {detected,etna,etnaCloud,flight,nepal,spain,type CaseImage,type CaseStudy} from './cases';
import './landing.css';

const clamp=(v:number,min=0,max=1)=>Math.max(min,Math.min(max,v));
// label: the presenter bar and the rail tooltip · short: the rail's step name.
const chapters=[
  {id:'home',label:'Home',short:'Home'},{id:'about',label:'About',short:'Earth'},{id:'work',label:'Case studies',short:'Cases'},
  {id:'spain',label:'Spain · wildfire',short:'Spain'},{id:'etna',label:'Etna · eruption',short:'Etna'},{id:'nepal',label:'Nepal · flood',short:'Nepal'},
  {id:'flight',label:'Nepal · 3D flight',short:'Flight'},{id:'discover',label:'Discover',short:'Discover'},
];
// Screens of scrolling the camera spends on the drone flight.
const FLIGHT_HOLD=3.6;
const eventIcons={wildfires:Flame,earthquakes:Activity,farming:Sprout,glaciers:Snowflake,volcanoes:Mountain};

function useReducedMotion(){
  const [reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(()=>{
    const media=window.matchMedia('(prefers-reduced-motion: reduce)'),update=()=>setReduced(media.matches);
    media.addEventListener('change',update);return()=>media.removeEventListener('change',update);
  },[]);
  return reduced;
}

// Shown in place of a visualization that is not available yet, so the layout stays intact and the asset is easy to swap in.
function Placeholder({title,asset,source}:{title:string;asset:string;source:string}){
  return <div className="sp-placeholder" role="img" aria-label={`${title}: visualization not available yet`}>
    <ImageOff size={34} aria-hidden="true"/>
    <strong>{title}</strong>
    <span>Visualization pending</span>
    <span>Expected asset: <code>{asset}</code></span>
    <span>Data source: <code>{source}</code></span>
  </div>;
}

// Autopilot demo of a before/after divider, as [seconds, split %] keyframes: hold, sweep right to show more
// of "before", across to show more of "after", and back to the middle, where it stays until the next stop.
// Seconds the autopilot rests on each case block: one full divider sweep plus a moment to read.
const CASE_DWELL=8.5;
const SWEEP:[number,number][]=[[0,50],[.7,50],[2,84],[2.5,84],[4.6,16],[5.1,16],[6.4,50],[7.6,50]];
function sweepAt(seconds:number,from:number){
  const t=Math.min(seconds,SWEEP[SWEEP.length-1][0]),first=seconds<SWEEP[1][0];
  for(let k=1;k<SWEEP.length;k++){
    const [t0,v0]=SWEEP[k-1],[t1,v1]=SWEEP[k];
    if(t<=t1){const u=(t-t0)/(t1-t0),e=u*u*(3-2*u),start=first&&k===1?from:v0;return start+(v1-start)*e;}
  }
  return 50;
}

// Before/after image comparison: drag the divider, or use the labelled range input from the keyboard.
// While the autopilot runs and the comparison is at rest on screen, the divider sweeps on its own.
function Compare({name,before,after,width,height,children}:{name:string;before:CaseImage;after:CaseImage;width:number;height:number;children?:ReactNode}){
  const [split,setSplit]=useState(50),[failed,setFailed]=useState<string[]>([]);
  const frame=useRef<HTMLDivElement>(null),splitRef=useRef(split),autopilot=useContext(AutopilotContext);
  splitRef.current=split;
  useEffect(()=>{
    if(!autopilot)return;
    let raf=0,since=-1,from=50;
    const tick=(now:number)=>{
      raf=requestAnimationFrame(tick);
      const el=frame.current;if(!el){since=-1;return;}
      // Only at rest on screen: drawn at its real size (the camera is not flying), inside the window, and its
      // middle above the bottom bar. Scenes waiting off screen fail the first checks.
      const r=el.getBoundingClientRect(),resting=Math.abs(r.width-el.offsetWidth)<1.5&&r.left>=0&&r.right<=window.innerWidth&&r.top>=40&&r.top+r.height/2<=window.innerHeight-100;
      if(!resting){since=-1;return;}
      if(since<0){since=now;from=splitRef.current;}
      setSplit(sweepAt((now-since)/1000,from));
    };
    raf=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(raf);
  },[autopilot]);
  const move=(e:ReactPointerEvent<HTMLDivElement>)=>{const r=frame.current?.getBoundingClientRect();if(r)setSplit(clamp((e.clientX-r.left)/r.width)*100);};
  const fail=(src:string)=>setFailed(list=>list.includes(src)?list:[...list,src]);
  const missing=[before,after].find(image=>failed.includes(image.src));
  const style={'--split':`${split}%`,'--fit':width/height,aspectRatio:`${width}/${height}`} as CSSProperties;
  if(missing)return <div className="sp-viewer" style={{'--fit':width/height} as CSSProperties}><div className="sp-compare sp-compare-missing" style={style}><Placeholder title={`${name} · ${missing.label}`} asset={missing.src} source={missing.source}/></div></div>;
  return <div className={'sp-viewer'+(width/height<1.1?' sp-viewer-tall':'')} style={{'--fit':width/height} as CSSProperties}>
    <div className={'sp-compare'+(width/height<.8?' sp-compare-narrow':'')} ref={frame} style={style}
      onPointerDown={e=>{if(e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);move(e);}}
      onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))move(e);}}
      onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}>
      <img src={after.src} width={width} height={height} alt={after.alt} loading="lazy" decoding="async" draggable={false} onError={()=>fail(after.src)}/>
      <div className="sp-compare-before"><img src={before.src} width={width} height={height} alt={before.alt} loading="lazy" decoding="async" draggable={false} onError={()=>fail(before.src)}/></div>
      {children}
      <span className="sp-tag sp-tag-before">{before.label}{before.date&&<b>{before.date}</b>}</span>
      <span className="sp-tag sp-tag-after">{after.label}{after.date&&<b>{after.date}</b>}</span>
      <div className="sp-divider" aria-hidden="true"><span><ChevronLeft size={20}/><ChevronRight size={20}/></span></div>
    </div>
    <label className="sp-range"><span>Drag to compare</span>
      <input type="range" min="0" max="100" value={Math.round(split)} onChange={e=>setSplit(Number(e.target.value))}
        aria-label={`${name}: compare ${before.label} and ${after.label}`} aria-valuetext={`${Math.round(split)}% ${before.label}, ${Math.round(100-split)}% ${after.label}`}/>
    </label>
  </div>;
}

// The prototype's instrument frame around a visualization: a header line with a live status, the visual, and a
// caption with its data source.
function Panel({code,label,status,caption,note,tag,children}:{code:string;label:string;status:string;caption:string;note?:string;tag:string;children:ReactNode}){
  return <div className="sp-panel">
    <div className="sp-panel-top"><span>{code} / {label}</span><span className="sp-status">{status}</span></div>
    {children}
    <div className="sp-panel-foot"><div><strong>{caption}</strong>{note&&<small>{note}</small>}</div><span className="sp-data-tag">{tag}</span></div>
  </div>;
}

function CaseViewer({study}:{study:CaseStudy}){
  const [on,setOn]=useState(()=>study.layers.filter(layer=>layer.on).map(layer=>layer.id)),[missing,setMissing]=useState<string[]>([]);
  return <Panel code={study.look.code} label={study.look.panel} status={study.look.status} caption={study.look.caption} note={study.notes.filter(note=>!note.startsWith('Passes')).join(' ')} tag="NISAR data"><div className="sp-case-visual">
    <Compare name={study.title} before={study.before} after={study.after} width={study.width} height={study.height}>
      {study.layers.filter(layer=>on.includes(layer.id)&&!missing.includes(layer.id)).map(layer=>
        <img key={layer.id} className="sp-layer" src={layer.src} alt="" draggable={false} onError={()=>setMissing(list=>[...list,layer.id])}/>)}
    </Compare>
    <div className="sp-layers" role="group" aria-label={`${study.title}: detection layers`}>
      {study.layers.map(layer=>{
        const gone=missing.includes(layer.id),active=on.includes(layer.id)&&!gone;
        return <button key={layer.id} type="button" aria-pressed={active} disabled={gone} onClick={()=>setOn(list=>list.includes(layer.id)?list.filter(id=>id!==layer.id):[...list,layer.id])}>
          <i style={{background:layer.color}} aria-hidden="true"/>
          <span><strong>{layer.label}</strong><small>{gone?`Asset pending · ${layer.source}`:layer.hint}</small></span>
          <em>{gone?'N/A':active?'On':'Off'}</em>
        </button>;
      })}
    </div>
  </div></Panel>;
}

// One stop of the camera journey. In motion mode it floats in 3D space; with reduced motion it is a plain block.
// hold/steps/dwell/pace tune how long the camera and the autopilot stay on it (see src/journey/engine.ts).
// close: the scene waits right behind the previous one and the camera pushes straight through to it.
function Scene({id,hold,steps,dwell,pace,close,children}:{id:string;hold?:number;steps?:number[];dwell?:number;pace?:number;close?:boolean;children:ReactNode}){
  return <div id={id} className="sp-scene" data-scene data-hold={hold} data-steps={steps?.join(',')} data-dwell={dwell} data-pace={pace} data-close={close?'':undefined}>{children}</div>;
}

function CaseSection({study,children}:{study:CaseStudy;children?:ReactNode}){
  const {look}=study;
  return <Scene id={study.id} dwell={CASE_DWELL}><section className={`sp-section sp-case sp-case-${study.id} sp-theme-${look.theme}`} aria-labelledby={`${study.id}-title`}>
    <div className="sp-case-grid">
      <div className="sp-case-text sp-reveal">
        <span className="sp-index">Event trace 0{study.index}</span>
        <h2 id={`${study.id}-title`} className="sp-case-title"><span className="sp-case-big">{look.region}<i>.</i></span> <span className="sp-case-sub">{look.sub}</span></h2>
        <p className="sp-case-meta">{study.title} · {study.place} · {study.eventDate}</p>
        <p>{study.summary}</p>
        <dl className="sp-stats">{study.stats.map(stat=><div key={stat.label}><dt>{stat.label}</dt><dd>{stat.value}{stat.unit&&<small>{stat.unit}</small>}</dd></div>)}</dl>
        <ul className="sp-micro"><li>Region / {look.region}</li><li>Type / {study.kind}</li></ul>
      </div>
      <div className="sp-reveal"><CaseViewer study={study}/></div>
    </div>
    {children}
  </section></Scene>;
}

// About: a camera flies around the globe from one event type's site to the next. The planet turns under it, the
// starfield sweeps past (journey/sky.ts), every site stays pinned on the globe, and on arrival the event's card
// grows out of its pin, with the astronaut riding on it. While the scene still waits behind the hero title
// (--arrive below 1) the globe just turns slowly and nothing else shows.
// Seconds for one flight and one stay; five of each make the autopilot's stop on About.
const FLY_MS=1500,STAY_MS=2400;
const toRad=(d:number)=>d*Math.PI/180;
// Unit-sphere position of a site as seen by the camera (x right, y up, z towards the viewer).
function seen(view:GlobeView,lat:number,lon:number){
  const la=toRad(lat),rel=toRad(lon)-view.lon,c=Math.cos(view.lat),sn=Math.sin(view.lat);
  const wx=Math.cos(la)*Math.sin(rel),wy=Math.sin(la),wz=Math.cos(la)*Math.cos(rel);
  return {x:wx,y:c*wy-sn*wz,z:sn*wy+c*wz};
}
function AboutGlobe({paused,reduced}:{paused:boolean;reduced:boolean}){
  const stage=useRef<HTMLDivElement>(null),world=useRef<HTMLDivElement>(null),globe=useRef<HTMLDivElement>(null),pins=useRef<(HTMLButtonElement|null)[]>([]),card=useRef<HTMLDivElement>(null);
  const start=detected[0].place;
  const view=useRef<GlobeView>({lon:toRad(start.lon),lat:toRad(start.lat)});
  const [active,setActive]=useState(0),[shown,setShown]=useState(false);
  const st=useRef({active:0,from:{...view.current},to:{...view.current},t0:0,flying:false,here:false,hover:false,next:0,holdUntil:0,still:false});
  st.current.still=paused||reduced;
  const go=(i:number)=>{
    const s=st.current,p=detected[i].place;let lon=toRad(p.lon);
    while(lon-view.current.lon>Math.PI)lon-=Math.PI*2;while(lon-view.current.lon<-Math.PI)lon+=Math.PI*2;
    s.active=i;s.from={...view.current};s.to={lon,lat:toRad(p.lat)};s.t0=performance.now();s.flying=true;
    setActive(i);setShown(false);
  };
  const pick=(i:number)=>{st.current.holdUntil=performance.now()+15000;go(i);};
  useEffect(()=>{
    const el=stage.current;if(!el)return;
    const scene=el.closest<HTMLElement>('[data-scene]');
    let frame=0,visible=false,last=performance.now();
    const tick=(now:number)=>{
      frame=0;const dt=Math.min(80,now-last);last=now;
      const s=st.current,arrive=parseFloat(scene?.style.getPropertyValue('--arrive')||'1');
      if(arrive<.99){
        // Waiting behind the hero: turn slowly, no card.
        if(s.here){s.here=false;setShown(false);}
        if(!s.flying&&!s.still)view.current={...view.current,lon:view.current.lon+dt*.00011};
      }else if(!s.here){s.here=true;go(s.active);}
      if(s.flying){
        const t=reduced?1:clamp((now-s.t0)/FLY_MS),e=t<.5?4*t*t*t:1-(-2*t+2)**3/2;
        view.current={lon:s.from.lon+(s.to.lon-s.from.lon)*e,lat:s.from.lat+(s.to.lat-s.from.lat)*e};
        // The camera pulls back a little mid-flight, as when orbiting to the far side.
        if(world.current)world.current.style.transform=`scale(${(1-.08*Math.sin(Math.PI*t)).toFixed(4)})`;
        if(t>=1){s.flying=false;s.next=now+STAY_MS;if(s.here)setShown(true);}
      }else if(s.here&&!s.still&&!s.hover&&now>s.next&&now>s.holdUntil)go((s.active+1)%detected.length);
      sky.lon=view.current.lon;sky.lat=view.current.lat;
      // Pins on the globe (hidden on the far side) and the card at the active pin.
      const g=globe.current;
      if(g){
        // The globe box sits at left/top 50% and is pulled back by half its size, so its offset is its centre.
        const R=g.offsetWidth/2*.91,cx=g.offsetLeft,cy=g.offsetTop;
        detected.forEach((ev,i)=>{
          const pin=pins.current[i];if(!pin)return;const p=seen(view.current,ev.place.lat,ev.place.lon),x=cx+p.x*R,y=cy-p.y*R;
          pin.style.transform=`translate(-50%,-50%) translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scale(${(.6+.4*clamp(p.z)).toFixed(3)})`;
          pin.style.opacity=p.z>.05?clamp(p.z*3).toFixed(3):'0';pin.style.visibility=p.z>.05?'visible':'hidden';
          if(i===s.active&&card.current){card.current.style.left=`${x.toFixed(1)}px`;card.current.style.top=`${y.toFixed(1)}px`;}
        });
      }
      if(visible)frame=requestAnimationFrame(tick);
    };
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible&&!frame){last=performance.now();frame=requestAnimationFrame(tick);}},{rootMargin:'20% 0px'});
    observer.observe(el);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  const ev=detected[active],Icon=eventIcons[ev.id];
  return <div className="sp-orbit-wrap sp-reveal">
    <div className="sp-orbit" ref={stage} onPointerEnter={()=>{st.current.hover=true;}} onPointerLeave={()=>{st.current.hover=false;}}>
      <div className="sp-ag-world" ref={world}>
        {/* Radar orbits around the globe, drawn twice: the far half behind the planet, the near half in front. */}
        <div className="sp-globe-rings sp-globe-rings-back" aria-hidden="true"><i/><i/></div>
        <div className="sp-orbit-globe" ref={globe}><EarthGlobe paused={paused||reduced} view={view}/></div>
        <div className="sp-globe-rings sp-globe-rings-front" aria-hidden="true"><i/><i/></div>
        <div className="sp-orbit-events" role="group" aria-label="Events EarthSignal detects, by example site">
          {detected.map((e,i)=>{const PinIcon=eventIcons[e.id];return <button key={e.id} type="button" ref={n=>{pins.current[i]=n;}} className="sp-ag-pin" aria-pressed={active===i} style={{'--event':e.color} as CSSProperties}
            aria-label={`${e.label}, ${e.place.name}`} onClick={()=>pick(i)}><PinIcon size={15} aria-hidden="true"/></button>;})}
        </div>
        <div className={'sp-ag-card'+(shown?' shown':'')} ref={card} style={{'--event':ev.color} as CSSProperties} aria-live="polite">
          <div className="sp-ag-astronaut" aria-hidden="true"><Astronaut/></div>
          <div className="sp-ag-pic">{ev.picture?<img src={ev.picture.src} alt={ev.picture.caption} draggable={false}/>:<div className="sp-ag-pic-empty"><ImageOff size={22} aria-hidden="true"/><span>Photo to add</span></div>}</div>
          <div className="sp-ag-body">
            <h3><i><Icon size={17} aria-hidden="true"/></i>{ev.label}</h3>
            <p>{ev.text}</p>
            <span className="sp-ag-place">{ev.place.example?'Example region':'Case study'} · {ev.place.name}</span>
            {ev.target?<a className="sp-link" href={`#${ev.target}`}>{ev.cta} <ArrowDown size={18} aria-hidden="true"/></a>:<span className="sp-soon">{ev.cta}</span>}
          </div>
        </div>
      </div>
    </div>
    <div className="sp-ag-dots" role="group" aria-label="Choose an event type">{detected.map((e,i)=><button key={e.id} type="button" aria-label={e.label} aria-pressed={i===active} style={{'--event':e.color} as CSSProperties} onClick={()=>pick(i)}/>)}</div>
  </div>;
}

// Fly-through along the detected flood trace, rendered ahead of time so it works offline. The camera rests on
// this scene for several screens of scrolling, and that hold progress picks the frame.
function Flight({reduced,near}:{reduced:boolean;near:boolean}){
  const journey=useContext(JourneyContext);
  const canvas=useRef<HTMLCanvasElement>(null),startLoad=useRef<()=>void>(()=>{}),nearRef=useRef(near);
  const [progress,setProgress]=useState(0),[loaded,setLoaded]=useState(0),[failed,setFailed]=useState(false);
  nearRef.current=near;
  useEffect(()=>{if(near)startLoad.current();},[near]);
  useEffect(()=>{
    const cv=canvas.current,ctx=cv?.getContext('2d');
    if(reduced||!journey||!cv||!ctx)return;
    const images:(HTMLImageElement|undefined)[]=new Array(flight.count);
    let drawn=-1,started=false,disposed=false,p=0;
    const nearest=(i:number)=>{for(let d=0;d<flight.count;d++){if(images[i-d])return i-d;if(images[i+d])return i+d;}return -1;};
    function render(){
      const i=nearest(Math.round(p*(flight.count-1)));
      if(i<0||i===drawn)return;
      const img=images[i]!,scale=Math.max(cv!.width/img.width,cv!.height/img.height),w=img.width*scale,h=img.height*scale;
      ctx!.drawImage(img,(cv!.width-w)/2,(cv!.height-h)/2,w,h);drawn=i;
    }
    const resize=()=>{const dpr=Math.min(window.devicePixelRatio||1,1.5);cv.width=Math.round(cv.clientWidth*dpr);cv.height=Math.round(cv.clientHeight*dpr);drawn=-1;render();};
    startLoad.current=()=>{
      if(started)return;started=true;
      // A coarse pass first, so scrubbing works before every frame has arrived.
      const order=[...Array(flight.count).keys()].sort((a,b)=>Number(a%6!==0)-Number(b%6!==0)||a-b);
      let next=0,busy=0;
      const pump=()=>{
        while(!disposed&&busy<6&&next<order.length){
          const i=order[next++],img=new Image();busy++;
          img.onload=()=>{busy--;images[i]=img;setLoaded(n=>n+1);render();pump();};
          img.onerror=()=>{busy--;if(i===0)setFailed(true);pump();};
          img.src=flight.frame(i);
        }
      };
      pump();
    };
    if(nearRef.current)startLoad.current();
    const off=journey.subscribe(frame=>{
      const next=frame.hold.flight??0;if(next===p)return;
      p=next;setProgress(prev=>Math.abs(prev-p)>.003||p===0||p===1?p:prev);render();
    });
    const observer=new ResizeObserver(resize);observer.observe(cv);
    return()=>{disposed=true;off();observer.disconnect();startLoad.current=()=>{};};
  },[reduced,journey]);
  const beatIndex=flight.beats.reduce((found,beat,i)=>progress>=beat.from?i:found,0),beat=flight.beats[beatIndex];
  const credit=<p className="sp-flight-credit">Imagery: Esri World Imagery · Terrain: AWS Terrain Tiles · Overlay: EarthSignal model on NISAR data</p>;
  const legend=<div className="sp-flight-legend"><span><i style={{background:'#ff1459'}}/>Confirmed by both methods</span><span><i style={{background:'#ffb826'}}/>One method only</span></div>;
  if(reduced)return <Scene id="flight"><section className="sp-section sp-flight-static" aria-labelledby="flight-title">
    <header className="sp-heading"><span className="sp-index">Flight path / Rasuwa, Nepal</span><h2 id="flight-title">Follow the flood, from its origin to Syabrubesi</h2></header>
    <div className="sp-stills">{flight.beats.map(beat=>Math.round(beat.at*(flight.count-1))).map((index,i)=><figure key={index}><img src={flight.frame(index)} width={flight.width} height={flight.height} loading="lazy" alt={`3D view of the flood trace: ${flight.beats[i].stop}`}/><figcaption><strong>{flight.beats[i].stop}</strong>{flight.beats[i].text}</figcaption></figure>)}</div>
    {legend}{credit}
  </section></Scene>;
  return <Scene id="flight" hold={FLIGHT_HOLD} steps={flight.beats.slice(1).map(beat=>beat.at)} dwell={1.5} pace={.4}><section className="sp-flight" aria-labelledby="flight-title">
    <div className="sp-flight-stage">
      <div className="sp-flight-window">
        <canvas ref={canvas} role="img" aria-label="Drone-style flight over a 3D map of the Bhote Koshi valley, following the detected flood trace from its origin to Syabrubesi"/>
        {failed&&<Placeholder title="Nepal · 3D flight along the flood trace" asset={flight.frame(0)} source={flight.source}/>}
        {!failed&&loaded<10&&<div className="sp-flight-loading" role="status">Loading flight… {Math.round(loaded/flight.count*100)}%</div>}
      </div>
      <div className="sp-flight-top sp-frame"><span className="sp-index">Flight path / Rasuwa, Nepal</span><h2 id="flight-title">Follow the flood, from its origin to Syabrubesi</h2></div>
      <div className="sp-flight-bottom">
        <div className="sp-flight-caption sp-frame" aria-live="polite"><strong>{beat.stop}</strong><p>{beat.text}</p></div>
        <div className="sp-flight-route sp-frame">
          <div className="sp-route-bar" aria-hidden="true"><i style={{width:`${progress*100}%`}}/>{flight.beats.map((stop,i)=><span key={stop.stop} className={progress>=stop.at-.002?'passed':''} style={{left:`${stop.at*100}%`}}><b/>{stop.stop}</span>)}</div>
          <div className="sp-route-meta"><strong>{(progress*flight.km).toFixed(1)} <small>/ {flight.km} km</small></strong>{legend}</div>
        </div>
      </div>
      {credit}
    </div>
  </section></Scene>;
}

export default function Landing(){
  const reduced=useReducedMotion();
  const [paused,setPaused]=useState(false),[chapter,setChapter]=useState('home');
  const [journey,setJourney]=useState<Journey|null>(null),[autopilot,setAutopilot]=useState(false);
  const root=useRef<HTMLDivElement>(null),world=useRef<HTMLElement>(null),spacer=useRef<HTMLDivElement>(null);
  useEffect(()=>{document.title='EarthSignal — Dancing with the SARs';},[]);
  // Motion mode: one camera flies through scenes placed in 3D space.
  useEffect(()=>{
    if(reduced||!root.current||!world.current||!spacer.current)return;
    const engine=new Journey(root.current,world.current,spacer.current,{onChapter:id=>setChapter(id),onAutopilot:setAutopilot});
    setJourney(engine);
    return()=>{engine.destroy();setJourney(null);setAutopilot(false);};
  },[reduced]);
  // The About globe shows through behind the hero title. Measure where it lands on the start screen (its centre and
  // radius, seen from the hero, i.e. scaled by the extra distance) so the hero can centre its title on it and
  // put the lead and button below it.
  useEffect(()=>{
    if(reduced)return;
    const hero=document.getElementById('home'),about=document.getElementById('about'),globe=about?.querySelector<HTMLElement>('.sp-orbit-globe'),title=hero?.querySelector<HTMLElement>('.sp-title');
    if(!hero||!about||!globe||!title)return;
    const seen=1/(1+CLOSE_DEPTH);
    const update=()=>{
      let y=0,node:HTMLElement|null=globe;
      while(node&&node!==about){y+=node.offsetTop;node=node.offsetParent as HTMLElement|null;}
      // The globe box is placed at top:50% and pulled up by half its height, so its offsetTop is its centre.
      const h=window.innerHeight,radius=globe.offsetHeight/2*.91*seen;
      // Behind the title the globe should be about as tall as the two title lines. Where it would look smaller,
      // About enlarges it while it waits (--globe-boost) and lets the enlargement go as the camera approaches;
      // capped so the globe still only grows on the way in.
      const lines=2*.94*parseFloat(getComputedStyle(title).fontSize),boost=Math.min(1.45,Math.max(1,lines*1.05/(2*radius||1)));
      about.style.setProperty('--globe-boost',boost.toFixed(3));
      hero.style.setProperty('--globe-y',`${(h/2+(y-h/2)*seen).toFixed(1)}px`);
      hero.style.setProperty('--globe-r',`${(radius*boost).toFixed(1)}px`);
    };
    const observer=new ResizeObserver(update);observer.observe(about);observer.observe(globe);observer.observe(title);
    update();
    return()=>{observer.disconnect();hero.style.removeProperty('--globe-y');hero.style.removeProperty('--globe-r');about.style.removeProperty('--globe-boost');};
  },[reduced]);
  // Reduced motion: an ordinary scrolling page with gentle reveals.
  useEffect(()=>{
    if(!reduced)return;
    let frame=0;
    const update=()=>{
      frame=0;
      const line=window.innerHeight*.45;let current='home';
      for(const item of chapters){const el=document.getElementById(item.id);if(el&&el.getBoundingClientRect().top<=line)current=item.id;}
      setChapter(current);
    };
    const schedule=()=>{if(!frame)frame=requestAnimationFrame(update);};
    const anchor=requestAnimationFrame(()=>{const hash=window.location.hash.slice(1);if(hash)document.getElementById(hash)?.scrollIntoView({behavior:'instant',block:'start'});schedule();});
    window.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);
    return()=>{cancelAnimationFrame(frame);cancelAnimationFrame(anchor);window.removeEventListener('scroll',schedule);window.removeEventListener('resize',schedule);};
  },[reduced]);
  const still=paused||reduced;
  const chapterIndex=chapters.findIndex(item=>item.id===chapter);
  return <JourneyContext.Provider value={journey}><AutopilotContext.Provider value={autopilot}><div className={'landing'+(reduced?' sp-flow':' sp-engine')+(still?' sp-paused':'')} ref={root}>
    <div className="sp-space" aria-hidden="true"/>
    <Starfield paused={paused} journey={journey}/>
    {/* Prototype HUD: a soft vignette, faint scanlines and a thin frame with corner brackets around the screen. */}
    <div className="sp-vignette" aria-hidden="true"/><div className="sp-scanlines" aria-hidden="true"/><div className="sp-corner" aria-hidden="true"/>
    <a className="sp-skip" href="#about">Skip to the journey</a>
    <header className="sp-nav">
      <a className="sp-brand" href="#home" aria-label="EarthSignal, back to the start"><span className="sp-logo" aria-hidden="true"/><span><b>EarthSignal</b><small>Dancing with the SARs</small></span></a>
      <div className="sp-nav-actions">
        <span className="sp-signal" aria-hidden="true"><i/>NISAR</span>
        <a className="sp-small-button" href={EXPLORER_PATH}><span className="sp-hide-sm">Open</span> Dashboard <ArrowUpRight size={16} aria-hidden="true"/></a>
      </div>
    </header>
    <nav className="sp-rail" aria-label="Journey chapters">
      {chapters.map((item,i)=><a key={item.id} href={`#${item.id}`} aria-current={chapter===item.id?'step':undefined} aria-label={item.label}><i/><b>{String(i+1).padStart(2,'0')}</b><span>{item.short}</span></a>)}
    </nav>

    <main className="sp-world" ref={world}>
      <Scene id="home" dwell={3}><section className="sp-hero" aria-labelledby="hero-title">
        <div className="sp-hero-inner">
          <p className="sp-kicker"><i/>NASA Space Apps Challenge 2026 · EarthSignal</p>
          <h1 id="hero-title" className="sp-title"><span className="sp-title-line">Dancing with</span> <span className="sp-title-line sp-title-accent">the SARs</span></h1>
          <div className="sp-hero-foot">
            <p className="sp-lead">Follow a changing planet with NISAR radar, through cloud, smoke and darkness.</p>
            <a className="sp-button" href="#about">Start the journey <ArrowDown size={20} aria-hidden="true"/></a>
          </div>
        </div>
        <a className="sp-scroll-cue" href="#about"><span>Scroll to travel</span><ChevronsDown size={22} aria-hidden="true"/></a>
      </section></Scene>

      {/* About waits right behind the hero title: from the start screen only its turning globe and orbits show;
          the camera flies through the title, the globe grows to full size and the details fill in on arrival. */}
      <Scene id="about" close dwell={detected.length*(FLY_MS+STAY_MS)/1000}><section className="sp-section sp-about" aria-labelledby="about-title">
        <header className="sp-heading sp-reveal">
          <span className="sp-index">01 / About</span>
          <h2 id="about-title">One radar. Five kinds of change.</h2>
        </header>
        <AboutGlobe paused={paused} reduced={reduced}/>
      </section></Scene>

      <Scene id="work"><section className="sp-section sp-work" aria-labelledby="work-title">
        <header className="sp-heading sp-reveal">
          <span className="sp-index">02 / Case studies</span>
          <h2 id="work-title">Three events, seen by radar.</h2>
          <p>Each case compares two NISAR passes, one before the event and one after, and shows where our model detected change.</p>
        </header>
        <div className="sp-case-links sp-reveal">
          {[spain,etna,nepal].map(study=><a key={study.id} className="sp-frame" href={`#${study.id}`}>
            <span className="sp-index">Case {study.index}</span><strong>{study.title}</strong><span>{study.kind} · {study.place}</span><ArrowDown size={22} aria-hidden="true"/>
          </a>)}
        </div>
        <p className="sp-disclaimer sp-reveal">The colour images are radar composites, not natural-colour photographs. Coloured areas are detections by our model, not validated damage maps.</p>
      </section></Scene>

      <CaseSection study={spain}/>

      <CaseSection study={etna}>
        <div className="sp-cloud sp-reveal" data-stop>
          <div className="sp-cloud-text">
            <span className="sp-index">Why radar</span>
            <h3>Clouds hide the summit. Radar sees through.</h3>
            <p>An optical satellite sees a white cloud cap over Etna. Radar passes through cloud, so NISAR still maps the summit and the lava fields beneath it.</p>
          </div>
          <Panel code="IT" label="Optical vs radar" status="Through cloud" caption="Etna under a cloud cap" note="Left: Sentinel-2 optical image. Right: NISAR radar." tag="Sentinel-2 · NISAR">
            <Compare name="Etna under cloud" before={etnaCloud.before} after={etnaCloud.after} width={etnaCloud.width} height={etnaCloud.height}/>
          </Panel>
        </div>
      </CaseSection>

      <CaseSection study={nepal}/>

      <Flight reduced={reduced} near={chapterIndex>=chapters.findIndex(item=>item.id==='etna')}/>

      <Scene id="discover" dwell={4}>
        <section className="sp-cta" aria-labelledby="discover-title">
          <div className="sp-reveal">
            <span className="sp-index">04 / Your turn</span>
            <h2 id="discover-title" className="sp-title"><span className="sp-title-line">Discover more</span> <span className="sp-title-line sp-title-accent">yourself</span></h2>
            <p className="sp-lead">Open the EarthSignal dashboard to explore the event map, filter the catalog and ask Orbit, our guide.</p>
            <a className="sp-button sp-button-large" href={EXPLORER_PATH}>Open the dashboard <Rocket size={24} aria-hidden="true"/></a>
          </div>
        </section>
        <footer className="sp-footer">
          <p><strong>EarthSignal</strong> · Built for the NASA International Space Apps Challenge 2026, “Dancing with the SARs”. An independent team project, not an official NASA or ISRO service.</p>
          <p>Data and imagery: NISAR L2 GCOV/GUNW (NASA/ISRO, ASF DAAC) · Sentinel-2 (Copernicus/ESA) · Blue Marble (NASA Earth Observatory) · Esri World Imagery · AWS Terrain Tiles.</p>
        </footer>
      </Scene>
    </main>
    <JourneyBar chapters={chapters} chapter={chapter} autopilot={autopilot} paused={paused} onPause={reduced?undefined:()=>setPaused(!paused)}/>
    <div className="sp-spacer" ref={spacer} aria-hidden="true"/>
  </div></AutopilotContext.Provider></JourneyContext.Provider>;
}
