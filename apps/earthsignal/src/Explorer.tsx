import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Astronaut} from './Astronaut';
import * as maplibregl from 'maplibre-gl';
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(mapWorkerUrl);
import 'maplibre-gl/dist/maplibre-gl.css';
import {ArrowUpRight,ArrowLeft,ArrowRight,Search,X,ChevronDown,Layers,Map as MapIcon,Plus,Minus,Check,LocateFixed,Send,Sparkles,ExternalLink,Info,PanelLeftClose,Menu,RotateCcw,Satellite,BadgeCheck,FlaskConical,ALargeSmall,CalendarDays,SlidersHorizontal} from 'lucide-react';
import {categories,filterEvents,inBounds,lonSpan,type Kind,type EventRecord} from './domain';
import {KindIcon,kindStyle} from './eventKinds';
import './explorer.css';
import {loadCatalog,loadOrbitStatus,sendOrbit,APIError,type OrbitStatus} from './api';
const allKinds=Object.keys(categories) as Kind[];
const fmt=(d:string)=>new Date(d+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
const reducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const motion=(ms:number)=>reducedMotion()?0:ms;
// Matches the CSS breakpoint where the sidebar becomes an overlay: only one large panel may be open there.
const narrow=()=>window.innerWidth<=640;
const noPadding={top:0,bottom:0,left:0,right:0};
const DEFAULT_FROM='2025-11-01',DEFAULT_TO='2026-11-30';
const fmtShort=(d:string)=>new Date(d+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'2-digit'});
const pad2=(n:number)=>n.toString().padStart(2,'0');
// Per-viewer UI preferences; storage can be unavailable (private mode), so failures fall back to defaults.
function stored<T>(key:string,fallback:T):T{try{const v=localStorage.getItem(key);return v===null?fallback:JSON.parse(v) as T;}catch{return fallback;}}
function store(key:string,value:unknown){try{localStorage.setItem(key,JSON.stringify(value));}catch{/* ignore */}}
type TextSize='auto'|'large'|'xl';
// Base map styles. Satellite (Esri World Imagery, needs a connection) is the default; the illustrated map is
// drawn from the bundled Natural Earth countries and always works offline.
type Basemap='satellite'|'map';
const basemaps:{id:Basemap;label:string;hint:string}[]=[{id:'satellite',label:'Satellite',hint:'Esri World Imagery'},{id:'map',label:'Map',hint:'Countries · works offline'}];
const SATELLITE_TILES='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
// Country borders read on both styles: light blue on the illustrated map, soft white over imagery.
const borderPaint:Record<Basemap,{color:string;opacity:number}>={satellite:{color:'#ffffff',opacity:.45},map:{color:'#8fd6ff',opacity:.35}};
const textSizes:Record<TextSize,{label:string;next:TextSize}>={auto:{label:'Auto',next:'large'},large:{label:'Large',next:'xl'},xl:{label:'XL',next:'auto'}};
type Snapshot={center:[number,number];zoom:number;search:string;kinds:Kind[];from:string;to:string;verified:boolean;viewOnly:boolean;orbitIds:string[]|null};

