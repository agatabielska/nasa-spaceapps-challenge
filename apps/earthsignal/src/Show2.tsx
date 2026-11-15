import {useEffect,useRef,useState,type CSSProperties} from 'react';
import {Astronaut} from './Astronaut';
import {etnaCloud,flight} from './cases';
import {EXPLORER_PATH} from './routes';
import {TEAM,TEAM_NAME,portrait} from './team';
import './show.css';
import './show2.css';

// /show2: the second cut of the 30-second presentation (the first one stays at /show). Seven scenes: the title with
// the team, why NISAR, the app's own globe with Orbit, the Nepal flight, a card announcing our local case study,
// the Silesia timeline with the app's own chart of one bowl, and the closing line.
// As in /show, everything is loaded before the clock starts and every scene is drawn from the clock time.
// ?auto starts it once loaded; ?t=12.5 freezes it at that second (for checking a frame).
const AT={title:0,why:1.5,app:6.5,nepal:13.7,local:19.1,silesia:21.1,outro:28.7},END=30;
const ORDER=['title','why','app','nepal','local','silesia','outro'] as const;
type SceneId=typeof ORDER[number];
const sceneAt=(t:number):SceneId=>ORDER.reduce<SceneId>((found,id)=>t>=AT[id]?id:found,'title');
const WHY=['Sees through clouds, smoke and darkness','Returns to the same place every 12 days','One radar for floods, fires, volcanoes and sinking ground','Measures ground motion down to centimetres','Open and free data'];
// The app scene, in seconds after it starts: two flights over the globe, then Orbit, then the zoom to Nepal.
const START={lon:42,lat:30},ETNA={name:'Etna',what:'Eruption',lon:15,lat:37.75,color:'#ff6b6b'},SPAIN={name:'Spain',what:'Wildfire',lon:-4.8,lat:40.4,color:'#ffa94d'},NEPAL={lon:85.4,lat:28.2};
const FLY=1.1,TO_ETNA=.2,TO_SPAIN=1.9,ORBIT=3.6,CHAT=3.9,TYPE=4.3,SENT=5.5,ZOOM=5.7,ZOOM_LEN=1.9,CLOSE_ZOOM=9.4;
const ASK='Show me the flood in Nepal';
const APP=EXPLORER_PATH+'?embed',TIMELINE='/analysis/silesia/krzyzowice-timeline.html';
const FRAMES=Array.from({length:Math.ceil(flight.count/2)},(_,i)=>i*2);
const clamp=(v:number,a=0,b=1)=>Math.max(a,Math.min(b,v));
const ease=(t:number)=>t*t*(3-2*t);
const mix=(a:number,b:number,u:number)=>a+(b-a)*u;
const day=(iso:string)=>new Date(iso+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
// Runs code inside the embedded timeline page (same origin), where its map and data are top-level constants.
function inFrame<T>(frame:HTMLIFrameElement|null,code:string):T|null{
  try{return (frame?.contentWindow as unknown as {eval(c:string):T}|null)?.eval(code)??null;}catch{return null;}
}
// The app's map, which the explorer exposes on its window in ?embed mode.
type AppMap={loaded():boolean;areTilesLoaded():boolean;getZoom():number;jumpTo(o:{center:[number,number];zoom:number;padding?:{top:number;bottom:number;left:number;right:number}}):void;project(p:[number,number]):{x:number;y:number}};
const appMap=(frame:HTMLIFrameElement|null)=>{try{return (frame?.contentWindow as unknown as {__earthsignalMap?:AppMap}|null)?.__earthsignalMap??null;}catch{return null;}};
// The chart is drawn for a 360 px panel; scale it with the screen.
const CHART_ZOOM=()=>clamp(window.innerWidth/1050,1,2.2).toFixed(2);
type Timeline={dates:string[];measured:number;event:{lon:number;lat:number}|null};

export default function Show2(){
  const [scene,setScene]=useState<SceneId>('title'),[ready,setReady]=useState(false),[loaded,setLoaded]=useState(0),[state,setState]=useState<'idle'|'playing'|'done'>('idle');
  const [site,setSite]=useState(-1),[orbit,setOrbit]=useState(false),[chat,setChat]=useState(false),[typed,setTyped]=useState(0),[sent,setSent]=useState(false);
  const [date,setDate]=useState(''),[hole,setHole]=useState<{x:number;y:number}|null>(null);
  const cloud=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null),app=useRef<HTMLIFrameElement>(null),frame=useRef<HTMLIFrameElement>(null),bar=useRef<HTMLElement>(null),route=useRef<HTMLElement>(null),label=useRef<HTMLSpanElement>(null);
  const images=useRef<(HTMLImageElement|undefined)[]>([]),timeline=useRef<Timeline|null>(null),zoom0=useRef(1.4);
  const frozen=useRef<number|null>(null);
  useEffect(()=>{document.title='EarthSignal — 30-second show';const t=new URLSearchParams(window.location.search).get('t');if(t!==null&&!Number.isNaN(+t))frozen.current=clamp(+t,0,END);},[]);
  // Load everything first: pictures, flight frames, the app's globe and the timeline page with its map tiles.
  useEffect(()=>{
    let cancelled=false,done=0;
    const stills=[etnaCloud.before.src,etnaCloud.after.src,...TEAM.map(portrait)];
    const total=stills.length+FRAMES.length+2;
    const tick=()=>{done++;if(!cancelled){setLoaded(done/total);if(done>=total)setReady(true);}};
    for(const src of stills){const img=new Image();img.onload=img.onerror=tick;img.src=src;}
    FRAMES.forEach((n,i)=>{const img=new Image();img.onload=()=>{images.current[i]=img;tick();};img.onerror=tick;img.src=flight.frame(n);});
    // Both embedded maps count once they have drawn (or after 15 s, so a slow connection cannot block the show).
    const started=Date.now();let appDone=false,lineDone=false;
    const late=()=>Date.now()-started>15000;
    const poll=setInterval(()=>{
      if(!appDone){
        const m=appMap(app.current);
        // The explorer turns to its overview once its catalog has loaded; that zoom is the base of this scene.
        if((m&&m.loaded()&&m.areTilesLoaded()&&app.current?.contentDocument?.querySelector('.map-marker'))||late()){appDone=true;if(m)zoom0.current=m.getZoom()-.32;tick();}
      }
      if(!lineDone){
        const f=frame.current,ok=inFrame<boolean>(f,'typeof map!=="undefined"&&map.loaded()&&map.areTilesLoaded()');
        if(ok||late()){
          lineDone=true;
          const data=inFrame<Timeline>(f,'({dates:C.dates,measured:NM,event:C.events[0]?{lon:C.events[0].lon,lat:C.events[0].lat}:null})');
          if(data){
            timeline.current=data;
            // Only the map stays: its own (Polish) panels are replaced by this page's headline and date.
            // Its chart of one bowl stays too, enlarged in the top-right corner: measurements and the forecast.
            const css=f!.contentDocument!.createElement('style');css.textContent='.panel,#time,#ev,.src,.maplibregl-ctrl,#chart .x,.boom{display:none!important}#chart{display:block!important;left:auto!important;bottom:auto!important;right:2.2vw!important;top:4vh!important;width:360px!important;zoom:'+CHART_ZOOM()+';box-shadow:0 20px 60px #000c}';f!.contentDocument!.head.append(css);
            // The bowl nearest to the sinkhole; the map is refitted so the chart and the caption do not cover the bowls.
            inFrame(f,`(()=>{const e=C.events[0];let k=0,d=1e9;if(e)C.bowls.forEach((b,i)=>{const q=(b.lon-e.lon)**2+(b.lat-e.lat)**2;if(q<d){d=q;k=i;}});sel=k;map.setFeatureState({source:'bowls',id:k},{on:true});draw(k);const w=innerWidth,h=innerHeight;map.fitBounds([[BW,BS],[BE,BN]],{padding:{top:h*.08,bottom:h*.3,left:w*.03,right:w*.4},duration:0});})()`);
            inFrame(f,'show(0)');
          }
          tick();
        }
      }
      if(appDone&&lineDone)clearInterval(poll);
    },250);
    return()=>{cancelled=true;clearInterval(poll);};
  },[]);
  // The show itself: everything on screen is a function of the seconds since it started.
  useEffect(()=>{
    if(state!=='playing')return;
    const t0=performance.now();let raf=0,drawn=-1,stop=-1;
    // Last values sent to React, so state is set only when something changes.
    const was={scene:'' as SceneId|'',site:-2,orbit:false,chat:false,typed:-1,sent:false,hole:false};
    const draw=()=>{
      const t=frozen.current??Math.min(END,(performance.now()-t0)/1000),now=sceneAt(t);
      if(now!==was.scene){was.scene=now;setScene(now);}
      if(bar.current)bar.current.style.transform=`scaleX(${(t/END).toFixed(4)})`;
      // Why NISAR: the divider crosses the whole picture, from optical to radar.
      if(cloud.current)cloud.current.style.setProperty('--split',`${mix(98,2,ease(clamp((t-AT.why-.9)/(AT.app-AT.why-1.7)))).toFixed(2)}%`);
      // The app: fly to Etna, then Spain; Orbit takes the question; only then the camera dives to Nepal.
      const a=t-AT.app,m=appMap(app.current);
      if(m&&a>-.7&&t<AT.nepal+.7){
        const u1=ease(clamp((a-TO_ETNA)/FLY)),u2=ease(clamp((a-TO_SPAIN)/FLY)),z=clamp((a-ZOOM)/ZOOM_LEN),turn=ease(clamp(z/.7));
        const lon=mix(mix(mix(START.lon,ETNA.lon,u1),SPAIN.lon,u2),NEPAL.lon,turn),lat=mix(mix(mix(START.lat,ETNA.lat,u1),SPAIN.lat,u2),NEPAL.lat,turn);
        const top=mix(window.innerHeight*.1,0,ease(z));
        m.jumpTo({center:[lon,lat],zoom:mix(zoom0.current,CLOSE_ZOOM,z*z*(3-2*z)),padding:{top,bottom:0,left:0,right:0}});
        const shown=a>=ZOOM-.2?-1:u2>.92?1:u1>.92&&a<TO_SPAIN+.1?0:-1;
        if(shown!==was.site){was.site=shown;setSite(shown);}
        const s=shown===1?SPAIN:ETNA,p=m.project([s.lon,s.lat]),box=(app.current!.contentDocument?.querySelector('.map')??app.current!).getBoundingClientRect();
        if(label.current)label.current.style.transform=`translate(${(box.left+p.x).toFixed(1)}px,${(box.top+p.y).toFixed(1)}px)`;
      }
      const flags={orbit:a>=ORBIT,chat:a>=CHAT,sent:a>=SENT},n=Math.round(clamp((a-TYPE)/(SENT-TYPE-.25))*ASK.length);
      if(flags.orbit!==was.orbit){was.orbit=flags.orbit;setOrbit(flags.orbit);}
      if(flags.chat!==was.chat){was.chat=flags.chat;setChat(flags.chat);}
      if(flags.sent!==was.sent){was.sent=flags.sent;setSent(flags.sent);}
      if(n!==was.typed){was.typed=n;setTyped(n);}
      // Nepal: one steady pass along the whole flight.
      if(t>=AT.nepal-.6&&t<AT.local+.6){
        const p=clamp((t-AT.nepal)/(AT.local-AT.nepal)),cv=canvas.current,ctx=cv?.getContext('2d');
        let i=Math.round(p*(FRAMES.length-1));while(i>0&&!images.current[i])i--;
        const img=images.current[i];
        if(cv&&ctx&&img&&i!==drawn){
          const w=cv.clientWidth,h=cv.clientHeight;if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
          const k=Math.max(w/img.width,h/img.height);ctx.drawImage(img,(w-img.width*k)/2,(h-img.height*k)/2,img.width*k,img.height*k);drawn=i;
        }
        if(route.current)route.current.style.transform=`scaleX(${p.toFixed(4)})`;
      }
      // Silesia: the measurements play from the first to the last radar pass, then the sinkhole is pointed out.
      const tl=timeline.current;
      if(tl&&t>=AT.silesia-.2){
        const last=tl.measured-1,i=Math.round(clamp((t-AT.silesia-.7)/3.9)*last);
        if(i!==stop){stop=i;inFrame(frame.current,`show(${i})`);setDate(day(tl.dates[i]));}
        const point=t>=AT.silesia+4.9&&!!tl.event;
        if(point!==was.hole){
          was.hole=point;
          const p=point?inFrame<[number,number]>(frame.current,`(p=>[p.x,p.y])(map.project([${tl.event!.lon},${tl.event!.lat}]))`):null;
          setHole(p?{x:p[0],y:p[1]}:null);
        }
      }
      if(t>=END){setState('done');return;}
      raf=requestAnimationFrame(draw);
    };
    raf=requestAnimationFrame(draw);
    return()=>cancelAnimationFrame(raf);
  },[state]);
  const start=()=>{if(ready&&state!=='playing'){inFrame(frame.current,'show(0)');setDate('');setHole(null);setSite(-1);setOrbit(false);setChat(false);setTyped(0);setSent(false);setScene('title');setState('playing');}};
  // Space or Enter starts it; ?auto (or ?t=) starts it as soon as everything is loaded.
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();start();}};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  });
  useEffect(()=>{const q=new URLSearchParams(window.location.search);if(ready&&state==='idle'&&(q.has('auto')||q.has('t')))start();},[ready]);
  const on=(id:SceneId)=>'sh-scene sh-'+id+(scene===id?' on':'');
  const shown=site===1?SPAIN:ETNA;
  return <div className={'show show2 sh-'+state}>
    <div className="sh-stars" aria-hidden="true"/>
    <section className={on('title')}>
      <p className="sh-kicker">NASA Space Apps Challenge 2026 · EarthSignal</p>
      <h1>Dancing with<br/><em>the SARs</em></h1>
      <p className="sh-line">A changing planet, seen by NISAR radar.</p>
      <p className="s2-team-name">Team <b>{TEAM_NAME}</b></p>
      <ul className="s2-team">{TEAM.map(name=><li key={name}><img src={portrait(name)} alt=""/><span>{name}</span></li>)}</ul>
      {state==='idle'&&<div className="sh-start">{ready?<button type="button" onClick={start} autoFocus>▶ Start</button>:<span className="sh-loading"><i style={{transform:`scaleX(${loaded})`}}/></span>}</div>}
    </section>
    <section className={on('why')}>
      <div className="sh-text"><p className="sh-kicker">Clouds hide it. Radar sees through.</p><h2>Why use <em>NISAR</em></h2>
        <ul className="s2-why">{WHY.map((line,i)=><li key={line} style={{'--i':i} as CSSProperties}>{line}</li>)}</ul></div>
      <div className="sh-compare" ref={cloud} style={{'--split':'98%',aspectRatio:`${etnaCloud.width}/${etnaCloud.height}`} as CSSProperties}>
        <img src={etnaCloud.after.src} alt=""/><div className="sh-before"><img src={etnaCloud.before.src} alt=""/></div>
        <span className="sh-tag sh-tag-l">Optical</span><span className="sh-tag sh-tag-r">Radar</span><i className="sh-divider"/>
      </div>
    </section>
    <section className={on('app')}>
      <iframe ref={app} src={APP} title="EarthSignal app" tabIndex={-1}/>
      <div className="s2-head"><h2 className={orbit?'':'on'}>Explore multiple events <em>with our app</em></h2><h2 className={orbit?'on':''}>Explore any place <em>with the help of Orbit</em></h2></div>
      <span className={'s2-label'+(site>=0?' on':'')} ref={label} style={{'--c':shown.color} as CSSProperties}><strong>{shown.name}<small>{shown.what}</small></strong></span>
      <div className={'s2-orbit'+(orbit?' awake':'')+(chat?' open':'')}>
        <div className="s2-chat">
          <p className="s2-chat-head"><i/>Orbit<small>your guide to the catalog</small></p>
          <p className={'s2-ask'+(sent?' sent':'')}>{ASK.slice(0,typed)}{!sent&&<b/>}</p>
          <p className={'s2-reply'+(sent?' on':'')}>Flying to Nepal…</p>
        </div>
        <div className="s2-astro"><Astronaut/></div>
      </div>
    </section>
    <section className={on('nepal')}>
      <canvas ref={canvas}/>
      <div className="sh-caption"><p className="sh-kicker">Nepal · glacier collapse</p><h2>The flood path, <em>traced from orbit.</em></h2>
        <p className="s2-key"><i/>Red and orange: the flood impact area detected by our model</p><span className="sh-route"><i ref={route}/></span></div>
    </section>
    <section className={on('local')}>
      <p className="sh-kicker">Our local case study</p>
      <h2>Poland's mining region,<br/><em>explored with NISAR for the first time.</em></h2>
    </section>
    <section className={on('silesia')}>
      <iframe ref={frame} src={TIMELINE} title="Subsidence timeline" tabIndex={-1}/>
      <div className="sh-caption s2-case"><p className="sh-kicker">Case study · Krzyżowice, Poland</p><h2>The ground sinks <em>above the mines.</em></h2>
        <p className="sh-date">{date}</p></div>
      {hole&&<div className="s2-hole" style={{left:hole.x,top:hole.y}}>
        <i/><div><strong>The sinkhole actually appeared where we mapped the ground sinking</strong><span>Last radar pass: <b>16 Oct</b> · Sinkhole: <b>28 Oct</b></span><small>Approximate location</small></div>
      </div>}
    </section>
    <section className={on('outro')}>
      <p className="sh-kicker">EarthSignal · Team {TEAM_NAME}</p>
      <h2>Anybody will be able to do such a study,<br/><em>anywhere, with our app.</em></h2>
    </section>
    <span className="sh-progress" aria-hidden="true"><i ref={bar}/></span>
    {state==='done'&&<div className="sh-end"><button type="button" onClick={start}>↻ Replay</button><a href={EXPLORER_PATH}>Open the app →</a></div>}
  </div>;
}
