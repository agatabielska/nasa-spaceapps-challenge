import {useContext,useEffect,useRef,useState,type CSSProperties,type PointerEvent as ReactPointerEvent,type ReactNode} from 'react';
import {Activity,ArrowDown,ArrowUpRight,ChevronLeft,ChevronRight,ChevronsDown,Flame,ImageOff,Menu,Mountain,Pause,Play,Rocket,Snowflake,Sprout,X} from 'lucide-react';
import {Astronaut} from './Astronaut';
import EarthGlobe from './EarthGlobe';
import Starfield from './Starfield';
import {Journey,JourneyContext} from './journey/engine';
import {EXPLORER_PATH} from './routes';
import {detected,etna,etnaCloud,flight,nepal,spain,type CaseImage,type CaseStudy} from './cases';
import './landing.css';

const clamp=(v:number,min=0,max=1)=>Math.max(min,Math.min(max,v));
const chapters=[
  {id:'home',label:'Home',nav:'home'},{id:'about',label:'About',nav:'about'},{id:'work',label:'Case studies',nav:'work'},
  {id:'spain',label:'Spain · wildfire',nav:'work'},{id:'etna',label:'Etna · eruption',nav:'work'},{id:'nepal',label:'Nepal · flood',nav:'work'},
  {id:'flight',label:'Nepal · 3D flight',nav:'work'},{id:'discover',label:'Discover',nav:'discover'},
];
const navLinks=[{id:'home',label:'Home'},{id:'about',label:'About'},{id:'work',label:'Work'},{id:'discover',label:'Discover'}];
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