export default function Explorer(){
const [search,setSearch]=useState(''),[kinds,setKinds]=useState<Kind[]>(allKinds),[from,setFrom]=useState(DEFAULT_FROM),[to,setTo]=useState(DEFAULT_TO),[verified,setVerified]=useState(false),[viewOnly,setViewOnly]=useState(false),[bounds,setBounds]=useState<[number,number,number,number]|null>(null),[selected,setSelected]=useState<EventRecord|null>(null),[chat,setChat]=useState(false),[sidebar,setSidebar]=useState(()=>window.innerWidth>=640),[info,setInfo]=useState(false),[guide,setGuide]=useState(-1),[input,setInput]=useState(''),[messages,setMessages]=useState<{role:string;text:string}[]>([{role:'assistant',text:'Hi, I’m Orbit. Let’s explore our changing planet. Ask for a place or an event type — in your language.'}]),[mapReady,setMapReady]=useState(false),[mapError,setMapError]=useState(false);
const [events,setEvents]=useState<EventRecord[]>([]),[catalogLoading,setCatalogLoading]=useState(true),[catalogError,setCatalogError]=useState(''),[busy,setBusy]=useState(false),[chatError,setChatError]=useState(''),[sources,setSources]=useState<{title:string;url:string}[]>([]),[orbitIds,setOrbitIds]=useState<string[]|null>(null),[orbitStatus,setOrbitStatus]=useState<OrbitStatus>({available:false,model:null,models:[],message:'Checking LM Studio…'}),[mapLoaded,setMapLoaded]=useState(false),[basemap,setBasemap]=useState<Basemap>(()=>stored('earthsignal.basemap','satellite')),[borders,setBorders]=useState(()=>stored('earthsignal.borders',true)),[stylesOpen,setStylesOpen]=useState(false),[satelliteFailed,setSatelliteFailed]=useState(false),[busySince,setBusySince]=useState(0),[,setTick]=useState(0),[statsOpen,setStatsOpen]=useState(()=>stored('earthsignal.stats',!narrow())),[moreOpen,setMoreOpen]=useState(()=>stored('earthsignal.moreFilters',false)),[customDates,setCustomDates]=useState(false),[textSize,setTextSize]=useState<TextSize>(()=>stored('earthsignal.textSize','auto'));
const revision=useRef(0),session=useRef<string|null>(null),snapshot=useRef<Snapshot|null>(null),abort=useRef<AbortController|null>(null),prevSelected=useRef<string|null>(null),initialFit=useRef(false),escape=useRef<()=>void>(()=>{});
async function refreshCatalog(){setCatalogLoading(true);setCatalogError('');try{const result=await loadCatalog();setEvents(result.events);}catch(e){setCatalogError(e instanceof Error?e.message:'Catalog unavailable');}finally{setCatalogLoading(false);}}
async function refreshModel(){try{setOrbitStatus(await loadOrbitStatus());}catch(e){setOrbitStatus({available:false,model:null,models:[],message:e instanceof Error?e.message:'Local API unavailable'});}}
useEffect(()=>{void refreshCatalog();void refreshModel();const timer=setInterval(()=>void refreshModel(),15000);return()=>clearInterval(timer);},[]);
useEffect(()=>{revision.current++;},[search,kinds,from,to,verified,viewOnly,bounds,selected?.id]);
const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null),messagesEl=useRef<HTMLDivElement>(null);
// Orbit results keep the order the assistant returned, so "the second one" matches what the user sees.
const filtered=useMemo(()=>{const list=filterEvents(events,search,kinds,from,to,verified,viewOnly?bounds:null);return orbitIds===null?list:list.filter(e=>orbitIds.includes(e.id)).sort((a,b)=>orbitIds.indexOf(a.id)-orbitIds.indexOf(b.id));},[events,search,kinds,from,to,verified,viewOnly,bounds,orbitIds]);
const visible=filtered.filter(e=>inBounds(e.coordinates,bounds));
const guideOpen=guide>=0;
// Padding measured from the visible overlays, so it follows the responsive layout and the UI text size.
function overlayRect(selector:string){const e=container.current?.parentElement?.querySelector(selector);return e&&getComputedStyle(e).display!=='none'?e.getBoundingClientRect():null;}
function fitPadding(){
  const c=container.current;if(!c)return {top:84,bottom:74,left:80,right:150};const box=c.getBoundingClientRect(),p={top:20,bottom:20,left:20,right:20};
  for(const s of ['.map-heading','.reopen']){const r=overlayRect(s);if(r)p.top=Math.max(p.top,r.bottom-box.top+14);}
  const legend=overlayRect('.map-legend'),controls=overlayRect('.map-controls'),astro=overlayRect('.astronaut-widget');
  if(legend)p.bottom=Math.max(p.bottom,box.bottom-legend.top+14);
  if(controls)p.left=Math.max(p.left,controls.right-box.left+14);
  if(astro)p.right=Math.max(p.right,box.right-astro.left+8);
  if(p.top+p.bottom>box.height-80){const k=Math.max(0,box.height-80)/(p.top+p.bottom);p.top*=k;p.bottom*=k;}
  if(p.left+p.right>box.width-80){const k=Math.max(0,box.width-80)/(p.left+p.right);p.left*=k;p.right*=k;}
  return p;
}
// Keep the selected hotspot clear of the side panel and the guide card.
function focusPadding(){
  // Start from the overview padding (heading, controls, legend), then keep clear of the open side panel and guide.
  const c=container.current;if(!c)return noPadding;const box=c.getBoundingClientRect(),p=fitPadding();
  const side=overlayRect('.detail')??overlayRect('.chat');
  if(side&&box.width>=640)p.right=Math.max(p.right,box.right-side.left+16);
  const g=overlayRect('.guide');
  if(g){const left=g.right-box.left+16;if(box.width-left-p.right>=160)p.left=Math.max(p.left,left);else p.bottom=Math.max(p.bottom,box.bottom-g.top+16);}
  if(p.top+p.bottom>box.height-90){const k=(box.height-90)/(p.top+p.bottom);p.top*=k;p.bottom*=k;}
  if(p.left+p.right>box.width-90){const k=(box.width-90)/(p.left+p.right);p.left*=k;p.right*=k;}
  return p;
}
function fitEvents(list:EventRecord[],duration=800){const m=map.current;const span=lonSpan(list.map(e=>e.coordinates[0]));if(!m||!span)return;const lats=list.map(e=>e.coordinates[1]);m.fitBounds([[span[0],Math.min(...lats)],[span[1],Math.max(...lats)]],{padding:fitPadding(),absolutePadding:true,maxZoom:5,duration:motion(duration)});}
useEffect(()=>{if(!container.current)return;try{const m=new maplibregl.Map({container:container.current,style:{version:8,sources:{countries:{type:'geojson',data:'/countries.geojson'},satellite:{type:'raster',tiles:[SATELLITE_TILES],tileSize:256,maxzoom:19,attribution:'Imagery © Esri, Maxar, Earthstar Geographics'}},layers:[{id:'ocean',type:'background',paint:{'background-color':'#050d1f'}},{id:'satellite',type:'raster',source:'satellite',layout:{visibility:basemap==='satellite'?'visible':'none'},paint:{'raster-brightness-max':.88,'raster-saturation':-.1,'raster-fade-duration':200}},{id:'land',type:'fill',source:'countries',layout:{visibility:basemap==='map'?'visible':'none'},paint:{'fill-color':'#16294d','fill-opacity':1}},{id:'borders',type:'line',source:'countries',layout:{visibility:borders?'visible':'none'},paint:{'line-color':borderPaint[basemap].color,'line-width':0.7,'line-opacity':borderPaint[basemap].opacity}}]},center:[14,24],zoom:1.65,maxZoom:12,minZoom:-1,attributionControl:{compact:true,customAttribution:'<a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a>'},pitchWithRotate:false,dragRotate:false});map.current=m;if(import.meta.env.DEV)(window as unknown as {__earthsignalMap:maplibregl.Map}).__earthsignalMap=m;setMapReady(true);m.on('load',()=>{setMapReady(true);setMapLoaded(true);const b=m.getBounds();setBounds([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);});m.on('moveend',()=>{const b=m.getBounds();setBounds([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);});m.on('error',e=>{if((e as {sourceId?:string}).sourceId==='satellite')setSatelliteFailed(true);else setMapError(true);});const resize=new ResizeObserver(()=>m.resize());resize.observe(container.current);return()=>{resize.disconnect();m.remove();map.current=null;};}catch{setMapError(true);}},[]);
// Markers are buttons with the event type's SVG icon, rendered by a small React root that is unmounted (after
// the current commit) when the markers are rebuilt or the map goes away.
useEffect(()=>{const m=map.current;if(!m||!mapReady)return;
  const made=filtered.map(e=>{
    const el=document.createElement('button');el.type='button';el.className='map-marker'+(selected?.id===e.id?' selected':'');
    el.style.setProperty('--marker',kindStyle[e.kind].color);
    el.setAttribute('aria-label',`${e.title}: ${categories[e.kind].label}, ${e.catalogVerified?'documented candidate':'demo scenario'}`);el.title=e.title;el.onclick=()=>select(e);
    const root=createRoot(el);root.render(<KindIcon kind={e.kind} size={selected?.id===e.id?24:20}/>);
    return {marker:new maplibregl.Marker({element:el}).setLngLat(e.coordinates).addTo(m),root};
  });
  return()=>{for(const {marker,root} of made){marker.remove();queueMicrotask(()=>root.unmount());}};
},[filtered,mapReady,selected?.id]);
// Switch the base map and the border lines without rebuilding the map.
useEffect(()=>{const m=map.current;if(!m||!mapLoaded)return;
  m.setLayoutProperty('satellite','visibility',basemap==='satellite'?'visible':'none');m.setLayoutProperty('land','visibility',basemap==='map'?'visible':'none');
  m.setLayoutProperty('borders','visibility',borders?'visible':'none');m.setPaintProperty('borders','line-color',borderPaint[basemap].color);m.setPaintProperty('borders','line-opacity',borderPaint[basemap].opacity);
},[basemap,borders,mapLoaded]);
// Without a connection the imagery cannot load: fall back to the illustrated map and say why. Only the viewer's
// own choice is remembered, so the next visit tries satellite again.
useEffect(()=>{if(satelliteFailed&&basemap==='satellite')setBasemap('map');},[satelliteFailed]);
// Close the map style menu on a click anywhere else.
useEffect(()=>{if(!stylesOpen)return;const close=(e:PointerEvent)=>{const t=e.target as Element;if(!t.closest('.map-styles,[aria-controls="map-styles"]'))setStylesOpen(false);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[stylesOpen]);
useEffect(()=>store('earthsignal.borders',borders),[borders]);
// Start with every catalog hotspot in view, clear of the overlays.
useEffect(()=>{if(mapLoaded&&events.length&&!initialFit.current){initialFit.current=true;fitEvents(events,0);}},[mapLoaded,events]);
useEffect(()=>{const m=map.current;if(!m)return;if(!selected){prevSelected.current=null;return;}const first=prevSelected.current!==selected.id;prevSelected.current=selected.id;if(first)m.flyTo({center:selected.coordinates,zoom:4.5,padding:focusPadding(),duration:motion(1000)});else m.easeTo({center:selected.coordinates,padding:focusPadding(),duration:motion(400)});},[selected,guideOpen]);
useEffect(()=>{if(selected&&!filtered.some(e=>e.id===selected.id)){setSelected(null);setGuide(-1);}},[filtered,selected]);
// When the side panel would cover the map heading (narrow map or large text), drop it below the heading.
useLayoutEffect(()=>{const area=container.current?.parentElement;if(!area)return;const check=()=>{const h=area.querySelector('.map-heading')?.getBoundingClientRect(),panel=area.querySelector('.detail,.chat')?.getBoundingClientRect();area.classList.toggle('panels-low',!!h&&!!panel&&panel.left<h.right+12);};check();window.addEventListener('resize',check);return()=>window.removeEventListener('resize',check);});
// Scroll only the message list; scrollIntoView would also scroll the clipped app shell.
useEffect(()=>{const el=messagesEl.current;if(el)el.scrollTo({top:el.scrollHeight,behavior:motion(1)?'smooth':'auto'});},[messages,busy,chatError,sources,chat]);
useEffect(()=>{if(!busy)return;const t=setInterval(()=>setTick(x=>x+1),1000);return()=>clearInterval(t);},[busy]);
escape.current=()=>{if(stylesOpen)setStylesOpen(false);else if(info)setInfo(false);else if(chat)setChat(false);else if(guideOpen)setGuide(-1);else if(selected)world();else if(narrow()&&sidebar)setSidebar(false);};
useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if(e.key==='Escape')escape.current();};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);},[]);
function reset(){setOrbitIds(null);setSearch('');setKinds(allKinds);setFrom(DEFAULT_FROM);setTo(DEFAULT_TO);setVerified(false);setViewOnly(false);}
/** Remember the camera and filters once, before the first step away from the overview. */
function remember(){const m=map.current;if(snapshot.current||!m)return;const c=m.getCenter();snapshot.current={center:[c.lng,c.lat],zoom:m.getZoom(),search,kinds,from,to,verified,viewOnly,orbitIds};}
function select(e:EventRecord){remember();setSelected(e);setGuide(-1);if(narrow()){setSidebar(false);setChat(false);}}
/** Back to the world: restore the camera and filters from before the event was opened. */
function world(){const s=snapshot.current;snapshot.current=null;setSelected(null);setGuide(-1);if(!s){fitEvents(filtered.length?filtered:events);return;}setSearch(s.search);setKinds(s.kinds);setFrom(s.from);setTo(s.to);setVerified(s.verified);setViewOnly(s.viewOnly);setOrbitIds(s.orbitIds);map.current?.flyTo({center:s.center,zoom:s.zoom,padding:noPadding,duration:motion(800)});}
/** Full reset to the initial overview. */
function home(){snapshot.current=null;reset();setSelected(null);setGuide(-1);fitEvents(events);}
function openChat(){setChat(true);if(narrow())setSidebar(false);}
function openSidebar(){setSidebar(true);if(narrow())setChat(false);}
async function ask(text:string){
if(!text.trim()||busy)return;
openChat();setInput('');setBusy(true);setBusySince(Date.now());setChatError('');setSources([]);
const started=revision.current,controller=new AbortController();abort.current=controller;
setMessages(m=>[...m,{role:'user',text}]);
try{
  const reply=await sendOrbit({message:text,sessionId:session.current??undefined,context:{selectedEventId:selected?.id??null,bounds,filters:{search,kinds,from,to,documentedOnly:verified,viewOnly},revision:started,listedIds:filtered.slice(0,100).map(e=>e.id)}},controller.signal);
  session.current=reply.sessionId;
  setMessages(m=>[...m,{role:'assistant',text:reply.text}]);setSources(reply.sources);
  setOrbitStatus(p=>({...p,available:true,model:reply.model,message:'Local model ready'}));
  if(started!==revision.current){setChatError('You changed the map while Orbit was answering, so its navigation was skipped. Ask again to apply it.');return;}
  const known=new Map([...events,...reply.events].map(e=>[e.id,e]));
  setEvents([...known.values()]);
  if(reply.actions.some(a=>a.type!=='reset_map'))remember();
  let resultIds:string[]|null=null;
  for(const action of reply.actions){
    if(action.type==='show_results'){
      reset();resultIds=action.eventIds.filter(id=>known.has(id));setOrbitIds(resultIds);
      const targets=resultIds.map(id=>known.get(id)!);if(targets.length>1)fitEvents(targets,700);
    } else if(action.type==='focus_event'||action.type==='start_guide'){
      const event=known.get(action.eventId);if(!event)continue;
      // Keep the list the user is looking at when the event is already on it (e.g. "open the second one").
      if(resultIds){reset();setOrbitIds(resultIds);}else if(!filtered.some(e=>e.id===event.id)){reset();setOrbitIds([event.id]);}
      setSelected(event);setGuide(action.type==='start_guide'?0:-1);
    }else if(action.type==='reset_map')home();
  }
}catch(e){
  if(e instanceof APIError&&e.code==='SESSION_EXPIRED')session.current=null;
  setChatError(e instanceof APIError&&e.code==='CANCELLED'?'Request cancelled. The map was not changed.':e instanceof Error?e.message:'Orbit could not get an answer from the model.');
}
finally{setBusy(false);abort.current=null;}
}
useEffect(()=>store('earthsignal.stats',statsOpen),[statsOpen]);
useEffect(()=>store('earthsignal.moreFilters',moreOpen),[moreOpen]);
useEffect(()=>store('earthsignal.textSize',textSize),[textSize]);
// Overlays change size with the text setting: re-fit the overview once the new layout is in place.
useEffect(()=>{if(!mapLoaded)return;const t=setTimeout(()=>{map.current?.resize();if(!selected)fitEvents(filtered.length?filtered:events,300);},60);return()=>clearTimeout(t);},[textSize]);
const todayISO=new Date().toISOString().slice(0,10);
const monthsAgo=(n:number)=>{const d=new Date();d.setUTCMonth(d.getUTCMonth()-n);return d.toISOString().slice(0,10);};
const presets=[{label:'All dates',from:DEFAULT_FROM,to:DEFAULT_TO},{label:'Last 3 months',from:monthsAgo(3),to:todayISO},{label:'2026',from:'2026-01-01',to:'2026-12-31'}];
const datePreset=presets.find(p=>p.from===from&&p.to===to);
const showDates=customDates||!datePreset;
const documentedVisible=visible.filter(e=>e.catalogVerified).length;
// Extra filters stay marked on the "More filters" button while the section is closed.
const extraFilters=(verified?1:0)+(viewOnly?1:0);
// Only filters that actually narrow the results count as active; Reset clears them all, Orbit's included.
const narrowed=!!search.trim()||kinds.length<allKinds.length||from!==DEFAULT_FROM||to!==DEFAULT_TO||verified||viewOnly||orbitIds!==null;
const toggleKind=(k:Kind)=>setKinds(p=>p.includes(k)?p.filter(x=>x!==k):[...p,k]);
// Catalog activity follows the selected date range (at most 24 months) instead of a fixed year.
const months:{y:number;m:number}[]=[];for(let y=+from.slice(0,4),m=+from.slice(5,7);(y<+to.slice(0,4)||(y===+to.slice(0,4)&&m<=+to.slice(5,7)))&&months.length<24;m===12?(m=1,y++):m++)months.push({y,m});
const monthly=months.map(({y,m})=>visible.filter(e=>+e.date.slice(0,4)===y&&+e.date.slice(5,7)===m).length);
const monthName=(y:number,m:number,style:'long'|'short'='long')=>new Date(Date.UTC(y,m-1,15)).toLocaleString('en-GB',{month:style,year:'numeric',timeZone:'UTC'});
const guideText=selected?[`Explore ${selected.country}. ${selected.description}`,selected.observations?`The candidate observations were acquired on ${selected.observations.map(fmt).join(' and ')}. They are individual samples, not continuous monitoring.`:'This scenario has no verified NISAR observations. The displayed date is part of a demonstration fixture.','The next stage will add aligned before/after rasters, valid-pixel masks and an independently checked interpretation. No surface-change result is available yet.']:['Choose a hotspot on the map or in the event list.','Use the category and date filters to explore the catalog.','A selected case study will unlock observation comparisons and measured statistics.'];
return <div className="app" data-text={textSize}>
<header className="topbar">
  <a className="brand" href="/" aria-label="EarthSignal, back to the journey"><span className="brand-logo" aria-hidden="true"/><span><b>EarthSignal</b><small>Explorer</small></span></a>
  <div className="top-right">
    <a className="top-link" href="/">The journey <ArrowUpRight size={15} aria-hidden="true"/></a>
    <button className="icon-button mobile-menu" aria-label={sidebar?'Close search and filters':'Open search and filters'} aria-expanded={sidebar} onClick={()=>sidebar?setSidebar(false):openSidebar()}><Menu size={19}/></button>
    <button className="text-size" onClick={()=>setTextSize(textSizes[textSize].next)} aria-label={`Text size: ${textSizes[textSize].label}. Change text size`} title="Text size for presentations"><ALargeSmall size={18} aria-hidden="true"/><span>{textSizes[textSize].label}</span></button>
    <button className="icon-button" onClick={()=>setInfo(true)} aria-label="About EarthSignal, data and method" title="About, data and method"><Info size={18}/></button>
  </div>
