import {useEffect,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {Activity,ArrowLeft,ArrowRight,Flame,ImageOff,Mountain,Snowflake,Sprout,type LucideIcon} from 'lucide-react';
import {Astronaut} from './Astronaut';
import EarthGlobe,{type GlobeView} from './EarthGlobe';
import {detected} from './cases';
import './about-variants.css';

// TEMPORARY PROTOTYPE (/about-variants): two candidate designs for the landing page's About scene, side by side,
// with the same five event types. Delete this file, about-variants.css and the route once a variant is chosen.

type EventId=(typeof detected)[number]['id'];
const icons:Record<EventId,LucideIcon>={wildfires:Flame,earthquakes:Activity,farming:Sprout,glaciers:Snowflake,volcanoes:Mountain};
// Pictures: radar composites from our case studies where we have one, a labelled placeholder otherwise.
const pictures:Partial<Record<EventId,{src:string;caption:string}>>={
  wildfires:{src:'/media/cases/spain/after.webp',caption:'NISAR radar composite · Ávila, Spain'},
  volcanoes:{src:'/media/cases/etna/after.webp',caption:'NISAR radar composite · Etna, Italy'},
  glaciers:{src:'/media/cases/nepal/after.webp',caption:'NISAR radar composite · Rasuwa, Nepal'},
};
// Where each type sits on the globe in variant 2: our case-study sites, and example regions where we have none.
const places:Record<EventId,{lat:number;lon:number;name:string;example?:boolean}>={
  wildfires:{lat:40.65,lon:-4.7,name:'Ávila, Spain'},
  earthquakes:{lat:38.3,lon:140.9,name:'Japan',example:true},
  farming:{lat:41.9,lon:-93.1,name:'US Midwest',example:true},
  glaciers:{lat:28.2,lon:85.4,name:'Rasuwa, Nepal'},
  volcanoes:{lat:37.75,lon:15,name:'Etna, Italy'},
};
const events=detected.map(e=>({...e,Icon:icons[e.id],picture:pictures[e.id],place:places[e.id]}));
const N=events.length;
type Event=(typeof events)[number];
const ease=(t:number)=>t<.5?4*t*t*t:1-(-2*t+2)**3/2;
const clamp=(v:number,a=0,b=1)=>Math.max(a,Math.min(b,v));
const useReduced=()=>useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches)[0];

function Card({event,compact,children}:{event:Event;compact?:boolean;children?:ReactNode}){
  const {Icon}=event;
  return <article className={'av-card'+(compact?' av-card-compact':'')} style={{'--event':event.color} as CSSProperties}>
    <div className="av-pic">{event.picture?<img src={event.picture.src} alt={event.picture.caption} draggable={false}/>:<div className="av-pic-empty"><ImageOff size={22} aria-hidden="true"/><span>Photo to add</span></div>}</div>
    <div className="av-body">
      <h3><i><Icon size={16} aria-hidden="true"/></i>{event.label}</h3>
      <p>{event.text}</p>
      {children}
    </div>
  </article>;
}

function Controls({active,go}:{active:number;go:(i:number)=>void}){
  return <div className="av-controls">
    <button type="button" aria-label="Previous event" onClick={()=>go((active+N-1)%N)}><ArrowLeft size={16}/></button>
    <div className="av-dots" role="group" aria-label="Events">{events.map((e,i)=><button key={e.id} type="button" aria-label={e.label} aria-pressed={i===active} style={{'--event':e.color} as CSSProperties} onClick={()=>go(i)}/>)}</div>
    <button type="button" aria-label="Next event" onClick={()=>go((active+1)%N)}><ArrowRight size={16}/></button>
  </div>;
}