// Before/after image comparison: drag the divider, or use the labelled range input from the keyboard.
function Compare({name,before,after,width,height,children}:{name:string;before:CaseImage;after:CaseImage;width:number;height:number;children?:ReactNode}){
  const [split,setSplit]=useState(50),[failed,setFailed]=useState<string[]>([]);
  const frame=useRef<HTMLDivElement>(null);
  const move=(e:ReactPointerEvent<HTMLDivElement>)=>{const r=frame.current?.getBoundingClientRect();if(r)setSplit(clamp((e.clientX-r.left)/r.width)*100);};
  const fail=(src:string)=>setFailed(list=>list.includes(src)?list:[...list,src]);
  const missing=[before,after].find(image=>failed.includes(image.src));
  const style={'--split':`${split}%`,'--fit':width/height,aspectRatio:`${width}/${height}`} as CSSProperties;
  if(missing)return <div className="sp-viewer" style={{'--fit':width/height} as CSSProperties}><div className="sp-compare sp-compare-missing" style={style}><Placeholder title={`${name} · ${missing.label}`} asset={missing.src} source={missing.source}/></div></div>;
  return <div className="sp-viewer" style={{'--fit':width/height} as CSSProperties}>
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

function CaseViewer({study}:{study:CaseStudy}){
  const [on,setOn]=useState(()=>study.layers.filter(layer=>layer.on).map(layer=>layer.id)),[missing,setMissing]=useState<string[]>([]);
  return <div className="sp-case-visual">
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
  </div>;
}

// One stop of the camera journey. In motion mode it floats in 3D space; with reduced motion it is a plain block.
function Scene({id,hold,children}:{id:string;hold?:number;children:ReactNode}){
  return <div id={id} className="sp-scene" data-scene data-hold={hold}>{children}</div>;
}

function CaseSection({study,children}:{study:CaseStudy;children?:ReactNode}){
  return <Scene id={study.id}><section className={`sp-section sp-case sp-case-${study.id}`} aria-labelledby={`${study.id}-title`}>
    <div className="sp-case-grid">
      <div className="sp-case-text sp-reveal">
        <span className="sp-index">Case {study.index} / {study.kind}</span>
        <h2 id={`${study.id}-title`}>{study.title}</h2>
        <p className="sp-case-meta">{study.place} · {study.eventDate}</p>
        <p>{study.summary}</p>
        <dl className="sp-stats">{study.stats.map(stat=><div key={stat.label}><dt>{stat.label}</dt><dd>{stat.value}{stat.unit&&<small>{stat.unit}</small>}</dd></div>)}</dl>
        <ul className="sp-notes">{study.notes.map(note=><li key={note}>{note}</li>)}</ul>
      </div>
      <div className="sp-reveal"><CaseViewer study={study}/></div>
    </div>
    {children}
  </section></Scene>;
}

// The detected event types orbit the globe; Orbit the astronaut drifts from one to the next.
function OrbitStage({paused,reduced}:{paused:boolean;reduced:boolean}){
  const stage=useRef<HTMLDivElement>(null),chips=useRef<(HTMLButtonElement|null)[]>([]),astronaut=useRef<HTMLDivElement>(null);
  const [active,setActive]=useState(0);
  const state=useRef({active:0,still:false,hover:false,holdUntil:0});
  state.current.active=active;state.current.still=paused||reduced;
  useEffect(()=>{
    const el=stage.current;if(!el)return;
    let frame=0,visible=false,last=performance.now(),angle=-Math.PI/2,ax=NaN,ay=NaN,nextSwitch=last+5200;
    const step=Math.PI*2/detected.length;
    function tick(now:number){
      frame=0;
      const dt=Math.min(80,now-last);last=now;
      const s=state.current,w=el!.clientWidth,h=el!.clientHeight,compact=w<760;
      const rx=w/2-(compact?30:122),ry=h/2-(compact?30:38);
      el!.style.setProperty('--rx',`${rx}px`);el!.style.setProperty('--ry',`${ry}px`);
      if(!s.still&&!s.hover)angle+=dt*Math.PI*2/80000;
      if(!s.still&&now>nextSwitch&&now>s.holdUntil){nextSwitch=now+5200;setActive(i=>(i+1)%detected.length);}
      chips.current.forEach((chip,i)=>{
        if(!chip)return;
        const a=angle+i*step,depth=(Math.sin(a)+1)/2;
        chip.style.transform=`translate(-50%,-50%) translate(${(Math.cos(a)*rx).toFixed(1)}px,${(Math.sin(a)*ry).toFixed(1)}px) scale(${(.86+.14*depth).toFixed(3)})`;
        chip.style.zIndex=depth>.5?'3':'1';
      });
      const a=angle+s.active*step,bx=Math.cos(a)*rx,by=Math.sin(a)*ry;
      const tx=bx+(compact?0:(bx>0?-1:1)*46),ty=by-(compact?58:80);
      if(Number.isNaN(ax)||s.still){ax=tx;ay=ty;}
      else{const k=1-Math.exp(-dt*.0026);ax+=(tx-ax)*k;ay+=(ty-ay)*k;}
      const tilt=s.still?0:clamp((tx-ax)*.14,-20,20)+Math.sin(now/1300)*4;
      if(astronaut.current)astronaut.current.style.transform=`translate(-50%,-50%) translate(${ax.toFixed(1)}px,${ay.toFixed(1)}px) rotate(${tilt.toFixed(2)}deg)`;
      if(visible)frame=requestAnimationFrame(tick);
    }
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible&&!frame){last=performance.now();frame=requestAnimationFrame(tick);}},{rootMargin:'20% 0px'});
    observer.observe(el);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  const pick=(i:number)=>{state.current.holdUntil=performance.now()+15000;setActive(i);};
  const current=detected[active],CurrentIcon=eventIcons[current.id];
  return <div className="sp-orbit-wrap sp-reveal">
    <div className="sp-orbit" ref={stage} onPointerEnter={()=>{state.current.hover=true;}} onPointerLeave={()=>{state.current.hover=false;}}>
      <div className="sp-orbit-ring" aria-hidden="true"/>
      <div className="sp-orbit-globe"><EarthGlobe paused={paused||reduced}/></div>
      <div className="sp-orbit-events" role="group" aria-label="Events EarthSignal detects">
        {detected.map((event,i)=>{const Icon=eventIcons[event.id];return <button key={event.id} type="button" ref={node=>{chips.current[i]=node;}} className="sp-chip" aria-pressed={active===i}
          aria-label={event.label} onClick={()=>pick(i)} onFocus={()=>pick(i)}><i><Icon size={20} aria-hidden="true"/></i><span>{event.label}</span></button>;})}
      </div>
      <div className="sp-orbit-astronaut" ref={astronaut} aria-hidden="true"><Astronaut/></div>
    </div>
    <div className="sp-orbit-panel sp-frame" aria-live="polite">
      <i><CurrentIcon size={26} aria-hidden="true"/></i>
      <div><span className="sp-orbit-count">Orbit points to {active+1} of {detected.length}</span><h3>{current.label}</h3><p>{current.text}</p></div>
      {current.target?<a className="sp-link" href={`#${current.target}`}>{current.cta} <ArrowDown size={18} aria-hidden="true"/></a>:<span className="sp-soon">{current.cta}</span>}
    </div>
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
    <div className="sp-stills">{[0,44,80,131].map((index,i)=><figure key={index}><img src={flight.frame(index)} width={flight.width} height={flight.height} loading="lazy" alt={`3D view of the flood trace: ${flight.beats[i].stop}`}/><figcaption><strong>{flight.beats[i].stop}</strong>{flight.beats[i].text}</figcaption></figure>)}</div>
    {legend}{credit}
  </section></Scene>;
  return <Scene id="flight" hold={FLIGHT_HOLD}><section className="sp-flight" aria-labelledby="flight-title">
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
          <div className="sp-route-bar" aria-hidden="true"><i style={{width:`${progress*100}%`}}/>{flight.beats.map((stop,i)=><span key={stop.stop} className={i<=beatIndex?'passed':''} style={{left:`${stop.at*100}%`}}><b/>{stop.stop}</span>)}</div>
          <div className="sp-route-meta"><strong>{(progress*flight.km).toFixed(1)} <small>/ {flight.km} km</small></strong>{legend}</div>
        </div>
      </div>
      {credit}
    </div>
  </section></Scene>;
}