</header>
<div className="workspace">{sidebar&&<aside className="sidebar" aria-label="Search and filters">
<div className="sb-head"><h1>Explore events</h1><button className="icon-button" aria-label="Collapse search and filters" onClick={()=>setSidebar(false)}><PanelLeftClose size={18}/></button></div>
<label className="search-box"><Search size={18} aria-hidden="true"/><input aria-label="Search a place or event" placeholder="Search a place or event…" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="Clear search" onClick={()=>setSearch('')}><X size={15}/></button>}</label>
<div className="kind-filter" role="group" aria-label="Event type">{allKinds.map(k=><button key={k} type="button" aria-pressed={kinds.includes(k)} className="kind-chip" style={{'--kind':kindStyle[k].color} as React.CSSProperties} onClick={()=>toggleKind(k)}><KindIcon kind={k} size={16}/><span>{categories[k].label}</span></button>)}</div>
<div className="date-range">
  <label className="date-select"><CalendarDays size={16} aria-hidden="true"/><span className="sr-only">Event date</span>
    <select value={showDates?'custom':datePreset!.label} onChange={e=>{const preset=presets.find(p=>p.label===e.target.value);if(preset){setFrom(preset.from);setTo(preset.to);setCustomDates(false);}else setCustomDates(true);}}>
      {presets.map(p=><option key={p.label} value={p.label}>{p.label}</option>)}<option value="custom">Custom range…</option>
    </select><ChevronDown size={15} aria-hidden="true"/></label>
  {showDates&&<div className="date-inputs"><label><span>From</span><input type="date" value={from} max={to} onChange={e=>{const v=e.target.value;if(!v)return;setFrom(v);if(v>to)setTo(v);}}/></label><label><span>To</span><input type="date" value={to} min={from} onChange={e=>{const v=e.target.value;if(!v)return;setTo(v);if(v<from)setFrom(v);}}/></label></div>}