// Variant 1: the five cards ride an ellipse around the globe. The active card stops in front, its neighbours stand
// at the sides and the two others pass behind the planet. The astronaut first hops onto the next card, then the
// carousel turns that card to the front.
const STEP=Math.PI*2/N,FRONT=Math.PI/2,HOP_MS=550,TURN_MS=900,DWELL_MS=4200;
function Variant1(){
  const reduced=useReduced();
  const stage=useRef<HTMLDivElement>(null),cards=useRef<(HTMLDivElement|null)[]>([]),astro=useRef<HTMLDivElement>(null);
  const [active,setActive]=useState(0);
  const s=useRef({active:0,theta:FRONT,from:FRONT,to:FRONT,t0:0,phase:'idle' as 'idle'|'hop'|'turn',hx:0,hy:0,ax:0,ay:0,hover:false,next:0});
  const go=(i:number)=>{
    const st=s.current;if(i===st.active&&st.phase==='idle')return;
    st.active=i;setActive(i);st.hx=st.ax;st.hy=st.ay;st.t0=performance.now();st.phase=reduced?'turn':'hop';
    if(reduced){st.from=st.theta;st.to=st.theta;}
  };
  useEffect(()=>{
    let frame=0;
    const place=(now:number)=>{
      const el=stage.current;if(!el)return;
      const st=s.current,w=el.clientWidth,h=el.clientHeight,first=cards.current[0];
      const cw=first?.offsetWidth??220,ch=first?.offsetHeight??260;
      const rx=Math.max(80,w/2-cw*.42-14),ry=h*.07,cx=w/2,cy=h*.56;
      const pos=(i:number)=>{const a=st.theta+i*STEP,depth=(Math.sin(a)+1)/2,k=.6+.4*depth;return {x:cx+Math.cos(a)*rx,y:cy+Math.sin(a)*ry,k,depth,front:Math.sin(a)>-.2};};
      // Card top, where the astronaut stands.
      const top=(i:number)=>{const p=pos(i);return {x:p.x,y:p.y-ch*p.k/2+6*p.k};};
      if(st.phase==='hop'){
        const t=clamp((now-st.t0)/HOP_MS),e=ease(t),target=top(st.active);
        st.ax=st.hx+(target.x-st.hx)*e;st.ay=st.hy+(target.y-st.hy)*e-Math.sin(Math.PI*t)*Math.min(90,Math.abs(target.x-st.hx)*.35+30);
        if(t>=1){st.phase='turn';st.t0=now;st.from=st.theta;let to=FRONT-st.active*STEP;while(to-st.theta>Math.PI)to-=Math.PI*2;while(to-st.theta<-Math.PI)to+=Math.PI*2;st.to=to;}
      }else{
        if(st.phase==='turn'){
          const t=reduced?1:clamp((now-st.t0)/TURN_MS);st.theta=st.from+(st.to-st.from)*ease(t);
          if(t>=1){st.phase='idle';st.next=now+DWELL_MS;}
        }
        const p=top(st.active);st.ax=p.x;st.ay=p.y+(reduced?0:Math.sin(now/600)*3);
        if(st.phase==='idle'&&!st.hover&&now>st.next&&!reduced)go((st.active+1)%N);
      }
      cards.current.forEach((card,i)=>{
        if(!card)return;const p=pos(i);
        card.style.transform=`translate(-50%,-50%) translate(${p.x.toFixed(1)}px,${p.y.toFixed(1)}px) scale(${p.k.toFixed(3)})`;
        card.style.zIndex=String(p.front?20+Math.round(p.depth*10):1);
        card.style.opacity=(p.front?.55+.45*p.depth:.28).toFixed(3);
      });
      if(astro.current)astro.current.style.transform=`translate(-50%,-100%) translate(${st.ax.toFixed(1)}px,${st.ay.toFixed(1)}px) rotate(${st.phase==='hop'?-12:Math.sin(now/1300)*4}deg)`;
    };
    const tick=(now:number)=>{place(now);frame=requestAnimationFrame(tick);};
    s.current.next=performance.now()+DWELL_MS;frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
  },[]);
  return <section className="av-panel" aria-labelledby="av1-title">
    <header><span className="av-eyebrow">Variant 1</span><h2 id="av1-title">Cards on the orbit</h2><p>The event types circle the globe; the astronaut hops onto the next card, then it turns to the front.</p></header>
    <div className="av-stage av1" ref={stage} onPointerEnter={()=>{s.current.hover=true;}} onPointerLeave={()=>{s.current.hover=false;}}>
      <div className="av1-ring" aria-hidden="true"/>
      <div className="av1-globe"><EarthGlobe/></div>
      {events.map((e,i)=><div key={e.id} className={'av1-slot'+(i===active?' active':'')} ref={n=>{cards.current[i]=n;}} onClick={()=>go(i)}><Card event={e}/></div>)}
      <div className="av-astronaut" ref={astro} aria-hidden="true"><Astronaut/></div>
    </div>
    <Controls active={active} go={go}/>
  </section>;
}