export default function Landing(){
  const reduced=useReducedMotion();
  const [paused,setPaused]=useState(false),[menu,setMenu]=useState(false),[chapter,setChapter]=useState('home');
  const [journey,setJourney]=useState<Journey|null>(null);
  const root=useRef<HTMLDivElement>(null),world=useRef<HTMLElement>(null),spacer=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    document.title='EarthSignal — Dancing with the SARs';
    const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setMenu(false);};
    window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);
  },[]);
  // Motion mode: one camera flies through scenes placed in 3D space.
  useEffect(()=>{
    if(reduced||!root.current||!world.current||!spacer.current)return;
    const engine=new Journey(root.current,world.current,spacer.current,id=>setChapter(id));
    setJourney(engine);
    return()=>{engine.destroy();setJourney(null);};
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
  const still=paused||reduced,activeNav=chapters.find(item=>item.id===chapter)?.nav;
  const chapterIndex=chapters.findIndex(item=>item.id===chapter);
  return <JourneyContext.Provider value={journey}><div className={'landing'+(reduced?' sp-flow':' sp-engine')+(still?' sp-paused':'')} ref={root}>
    <div className="sp-space" aria-hidden="true"/>
    <Starfield paused={paused} journey={journey}/>
    <a className="sp-skip" href="#about">Skip to the journey</a>
    <header className="sp-nav">
      <a className="sp-brand" href="#home" aria-label="EarthSignal, back to the top">earth<span>signal</span></a>
      <nav aria-label="Journey" className={menu?'sp-nav-links open':'sp-nav-links'}>
        {navLinks.map(link=><a key={link.id} href={`#${link.id}`} aria-current={activeNav===link.id?'location':undefined} onClick={()=>setMenu(false)}>{link.label}</a>)}
      </nav>
      <div className="sp-nav-actions">
        {!reduced&&<button type="button" className="sp-motion" onClick={()=>setPaused(!paused)} aria-pressed={paused} aria-label={paused?'Play background motion':'Pause background motion'}>{paused?<Play size={16} aria-hidden="true"/>:<Pause size={16} aria-hidden="true"/>}<span>{paused?'Play motion':'Pause motion'}</span></button>}
        <a className="sp-button sp-button-small" href={EXPLORER_PATH} aria-label="Open dashboard"><span className="sp-wide">Open dashboard</span><span className="sp-narrow">Dashboard</span><ArrowUpRight size={18} aria-hidden="true"/></a>
        <button type="button" className="sp-menu" aria-label={menu?'Close navigation':'Open navigation'} aria-expanded={menu} onClick={()=>setMenu(!menu)}>{menu?<X/>:<Menu/>}</button>
      </div>
    </header>
    <nav className="sp-rail" aria-label="Journey progress">
      {chapters.map(item=><a key={item.id} href={`#${item.id}`} aria-current={chapter===item.id?'step':undefined}><span>{item.label}</span><i/></a>)}
    </nav>

    <main className="sp-world" ref={world}>
      <Scene id="home"><section className="sp-hero" aria-labelledby="hero-title">
        <div className="sp-hero-inner">
          <p className="sp-kicker"><i/>NASA Space Apps Challenge 2026 · EarthSignal</p>
          <h1 id="hero-title" className="sp-title"><span className="sp-title-line">Dancing with</span> <span className="sp-title-line sp-title-accent">the SARs</span></h1>
          <p className="sp-lead">Follow a changing planet with NISAR radar, through cloud, smoke and darkness.</p>
          <a className="sp-button" href="#about">Start the journey <ArrowDown size={20} aria-hidden="true"/></a>
        </div>
        <a className="sp-scroll-cue" href="#about"><span>Scroll to fly</span><ChevronsDown size={22} aria-hidden="true"/></a>
      </section></Scene>

      <Scene id="about"><section className="sp-section sp-about" aria-labelledby="about-title">
        <header className="sp-heading sp-reveal">
          <span className="sp-index">01 / About</span>
          <h2 id="about-title">One radar. Five kinds of change.</h2>
          <p>NISAR, the NASA–ISRO radar satellite, maps Earth’s surface with L- and S-band radar. EarthSignal compares its repeat passes to find what changed on the ground.</p>
        </header>
        <OrbitStage paused={paused} reduced={reduced}/>
        <ul className="sp-facts sp-reveal">
          <li><strong>Day and night</strong><span>Radar brings its own signal, so it needs no sunlight.</span></li>
          <li><strong>Through cloud</strong><span>Radar waves pass through cloud and smoke.</span></li>
          <li><strong>Every 12 days</strong><span>Repeat passes over the same place reveal change.</span></li>
        </ul>
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
        <div className="sp-cloud sp-reveal">
          <div className="sp-cloud-text">
            <span className="sp-index">Why radar</span>
            <h3>Clouds hide the summit. Radar sees through.</h3>
            <p>An optical satellite sees a white cloud cap over Etna. Radar passes through cloud, so NISAR still maps the summit and the lava fields beneath it.</p>
          </div>
          <Compare name="Etna under cloud" before={etnaCloud.before} after={etnaCloud.after} width={etnaCloud.width} height={etnaCloud.height}/>
        </div>
      </CaseSection>

      <CaseSection study={nepal}/>

      <Flight reduced={reduced} near={chapterIndex>=chapters.findIndex(item=>item.id==='etna')}/>

      <Scene id="discover">
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
    <div className="sp-spacer" ref={spacer} aria-hidden="true"/>
  </div></JourneyContext.Provider>;
}