</div>
<div className="more-filters">
  <button type="button" className="more-toggle" aria-expanded={moreOpen} aria-controls="more-filters" onClick={()=>setMoreOpen(!moreOpen)}><SlidersHorizontal size={16} aria-hidden="true"/><span>More filters</span>{extraFilters>0&&<b className="more-count" aria-label={`${extraFilters} on`}>{extraFilters} on</b>}<ChevronDown size={16} aria-hidden="true"/></button>
  {moreOpen&&<div className="more-body" id="more-filters"><label className="switch-row"><span><strong>Documented candidates only</strong><small>Hide illustrative demo scenarios</small></span><input type="checkbox" role="switch" checked={verified} onChange={e=>setVerified(e.target.checked)}/></label><label className="switch-row"><span><strong>Current map area only</strong><small>List only events visible on the map</small></span><input type="checkbox" role="switch" checked={viewOnly} onChange={e=>setViewOnly(e.target.checked)}/></label></div>}
</div>
<div className="list-head"><h2><b>{filtered.length}</b> {filtered.length===1?'result':'results'}</h2>{narrowed&&<button className="reset-link" onClick={reset}><RotateCcw size={13} aria-hidden="true"/>Reset</button>}<button className="icon-button" aria-label="Refresh event catalog" title="Refresh catalog" onClick={()=>void refreshCatalog()}><RotateCcw size={14}/></button></div>
{orbitIds!==null&&<button className="orbit-chip" onClick={()=>setOrbitIds(null)} aria-label={`Remove Orbit's limit to ${orbitIds.length} results`}><Sparkles size={13} aria-hidden="true"/><span>Orbit picked {orbitIds.length} {orbitIds.length===1?'result':'results'}</span><X size={13} aria-hidden="true"/></button>}
<div className="event-list">{catalogLoading?<div className="empty-list">Loading local database…</div>:catalogError?<div className="empty-list" role="alert">{catalogError}<button onClick={()=>void refreshCatalog()}>Retry</button></div>:filtered.length?filtered.map(e=><button className={'event-row'+(selected?.id===e.id?' active':'')} key={e.id} onClick={()=>select(e)} style={{'--kind':kindStyle[e.kind].color} as React.CSSProperties}><span className="row-icon"><KindIcon kind={e.kind} size={17}/><span className="sr-only">{categories[e.kind].label}: </span></span><span className="row-text"><strong>{e.title}</strong><small><span>{e.country} · {fmt(e.date)}</span><span className={'row-badge'+(e.catalogVerified?' documented':'')}>{e.catalogVerified?'Documented':'Demo'}</span></small></span></button>):<div className="empty-list">No events match these filters.<button onClick={reset}>Reset filters</button></div>}</div>
<button className="method-link" onClick={()=>setInfo(true)}><Satellite size={16} aria-hidden="true"/>Data & method</button></aside>}
<main className="main"><div className="map-area"><div className="map" ref={container}/>{!sidebar&&<button className="reopen panel" onClick={openSidebar}><Search size={16} aria-hidden="true"/> Search & filters</button>}<div className="map-heading panel"><div className="map-heading-row"><span className="live-label"><span/>Explorer</span><span className="map-breadcrumb">Earth <span>/</span> {selected?selected.country:'Global overview'}</span></div><div className="map-status"><span className="amber-dot"/>Prototype catalog <span>·</span> Pixel analysis pending</div></div>{stylesOpen&&<div className="map-styles panel" id="map-styles" role="group" aria-label="Map style">
  {basemaps.map(b=><button key={b.id} type="button" aria-pressed={basemap===b.id} onClick={()=>{setBasemap(b.id);store('earthsignal.basemap',b.id);if(b.id==='satellite')setSatelliteFailed(false);}}>{b.id==='satellite'?<Satellite size={17} aria-hidden="true"/>:<MapIcon size={17} aria-hidden="true"/>}<span><strong>{b.label}</strong><small>{b.id==='satellite'&&satelliteFailed?'Could not load: offline?':b.hint}</small></span>{basemap===b.id&&<Check size={16} aria-hidden="true"/>}</button>)}
  <label className="switch-row"><span><strong>Country borders</strong></span><input type="checkbox" role="switch" checked={borders} onChange={e=>setBorders(e.target.checked)}/></label>
</div>}
{satelliteFailed&&basemap==='map'&&<div className="map-warning" role="status">Satellite imagery could not load, so the map view is shown. Choose Satellite again under Map style once you are online.</div>}
{mapError&&<div className="map-warning">Some map resources could not load. The event list and navigator remain available.</div>}
<div className="map-controls panel"><button aria-label="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus size={18}/></button><button aria-label="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus size={18}/></button><hr/><button aria-label="Return to world view" onClick={world}><LocateFixed size={17}/></button><button aria-label="Map style" title="Map style" aria-expanded={stylesOpen} aria-controls="map-styles" className={stylesOpen?'active':''} onClick={()=>setStylesOpen(!stylesOpen)}><Layers size={17}/></button></div>
<div className="map-legend panel" role="group" aria-label="Legend: show one event type">{allKinds.map(k=><button key={k} onClick={()=>setKinds([k])} title={`Show only ${categories[k].label.toLowerCase()}`} style={{'--kind':kindStyle[k].color} as React.CSSProperties}><KindIcon kind={k} size={15}/>{categories[k].label}</button>)}</div>
{selected&&!chat&&<section className="detail panel" aria-label="Event brief"><div className="detail-top"><span className="eyebrow">Event brief</span><button className="icon-button" aria-label="Close event" onClick={()=>{setSelected(null);setGuide(-1);}}><X size={17}/></button></div><span className="tag" style={{'--kind':kindStyle[selected.kind].color} as React.CSSProperties}><KindIcon kind={selected.kind} size={16}/>{categories[selected.kind].label}</span><h2>{selected.title}</h2><div className="detail-location">{selected.country} <span>·</span> {fmt(selected.date)}</div><div className={'data-badge '+(selected.catalogVerified?'documented':'demo')}>{selected.catalogVerified?<><BadgeCheck size={18}/>Documented candidate · analysis pending</>:<><FlaskConical size={18}/>Demo scenario · illustrative metadata</>}</div><p>{selected.description}</p>{selected.observations&&<div className="observation-pair"><span className="eyebrow">NISAR observation dates</span><div>{selected.observations.map((d,i)=><React.Fragment key={d}>{i>0&&<ArrowRight size={18}/>}<span className="obs-date"><small>{selected.observations!.length===2?(i===0?'Earlier':'Later'):`Scene ${i+1}`}</small><strong>{fmt(d)}</strong></span></React.Fragment>)}</div></div>}<div className="analysis-empty"><Satellite size={21}/><div><strong>Ready for a closer look?</strong><p>Before / after layers and measured statistics will appear when the team selects and processes a case study.</p></div></div>{selected.source&&<a className="source-link" href={selected.source} target="_blank" rel="noreferrer">Read the reference <ExternalLink size={13}/></a>}<button className="primary-button" onClick={()=>{setGuide(0);}}>Explore with Orbit <Sparkles size={15}/></button></section>}
{guide>=0&&<section className="guide panel" aria-live="polite"><div className="guide-head"><Sparkles size={14}/><span>Orbit’s field notes · step {guide+1} of 3</span><button aria-label="Close guide" onClick={()=>setGuide(-1)}><X size={15}/></button></div><div className="guide-steps" aria-hidden="true">{[0,1,2].map(i=><span key={i} className={i<=guide?'done':''}/>)}</div><h3>{['Start with context','Check the observations','Interpret with evidence'][guide]}</h3><p>{guideText[guide]}</p><div className="guide-actions"><button disabled={guide===0} onClick={()=>setGuide(guide-1)}><ArrowLeft size={14}/> Back</button><button onClick={()=>guide===2?setGuide(-1):setGuide(guide+1)}>{guide===2?'Finish':'Next'}<ArrowRight size={14}/></button></div></section>}
{!chat&&<div className="astronaut-widget"><button onClick={openChat} aria-label="Chat with Orbit, your exploration guide"><Astronaut/><span>Ask Orbit <Sparkles size={12}/></span></button></div>}
{chat&&<section className="chat panel" aria-label="Orbit chat"><div className="chat-header"><div className="chat-avatar"><Astronaut/></div><div><strong>Orbit</strong><small><span/> Your exploration guide</small></div><button aria-label="Close chat" className="icon-button" onClick={()=>setChat(false)}><X size={18}/></button></div><div className="chat-notice">{orbitStatus.available?'Local AI · '+orbitStatus.model:'LM Studio · disconnected'} <button onClick={()=>void refreshModel()} aria-label="Refresh model status"><RotateCcw size={12}/></button></div><div className="model-status" role="status">{orbitStatus.message}</div>{selected&&<div className="chat-event" style={{'--kind':kindStyle[selected.kind].color} as React.CSSProperties}><span className="row-icon"><KindIcon kind={selected.kind} size={16}/><span className="sr-only">{categories[selected.kind].label}: </span></span><span><strong>{selected.title}</strong><small>{selected.country} · {selected.catalogVerified?'Documented candidate · analysis pending':'Demo scenario · illustrative'}</small></span><button onClick={()=>setChat(false)}>View brief</button></div>}<div className="messages" aria-live="polite" ref={messagesEl}>{messages.map((m,i)=><div className={'message '+m.role} key={i}>{m.text}</div>)}{busy&&<div className="message assistant thinking"><span>Orbit is searching the local catalog… <span className="elapsed">{Math.max(0,Math.floor((Date.now()-busySince)/1000))} s</span></span><button onClick={()=>abort.current?.abort()}>Cancel</button></div>}{chatError&&<div className="chat-error" role="alert">{chatError}</div>}{sources.length>0&&<div className="chat-sources">{sources.map(source=><a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}<ExternalLink size={10}/></a>)}</div>}</div><div className="suggestions">{['Wildfires in Spain','Floods in Mozambique',selected?'Guide me':'Show earthquakes'].map(t=><button key={t} disabled={busy} onClick={()=>void ask(t)}>{t}<ArrowUpRight size={11}/></button>)}</div><form onSubmit={e=>{e.preventDefault();ask(input);}}><textarea aria-label="Message Orbit" rows={2} maxLength={8000} value={input} onChange={e=>setInput(e.target.value)} disabled={busy} placeholder="Ask in your language… (Enter to send, Shift+Enter for a new line)" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void ask(input);}}}/><button disabled={!input.trim()||busy} aria-label="Send message"><Send size={16}/></button></form></section>}
</div><section className={'bottom-panel'+(statsOpen?'':' collapsed')} aria-label="Map statistics"><div className="bottom-bar"><button className="bottom-toggle" aria-expanded={statsOpen} aria-controls="bottom-stats" onClick={()=>setStatsOpen(!statsOpen)} title={statsOpen?'Collapse statistics':'Expand statistics'}><ChevronDown size={16}/><span>{selected?'Selected event':'Your window on Earth'}</span></button><span className="scope"><LocateFixed size={13}/>{selected?'Metadata only':'Current map view'}</span>{!statsOpen&&<span className="bottom-summary"><b>{visible.length}</b> of {filtered.length} in view<i>·</i><b>{documentedVisible}</b> documented<i>·</i>no completed analyses</span>}</div>
{statsOpen&&<div className="bottom-content" id="bottom-stats"><div className="stats"><div className="stat" title="Filtered catalog entries located inside the current map view"><strong>{pad2(visible.length)}<small>/{filtered.length}</small></strong><span><b>Visible entries</b><small>In the current map view</small></span></div><div className="stat"><strong>{pad2(documentedVisible)}</strong><span><b>Documented candidates</b><small>Analysis pending</small></span></div><div className="stat"><strong className="muted-number">—</strong><span><b>Completed analyses</b><small>Case study not yet selected</small></span></div></div>
<div className="timeline" title="Catalog entries per month in the selected date range. These are not satellite measurements."><div className="timeline-title"><span>Catalog activity</span><small>{months.length?`${monthName(months[0].y,months[0].m,'short')} – ${monthName(months[months.length-1].y,months[months.length-1].m,'short')}`:''}</small></div><div className="bars">{months.map(({y,m},i)=><button key={y+'-'+m} className={monthly[i]?'has-data':''} title={`${monthName(y,m)}: ${monthly[i]} catalog ${monthly[i]===1?'entry':'entries'}. Click to filter.`} aria-label={`${monthName(y,m)}: ${monthly[i]} entries`} onClick={()=>{setFrom(`${y}-${String(m).padStart(2,'0')}-01`);setTo(`${y}-${String(m).padStart(2,'0')}-${new Date(Date.UTC(y,m,0)).getUTCDate()}`);}}><i style={{height:`${Math.max(3,monthly[i]/Math.max(1,...monthly)*24)}px`}}/><span>{'JFMAMJJASOND'[m-1]}</span></button>)}</div></div></div>}</section></main></div>
{info&&<div className="modal-backdrop" onClick={()=>setInfo(false)}><section className="modal panel" role="dialog" aria-modal="true" aria-label="About EarthSignal" onClick={e=>e.stopPropagation()}><button className="modal-close icon-button" onClick={()=>setInfo(false)} aria-label="Close information"><X size={20}/></button><span className="brand-logo" aria-hidden="true"/><span className="eyebrow">Dancing with the SARs</span><h2>Every change<br/>has a story.</h2><p>EarthSignal is a first-version explorer created for NASA International Space Apps Challenge 2026. It helps people discover how radar observations can reveal changes on Earth.</p><div className="info-grid"><div><strong>{events.filter(e=>e.catalogVerified).length.toString().padStart(2,'0')}</strong><span>Documented study candidates</span></div><div><strong>{events.filter(e=>!e.catalogVerified).length.toString().padStart(2,'0')}</strong><span>Illustrative catalog scenarios</span></div></div><p><strong>Data status:</strong> no case study has been selected or processed. The application does not display computed NISAR rasters, surface-change measurements or real-time alerts. Scenario dates and locations are illustrative.</p><p><strong>Event dates</strong> are when the event happened (UTC), not when the satellite observed it.</p><p><strong>Orbit:</strong> Orbit uses a local LM Studio model to search the SQLite catalog and navigate the map. No prompts or event records are sent to an external AI provider. Validated before/after analysis is a subsequent integration.</p><a className="source-link" target="_blank" rel="noreferrer" href="https://nisar-docs.asf.alaska.edu/">Explore NISAR documentation <ExternalLink size={14}/></a><button className="primary-button" onClick={()=>setInfo(false)}>Start exploring <ArrowRight size={15}/></button></section></div>}
</div>
}