// Variant 2: the camera flies around the globe from site to site (the planet turns under it and the stars sweep
// past); on arrival the event's card grows out of its pin. All five sites stay marked on the globe.
const FLY_MS=1800,STAY_MS=5200;
const rad=(d:number)=>d*Math.PI/180;
function project(view:GlobeView,lat:number,lon:number){
  const la=rad(lat),rel=rad(lon)-view.lon,c=Math.cos(view.lat),sn=Math.sin(view.lat);
  const wx=Math.cos(la)*Math.sin(rel),wy=Math.sin(la),wz=Math.cos(la)*Math.cos(rel);
  return {x:wx,y:c*wy-sn*wz,z:sn*wy+c*wz};
}
function Variant2(){
  const reduced=useReduced();
  const stage=useRef<HTMLDivElement>(null),world=useRef<HTMLDivElement>(null),pins=useRef<(HTMLButtonElement|null)[]>([]),card=useRef<HTMLDivElement>(null),stars=useRef<HTMLCanvasElement>(null);
  const view=useRef<GlobeView>({lon:rad(places.wildfires.lon),lat:rad(places.wildfires.lat)});
  const [active,setActive]=useState(0),[arrived,setArrived]=useState(true);
  const s=useRef({active:0,from:{...view.current},to:{...view.current},t0:0,flying:false,hover:false,next:0});
  const go=(i:number)=>{
    const st=s.current;if(i===st.active&&!st.flying)return;
    const p=events[i].place;let lon=rad(p.lon);
    while(lon-view.current.lon>Math.PI)lon-=Math.PI*2;while(lon-view.current.lon<-Math.PI)lon+=Math.PI*2;
    st.active=i;st.from={...view.current};st.to={lon,lat:rad(p.lat)};st.t0=performance.now();st.flying=true;
    setActive(i);setArrived(false);
  };
  useEffect(()=>{
    const cv=stars.current,ctx=cv?.getContext('2d');
    const field=Array.from({length:260},()=>({x:Math.random(),y:Math.random(),z:Math.random()**2*.9+.1,r:Math.random()*1.2+.3}));
    let frame=0;
    const tick=(now:number)=>{
      frame=requestAnimationFrame(tick);
      const st=s.current,el=stage.current;if(!el)return;
      if(st.flying){
        const t=reduced?1:clamp((now-st.t0)/FLY_MS),e=ease(t);
        view.current={lon:st.from.lon+(st.to.lon-st.from.lon)*e,lat:st.from.lat+(st.to.lat-st.from.lat)*e};
        // The camera pulls back a little mid-flight, as when orbiting to the far side.
        if(world.current)world.current.style.transform=`scale(${(1-.1*Math.sin(Math.PI*t)).toFixed(4)})`;
        if(t>=1){st.flying=false;st.next=now+STAY_MS;setArrived(true);}
      }else if(!st.hover&&!reduced&&now>st.next)go((st.active+1)%N);
      // Pins on the globe, hidden on the far side.
      const g=world.current?.querySelector<HTMLElement>('.av2-globe');
      if(g){
        // The globe box is placed at left/top 50% and pulled back by half its size, so its offset is its centre.
        const size=g.offsetWidth,R=size/2*.91,cx=g.offsetLeft,cy=g.offsetTop;
        events.forEach((ev,i)=>{
          const pin=pins.current[i];if(!pin)return;const p=project(view.current,ev.place.lat,ev.place.lon);
          pin.style.transform=`translate(-50%,-50%) translate(${(cx+p.x*R).toFixed(1)}px,${(cy-p.y*R).toFixed(1)}px) scale(${(.6+.4*clamp(p.z)).toFixed(3)})`;
          pin.style.opacity=p.z>.05?String(clamp(p.z*3)):'0';pin.style.pointerEvents=p.z>.2?'auto':'none';
          if(i===st.active&&card.current){card.current.style.left=`${(cx+p.x*R).toFixed(1)}px`;card.current.style.top=`${(cy-p.y*R).toFixed(1)}px`;}
        });
      }
      // Stars sweep the opposite way to the camera, nearer ones faster.
      if(cv&&ctx){
        const w=el.clientWidth,h=el.clientHeight;if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
        ctx.clearRect(0,0,w,h);ctx.fillStyle='#dceeff';
        for(const st2 of field){
          const x=((st2.x-view.current.lon/(Math.PI*2)*1.6*st2.z)%1+1)%1*w,y=((st2.y+view.current.lat/Math.PI*.8*st2.z)%1+1)%1*h;
          ctx.globalAlpha=.25+.6*st2.z;ctx.fillRect(x,y,st2.r*(1+st2.z),st2.r*(1+st2.z));
        }
        ctx.globalAlpha=1;
      }
    };
    s.current.next=performance.now()+STAY_MS;frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
  },[]);
  const ev=events[active];
  return <section className="av-panel" aria-labelledby="av2-title">
    <header><span className="av-eyebrow">Variant 2</span><h2 id="av2-title">Camera around the planet</h2><p>The camera flies around the globe to each site; the card grows out of the pin when it arrives.</p></header>
    <div className="av-stage av2" ref={stage} onPointerEnter={()=>{s.current.hover=true;}} onPointerLeave={()=>{s.current.hover=false;}}>
      <canvas className="av2-stars" ref={stars} aria-hidden="true"/>
      <div className="av2-world" ref={world}>
        <div className="av2-globe"><EarthGlobe view={view}/></div>
        {events.map((e,i)=>{const Icon=e.Icon;return <button key={e.id} type="button" className={'av2-pin'+(i===active?' active':'')} ref={n=>{pins.current[i]=n;}} style={{'--event':e.color} as CSSProperties} aria-label={`${e.label}: ${e.place.name}`} onClick={()=>go(i)}><Icon size={14} aria-hidden="true"/></button>;})}
        <div className={'av2-card'+(arrived?' shown':'')} ref={card} aria-live="polite">
          <Card event={ev} compact><span className="av-place">{ev.place.example?'Example region · ':'Case study · '}{ev.place.name}</span></Card>
        </div>
      </div>
    </div>
    <Controls active={active} go={go}/>
  </section>;
}

export default function AboutVariants(){
  useEffect(()=>{document.title='EarthSignal — About variants (prototype)';},[]);
  return <div className="av">
    <header className="av-top"><a href="/#about">← Back to the landing page</a><h1>About · two variants <small>Temporary prototype page, same five event types in both</small></h1></header>
    <main className="av-grid"><Variant1/><Variant2/></main>
  </div>;
}
