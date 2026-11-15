import {useEffect,useRef,useState,type CSSProperties} from 'react';
import EarthGlobe,{type GlobeView} from './EarthGlobe';
import {etna,etnaCloud,flight} from './cases';
import {EXPLORER_PATH} from './routes';
import './show.css';

// /show: a self-contained 30-second presentation and nothing else. It is one page with no navigation: everything
// it needs is loaded before the clock starts, each scene is drawn from the clock time (so the length is exact
// whatever the frame rate), and scenes cross-fade. Text is limited to one headline per scene.
// Scene starts in seconds; END is the total length.
const AT={title:0,globe:2,cloud:8,etna:12,nepal:16,silesia:22},END=30;
const ORDER=['title','globe','cloud','etna','nepal','silesia'] as const;
type SceneId=typeof ORDER[number];
const sceneAt=(t:number):SceneId=>ORDER.reduce<SceneId>((found,id)=>t>=AT[id]?id:found,'title');
const SITES=[
  {name:'Poland',what:'Sinking ground',lat:50.2,lon:18.85,color:'#c9a6ff'},
  {name:'Etna',what:'Eruption',lat:37.75,lon:15,color:'#ff6b6b'},
  {name:'Nepal',what:'Glacier flood',lat:28.2,lon:85.4,color:'#9be7ff'},
];
const TIMELINE='/analysis/silesia/krzyzowice-timeline.html';
// Every second flight frame is enough for a six-second pass and halves the download.
const FRAMES=Array.from({length:Math.ceil(flight.count/2)},(_,i)=>i*2);
const clamp=(v:number,a=0,b=1)=>Math.max(a,Math.min(b,v));
const ease=(t:number)=>t*t*(3-2*t);
const rad=(d:number)=>d*Math.PI/180;
const month=(iso:string)=>new Date(iso+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
// Runs code inside the embedded timeline page (same origin), where its map and data are top-level constants.
function inFrame<T>(frame:HTMLIFrameElement|null,code:string):T|null{
  try{return (frame?.contentWindow as unknown as {eval(c:string):T}|null)?.eval(code)??null;}catch{return null;}
}

export default function Show(){
  const [scene,setScene]=useState<SceneId>('title'),[ready,setReady]=useState(false),[loaded,setLoaded]=useState(0),[state,setState]=useState<'idle'|'playing'|'done'>('idle');
  const [site,setSite]=useState(0),[date,setDate]=useState(''),[forecast,setForecast]=useState(false),[sinkhole,setSinkhole]=useState(false);
  const view=useRef<GlobeView>({lon:rad(SITES[0].lon-40),lat:rad(25)});
  const globe=useRef<HTMLDivElement>(null),pins=useRef<(HTMLSpanElement|null)[]>([]),cloud=useRef<HTMLDivElement>(null),pair=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null),frame=useRef<HTMLIFrameElement>(null),bar=useRef<HTMLElement>(null),route=useRef<HTMLElement>(null);
  const images=useRef<(HTMLImageElement|undefined)[]>([]),timeline=useRef<{dates:string[];measured:number;event:number}|null>(null);
  useEffect(()=>{document.title='EarthSignal — 30-second show';},[]);
  // Load everything first: pictures, flight frames and the timeline page with its map tiles.
  useEffect(()=>{
    let cancelled=false,done=0;
    const stills=[etnaCloud.before.src,etnaCloud.after.src,etna.before.src,etna.after.src,...etna.layers.slice(0,3).map(l=>l.src)];
    const total=stills.length+FRAMES.length+1;
    const tick=()=>{done++;if(!cancelled){setLoaded(done/total);if(done>=total)setReady(true);}};
    for(const src of stills){const img=new Image();img.onload=img.onerror=tick;img.src=src;}
    FRAMES.forEach((n,i)=>{const img=new Image();img.onload=()=>{images.current[i]=img;tick();};img.onerror=tick;img.src=flight.frame(n);});
    // The timeline counts once its map has drawn (or after 15 s, so a slow connection cannot block the show).
    const started=Date.now();
    const poll=setInterval(()=>{
      const f=frame.current,ok=inFrame<boolean>(f,'typeof map!=="undefined"&&map.loaded()&&map.areTilesLoaded()');
      if(!ok&&Date.now()-started<15000)return;
      clearInterval(poll);
      const data=inFrame<{dates:string[];measured:number;event:number}>(f,'({dates:C.dates,measured:NM,event:(C.events[0]||{stop:99}).stop})');
      if(data){
        timeline.current=data;
        // Only the map stays: its own (Polish) panels are replaced by this page's headline and date.
        const css=f!.contentDocument!.createElement('style');css.textContent='.panel,#chart,#time,#ev,.src,.maplibregl-ctrl{display:none!important}';f!.contentDocument!.head.append(css);
        inFrame(f,'show(0)');
      }
      tick();
    },250);
    return()=>{cancelled=true;clearInterval(poll);};
  },[]);
  // The show itself: everything on screen is a function of the seconds since it started.
  useEffect(()=>{
    if(state!=='playing')return;
    const t0=performance.now();let raf=0,last:SceneId|''='',drawn=-1,stop=-1,lastSite=-1;
    const draw=()=>{
      const t=Math.min(END,(performance.now()-t0)/1000),now=sceneAt(t);
      if(now!==last){last=now;setScene(now);}
      if(bar.current)bar.current.style.transform=`scaleX(${(t/END).toFixed(4)})`;
      // Globe: fly to each site in turn (0.7 s), then rest on it.
      if(t<AT.cloud+.6){
        const g=clamp((t-AT.globe)/(AT.cloud-AT.globe),0,.9999)*SITES.length,k=Math.floor(g),u=ease(clamp((g-k)/.35));
        const from=k?SITES[k-1]:{lon:SITES[0].lon-40,lat:25},to=SITES[k];
        view.current={lon:rad(from.lon+(to.lon-from.lon)*u),lat:rad(from.lat+(to.lat-from.lat)*u)};
        const shown=u>.6?k:-1;if(shown!==lastSite){lastSite=shown;setSite(shown);}
        const el=globe.current;
        if(el){
          const R=el.offsetWidth/2*.91;
          SITES.forEach((s,i)=>{
            const pin=pins.current[i];if(!pin)return;
            const la=rad(s.lat),rel=rad(s.lon)-view.current.lon,c=Math.cos(view.current.lat),sn=Math.sin(view.current.lat);
            const x=Math.cos(la)*Math.sin(rel),wy=Math.sin(la),wz=Math.cos(la)*Math.cos(rel),y=c*wy-sn*wz,z=sn*wy+c*wz;
            pin.style.transform=`translate(-50%,-50%) translate(${(x*R).toFixed(1)}px,${(-y*R).toFixed(1)}px)`;pin.style.opacity=z>.05?'1':'0';
          });
        }
      }
      // Comparisons: the divider sweeps once across the picture, from one image to the other.
      const sweep=(el:HTMLDivElement|null,start:number,end:number)=>{if(el)el.style.setProperty('--split',`${(88-76*ease(clamp((t-start-.5)/(end-start-1.3)))).toFixed(2)}%`);};
      sweep(cloud.current,AT.cloud,AT.etna);sweep(pair.current,AT.etna,AT.nepal);
      // Nepal: one steady pass along the whole flight.
      if(t>=AT.nepal-.6&&t<AT.silesia+.6){
        const p=clamp((t-AT.nepal)/(AT.silesia-AT.nepal)),cv=canvas.current,ctx=cv?.getContext('2d');
        let i=Math.round(p*(FRAMES.length-1));while(i>0&&!images.current[i])i--;
        const img=images.current[i];
        if(cv&&ctx&&img&&i!==drawn){
          const w=cv.clientWidth,h=cv.clientHeight;if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
          const k=Math.max(w/img.width,h/img.height);ctx.drawImage(img,(w-img.width*k)/2,(h-img.height*k)/2,img.width*k,img.height*k);drawn=i;
        }
        if(route.current)route.current.style.transform=`scaleX(${p.toFixed(4)})`;
      }
      // Silesia: the timeline runs from the first measurement to the end of the forecast.
      const tl=timeline.current;
      if(tl&&t>=AT.silesia-.2){
        const n=tl.dates.length-1,i=Math.round(clamp((t-AT.silesia-1.2)/(END-AT.silesia-2.4))*n);
        if(i!==stop){stop=i;inFrame(frame.current,`show(${i})`);setDate(month(tl.dates[i]));setForecast(i>=tl.measured);setSinkhole(i>=tl.event);}
      }
      if(t>=END){setState('done');return;}
      raf=requestAnimationFrame(draw);
    };
    raf=requestAnimationFrame(draw);
    return()=>cancelAnimationFrame(raf);
  },[state]);
  const start=()=>{if(ready&&state!=='playing'){inFrame(frame.current,'show(0)');setDate('');setForecast(false);setSinkhole(false);setScene('title');setState('playing');}};
  // Space or Enter starts it; ?auto starts it as soon as everything is loaded.
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();start();}};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  });
  useEffect(()=>{if(ready&&state==='idle'&&new URLSearchParams(window.location.search).has('auto'))start();},[ready]);
  const on=(id:SceneId)=>'sh-scene sh-'+id+(scene===id?' on':'');
  const compare=(ref:React.RefObject<HTMLDivElement|null>,before:{src:string},after:{src:string},left:string,right:string,width:number,height:number,layers:string[]=[])=>
    <div className="sh-compare" ref={ref} style={{'--split':'88%',aspectRatio:`${width}/${height}`} as CSSProperties}>
      <img src={after.src} alt=""/>{layers.map(src=><img key={src} className="sh-layer" src={src} alt=""/>)}
      <div className="sh-before"><img src={before.src} alt=""/></div>
      <span className="sh-tag sh-tag-l">{left}</span><span className="sh-tag sh-tag-r">{right}</span><i className="sh-divider"/>
    </div>;
  return <div className={'show sh-'+state}>
    <div className="sh-stars" aria-hidden="true"/>
    <section className={on('title')}>
      <p className="sh-kicker">NASA Space Apps Challenge 2026 · EarthSignal</p>
      <h1>Dancing with<br/><em>the SARs</em></h1>
      <p className="sh-line">A changing planet, seen by NISAR radar.</p>
      {state==='idle'&&<div className="sh-start">{ready?<button type="button" onClick={start} autoFocus>▶ Start</button>:<span className="sh-loading"><i style={{transform:`scaleX(${loaded})`}}/></span>}</div>}
    </section>
    <section className={on('globe')}>
      <h2>One radar. <em>Three events.</em></h2>
      <div className="sh-globe" ref={globe}>
        <EarthGlobe view={view}/>
        {SITES.map((s,i)=><span key={s.name} className={'sh-pin'+(site===i?' on':'')} ref={n=>{pins.current[i]=n;}} style={{'--c':s.color} as CSSProperties}><b/><strong>{s.name}<small>{s.what}</small></strong></span>)}
      </div>
    </section>
    <section className={on('cloud')}>
      <div className="sh-text"><p className="sh-kicker">Why radar</p><h2>Clouds hide it.<br/><em>Radar sees through.</em></h2></div>
      {compare(cloud,etnaCloud.before,etnaCloud.after,'Optical','Radar',etnaCloud.width,etnaCloud.height)}
    </section>
    <section className={on('etna')}>
      <div className="sh-text"><p className="sh-kicker">Etna · Italy</p><h2>Before and after<br/><em>the eruption.</em></h2></div>
      {compare(pair,etna.before,etna.after,'23 Jul','28 Aug',etna.width,etna.height,etna.layers.slice(0,3).map(l=>l.src))}
    </section>
    <section className={on('nepal')}>
      <canvas ref={canvas}/>
      <div className="sh-caption"><p className="sh-kicker">Nepal · glacier collapse</p><h2>The flood path, <em>traced from orbit.</em></h2><span className="sh-route"><i ref={route}/></span></div>
    </section>
    <section className={on('silesia')}>
      <iframe ref={frame} src={TIMELINE} title="Subsidence timeline" tabIndex={-1}/>
      <div className="sh-caption"><p className="sh-kicker">Poland · mining region</p><h2>The ground sinks <em>above the mines.</em></h2>
        <p className="sh-date">{date}{forecast&&<b>Forecast</b>}{sinkhole&&<u>Sinkhole reported</u>}</p></div>
    </section>
    <span className="sh-progress" aria-hidden="true"><i ref={bar}/></span>
    {state==='done'&&<div className="sh-end"><button type="button" onClick={start}>↻ Replay</button><a href={EXPLORER_PATH}>Open the app →</a></div>}
  </div>;
}
