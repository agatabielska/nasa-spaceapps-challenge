import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Astronaut} from './Astronaut';
import * as maplibregl from 'maplibre-gl';
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(mapWorkerUrl);
import 'maplibre-gl/dist/maplibre-gl.css';
import {ArrowUpRight,ArrowLeft,ArrowRight,Search,X,ChevronDown,Layers,Map as MapIcon,Plus,Minus,Check,LocateFixed,Send,Sparkles,ExternalLink,Info,PanelLeftClose,Menu,RotateCcw,Satellite,ALargeSmall,CalendarDays,SlidersHorizontal,Clock,Play,Images,Newspaper} from 'lucide-react';
import {categories,filterEvents,inBounds,lonSpan,type Kind,type EventRecord} from './domain';
import {KindIcon,kindStyle} from './eventKinds';
import './explorer.css';
import {loadCatalog,loadOrbitStatus,sendOrbit,APIError,type OrbitStatus} from './api';
import {analyses} from './analyses';
const allKinds=Object.keys(categories) as Kind[];
const fmt=(d:string)=>new Date(d+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
const reducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const motion=(ms:number)=>reducedMotion()?0:ms;
// Matches the CSS breakpoint where the sidebar becomes an overlay: only one large panel may be open there.
const narrow=()=>window.innerWidth<=640;
const noPadding={top:0,bottom:0,left:0,right:0};
const DEFAULT_FROM='2025-11-01',DEFAULT_TO='2026-11-30';
function catastropheName(e:EventRecord):string{
  if(e.id==='etna')return 'Etna';
  if(e.id==='mozambique')return 'Limpopo';
  if(e.id==='hubbard')return 'Hubbard Glacier';
  if(e.title.includes('·')){
    const parts=e.title.split('·').map(s=>s.trim());
    const isType=(s:string)=>/volcan|erupt|flood|fire|forest|earthquake|ground|glacier|surface/i.test(s);
    const nonType=parts.find(p=>!isType(p));
    if(nonType)return nonType;
    return parts[parts.length-1];
  }
  return e.country||e.title;
}
const fmtShort=(d:string)=>new Date(d+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'2-digit'});
const pad2=(n:number)=>n.toString().padStart(2,'0');
const coords=([lon,lat]:[number,number])=>`${Math.abs(lat).toFixed(2)}° ${lat>=0?'N':'S'}, ${Math.abs(lon).toFixed(2)}° ${lon>=0?'E':'W'}`;
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
const [search,setSearch]=useState(''),[kinds,setKinds]=useState<Kind[]>(allKinds),[from,setFrom]=useState(DEFAULT_FROM),[to,setTo]=useState(DEFAULT_TO),[verified,setVerified]=useState(false),[viewOnly,setViewOnly]=useState(false),[bounds,setBounds]=useState<[number,number,number,number]|null>(null),[selected,setSelected]=useState<EventRecord|null>(null),[chat,setChat]=useState(false),[sidebar,setSidebar]=useState(false),[info,setInfo]=useState(false),[analysis,setAnalysis]=useState<EventRecord|null>(null),[tab,setTab]=useState(0),[guide,setGuide]=useState(-1),[input,setInput]=useState(''),[messages,setMessages]=useState<{role:string;text:string}[]>([{role:'assistant',text:'Hi, I’m Orbit. Ask me about a place or an event.'}]),[mapReady,setMapReady]=useState(false),[mapError,setMapError]=useState(false);
const [events,setEvents]=useState<EventRecord[]>([]),[catalogLoading,setCatalogLoading]=useState(true),[catalogError,setCatalogError]=useState(''),[busy,setBusy]=useState(false),[chatError,setChatError]=useState(''),[sources,setSources]=useState<{title:string;url:string}[]>([]),[orbitIds,setOrbitIds]=useState<string[]|null>(null),[orbitStatus,setOrbitStatus]=useState<OrbitStatus>({available:false,model:null,models:[],message:'Checking LM Studio…'}),[mapLoaded,setMapLoaded]=useState(false),[basemap,setBasemap]=useState<Basemap>(()=>stored('earthsignal.basemap','satellite')),[borders,setBorders]=useState(()=>stored('earthsignal.borders',true)),[stylesOpen,setStylesOpen]=useState(false),[satelliteFailed,setSatelliteFailed]=useState(false),[busySince,setBusySince]=useState(0),[,setTick]=useState(0),[statsOpen,setStatsOpen]=useState(()=>stored('earthsignal.statsOpen',false)),[moreOpen,setMoreOpen]=useState(()=>stored('earthsignal.moreFilters',false)),[customDates,setCustomDates]=useState(false),[dateOpen,setDateOpen]=useState(false),[textSize,setTextSize]=useState<TextSize>(()=>stored('earthsignal.textSize','auto'));
const revision=useRef(0),session=useRef<string|null>(null),snapshot=useRef<Snapshot|null>(null),abort=useRef<AbortController|null>(null),prevSelected=useRef<string|null>(null),initialFit=useRef(false),escape=useRef<()=>void>(()=>{});
async function refreshCatalog(){setCatalogLoading(true);setCatalogError('');try{const result=await loadCatalog();setEvents(result.events);}catch(e){setCatalogError(e instanceof Error?e.message:'Catalog unavailable');}finally{setCatalogLoading(false);}}
async function refreshModel(){try{setOrbitStatus(await loadOrbitStatus());}catch(e){setOrbitStatus({available:false,model:null,models:[],message:e instanceof Error?e.message:'Local API unavailable'});}}
useEffect(()=>{void refreshCatalog();void refreshModel();const timer=setInterval(()=>void refreshModel(),15000);return()=>clearInterval(timer);},[]);
useEffect(()=>{revision.current++;},[search,kinds,from,to,verified,viewOnly,bounds,selected?.id]);
const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null),messagesEl=useRef<HTMLDivElement>(null);
// Orbit results keep the order the assistant returned, so "the second one" matches what the user sees.
// Documented events (catalogVerified) are prioritized first in the list.
const filtered=useMemo(()=>{
  const list=filterEvents(events,search,kinds,from,to,verified,viewOnly?bounds:null);
  const sorted=[...list].sort((a,b)=>{
    if(a.catalogVerified!==b.catalogVerified)return a.catalogVerified?-1:1;
    return b.date.localeCompare(a.date);
  });
  return orbitIds===null?sorted:sorted.filter(e=>orbitIds.includes(e.id)).sort((a,b)=>orbitIds.indexOf(a.id)-orbitIds.indexOf(b.id));
},[events,search,kinds,from,to,verified,viewOnly,bounds,orbitIds]);
const visible=filtered.filter(e=>inBounds(e.coordinates,bounds));
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
// The overview shows the whole globe, turned towards the events that have an analysis (Europe to the Himalaya).
function overview(duration=800){const m=map.current,c=container.current;if(!m||!c)return;const size=Math.max(240,Math.min(c.clientHeight,c.clientWidth)*.84);m.flyTo({center:[42,30],zoom:Math.log2(size*Math.PI/512),padding:noPadding,duration:motion(duration)});}
function fitEvents(list:EventRecord[],duration=800){const m=map.current;const span=lonSpan(list.map(e=>e.coordinates[0]));if(!m||!span)return;const lats=list.map(e=>e.coordinates[1]);m.fitBounds([[span[0],Math.min(...lats)],[span[1],Math.max(...lats)]],{padding:fitPadding(),absolutePadding:true,maxZoom:5,duration:motion(duration)});}
useEffect(()=>{if(!container.current)return;try{const m=new maplibregl.Map({container:container.current,style:{version:8,projection:{type:'globe'},sky:{'atmosphere-blend':['interpolate',['linear'],['zoom'],0,1,4,1,6,0]},sources:{countries:{type:'geojson',data:'/countries.geojson'},satellite:{type:'raster',tiles:[SATELLITE_TILES],tileSize:256,maxzoom:19,attribution:'Imagery © Esri, Maxar, Earthstar Geographics'}},layers:[{id:'ocean',type:'background',paint:{'background-color':'#050d1f'}},{id:'satellite',type:'raster',source:'satellite',layout:{visibility:basemap==='satellite'?'visible':'none'},paint:{'raster-brightness-max':.88,'raster-saturation':-.1,'raster-fade-duration':200}},{id:'land',type:'fill',source:'countries',layout:{visibility:basemap==='map'?'visible':'none'},paint:{'fill-color':'#16294d','fill-opacity':1}},{id:'borders',type:'line',source:'countries',layout:{visibility:borders?'visible':'none'},paint:{'line-color':borderPaint[basemap].color,'line-width':0.7,'line-opacity':borderPaint[basemap].opacity}}]},center:[35,38],zoom:2.1,maxZoom:12,minZoom:.6,attributionControl:{compact:true,customAttribution:'<a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer">Natural Earth</a>'},pitchWithRotate:false,dragRotate:false});map.current=m;if(import.meta.env.DEV)(window as unknown as {__earthsignalMap:maplibregl.Map}).__earthsignalMap=m;setMapReady(true);m.on('load',()=>{setMapReady(true);setMapLoaded(true);const b=m.getBounds();setBounds([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);});m.on('moveend',()=>{const b=m.getBounds();setBounds([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);});m.on('error',e=>{if((e as {sourceId?:string}).sourceId==='satellite')setSatelliteFailed(true);else setMapError(true);});const resize=new ResizeObserver(()=>m.resize());resize.observe(container.current);return()=>{resize.disconnect();m.remove();map.current=null;};}catch{setMapError(true);}},[]);
// Markers are buttons with the event type's SVG icon, rendered by a small React root that is unmounted (after
// the current commit) when the markers are rebuilt or the map goes away.
useEffect(()=>{const m=map.current;if(!m||!mapReady)return;
  const made=[...filtered].sort((a,b)=>+a.analysisAvailable-+b.analysisAvailable).map(e=>{
    const el=document.createElement('button');el.type='button';el.className='map-marker'+(e.analysisAvailable?'':' inactive')+(selected?.id===e.id?' selected':'');
    el.style.setProperty('--marker',kindStyle[e.kind].color);
    el.setAttribute('aria-label',`${e.title}: ${categories[e.kind].label}, ${e.analysisAvailable?'analysis available':'coming soon'}`);el.title=e.title;el.onclick=()=>select(e);
    const root=createRoot(el);root.render(<KindIcon kind={e.kind} size={selected?.id===e.id?24:e.analysisAvailable?20:15}/>);
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
useEffect(()=>{if(!dateOpen)return;const close=(e:PointerEvent)=>{const t=e.target as Element;if(!t.closest('.date-picker-anchor'))setDateOpen(false);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[dateOpen]);
useEffect(()=>store('earthsignal.borders',borders),[borders]);
// Start with every catalog hotspot in view, clear of the overlays.
useEffect(()=>{if(mapLoaded&&events.length&&!initialFit.current){initialFit.current=true;overview(0);}},[mapLoaded,events]);
useEffect(()=>{const m=map.current;if(!m)return;if(!selected){prevSelected.current=null;return;}const first=prevSelected.current!==selected.id;prevSelected.current=selected.id;if(first)m.flyTo({center:selected.coordinates,zoom:4.5,padding:focusPadding(),duration:motion(1000)});else m.easeTo({center:selected.coordinates,padding:focusPadding(),duration:motion(400)});},[selected]);
useEffect(()=>{if(selected&&!filtered.some(e=>e.id===selected.id)){setSelected(null);}},[filtered,selected]);
// When the side panel would cover the map heading (narrow map or large text), drop it below the heading.
useLayoutEffect(()=>{const area=container.current?.parentElement;if(!area)return;const check=()=>{const h=area.querySelector('.map-heading')?.getBoundingClientRect(),panel=area.querySelector('.detail,.chat')?.getBoundingClientRect();area.classList.toggle('panels-low',!!h&&!!panel&&panel.left<h.right+12);};check();window.addEventListener('resize',check);return()=>window.removeEventListener('resize',check);});
// Scroll only the message list; scrollIntoView would also scroll the clipped app shell.
useEffect(()=>{const el=messagesEl.current;if(el)el.scrollTo({top:el.scrollHeight,behavior:motion(1)?'smooth':'auto'});},[messages,busy,chatError,sources,chat]);
useEffect(()=>{if(!busy)return;const t=setInterval(()=>setTick(x=>x+1),1000);return()=>clearInterval(t);},[busy]);
escape.current=()=>{if(stylesOpen)setStylesOpen(false);else if(info)setInfo(false);else if(analysis)setAnalysis(null);else if(chat)setChat(false);else if(selected)world();else if(narrow()&&sidebar)setSidebar(false);};
useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if(e.key==='Escape')escape.current();};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);},[]);
function reset(){setOrbitIds(null);setSearch('');setKinds(allKinds);setFrom(DEFAULT_FROM);setTo(DEFAULT_TO);setVerified(false);setViewOnly(false);setCustomDates(false);setDateOpen(false);}
/** Remember the camera and filters once, before the first step away from the overview. */
function remember(){const m=map.current;if(snapshot.current||!m)return;const c=m.getCenter();snapshot.current={center:[c.lng,c.lat],zoom:m.getZoom(),search,kinds,from,to,verified,viewOnly,orbitIds};}
// Clicking an event (marker or list row) shows its card, so the chat steps aside; events Orbit itself opens keep the chat.
function select(e:EventRecord){remember();setSelected(e);setGuide(-1);setChat(false);if(narrow())setSidebar(false);}
function closeSelected(){snapshot.current=null;setSelected(null);setGuide(-1);fitEvents(events,1100);}
/** Back to the world: restore the camera and filters from before the event was opened. */
function world(){closeSelected();}
/** Full reset to the initial overview. */
function home(){snapshot.current=null;reset();setSelected(null);overview();}
function openAnalysis(e:EventRecord){if(!analyses[e.id])return;setTab(0);setAnalysis(e);setChat(false);}
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
  if(started!==revision.current){setChatError('The globe moved while Orbit was answering. Ask again.');return;}
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
      setSelected(event);if(action.type==='start_guide')openAnalysis(event);
    }else if(action.type==='reset_map')home();
  }
}catch(e){
  if(e instanceof APIError&&e.code==='SESSION_EXPIRED')session.current=null;
  setChatError(e instanceof APIError&&e.code==='CANCELLED'?'Cancelled.':e instanceof APIError&&e.code==='SESSION_EXPIRED'?'Please ask again.':'Orbit is offline right now.');
}
finally{setBusy(false);abort.current=null;}
}
useEffect(()=>store('earthsignal.statsOpen',statsOpen),[statsOpen]);
useEffect(()=>store('earthsignal.moreFilters',moreOpen),[moreOpen]);
useEffect(()=>store('earthsignal.textSize',textSize),[textSize]);
// Overlays change size with the text setting: re-fit the overview once the new layout is in place.
useEffect(()=>{if(!mapLoaded)return;const t=setTimeout(()=>{map.current?.resize();if(!selected)overview(300);},60);return()=>clearTimeout(t);},[textSize]);
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
const analysedCount=events.filter(e=>e.analysisAvailable).length;
const study=selected?analyses[selected.id]:undefined,open=analysis?analyses[analysis.id]:undefined;
return <div className="app" data-text={textSize}>
<header className="topbar">
  <a className="brand" href="/" aria-label="EarthSignal, back to the journey"><span className="brand-logo" aria-hidden="true"/><span><b>EarthSignal</b><small>App</small></span></a>
  <div className="top-right">
    <a className="top-link" href="/">The journey <ArrowUpRight size={15} aria-hidden="true"/></a>
    <button className="icon-button mobile-menu" aria-label={sidebar?'Close search and filters':'Open search and filters'} aria-expanded={sidebar} onClick={()=>sidebar?setSidebar(false):openSidebar()}><Menu size={19}/></button>
    <button className="text-size" onClick={()=>setTextSize(textSizes[textSize].next)} aria-label={`Text size: ${textSizes[textSize].label}. Change text size`} title="Text size for presentations"><ALargeSmall size={18} aria-hidden="true"/><span>{textSizes[textSize].label}</span></button>
    <button className="icon-button" onClick={()=>setInfo(true)} aria-label="About EarthSignal, data and method" title="About, data and method"><Info size={18}/></button>
  </div>
</header>
<div className="workspace">{sidebar&&<aside className="sidebar" aria-label="Search and filters">
<div className="kind-filter" role="group" aria-label="Filters">
  {allKinds.map(k=><button key={k} type="button" aria-pressed={kinds.includes(k)} aria-label={categories[k].label} data-tooltip={categories[k].label} className="kind-chip" style={{'--kind':kindStyle[k].color} as React.CSSProperties} onClick={()=>toggleKind(k)}><KindIcon kind={k} size={20}/></button>)}
  <div className="filter-divider" aria-hidden="true"/>
  <div className="date-picker-anchor">
    <button type="button" aria-label="Filter by date" aria-expanded={dateOpen} data-tooltip={from===DEFAULT_FROM&&to===DEFAULT_TO?'Filter by date':`${fmtShort(from)} – ${fmtShort(to)}`} className={'kind-chip calendar-chip'+(from!==DEFAULT_FROM||to!==DEFAULT_TO?' active':'')} onClick={()=>setDateOpen(!dateOpen)}><CalendarDays size={18}/></button>
    {dateOpen&&<div className="date-popover panel" role="dialog" aria-label="Date range">
      <div className="date-preset-list">
        {presets.map(p=><button key={p.label} className={p.from===from&&p.to===to&&!customDates?'active':''} onClick={()=>{setFrom(p.from);setTo(p.to);setCustomDates(false);setDateOpen(false);}}>{p.label}</button>)}
        <button className={customDates?'active':''} onClick={()=>setCustomDates(true)}>Custom range…</button>
      </div>
      {customDates&&<div className="date-inputs">
        <label><span>From</span><input type="date" value={from} max={to} onChange={e=>{const v=e.target.value;if(!v)return;setFrom(v);if(v>to)setTo(v);}}/></label>
        <label><span>To</span><input type="date" value={to} min={from} onChange={e=>{const v=e.target.value;if(!v)return;setTo(v);if(v<from)setFrom(v);}}/></label>
      </div>}
    </div>}
  </div>
  <button type="button" className="kind-chip collapse-chip" aria-label="Collapse search and filters" data-tooltip="Collapse filters" onClick={()=>setSidebar(false)}><PanelLeftClose size={18}/></button>
</div>
{narrowed&&<button className="reset-link" onClick={reset}><RotateCcw size={13} aria-hidden="true"/>Reset filters</button>}
{orbitIds!==null&&<button className="orbit-chip" onClick={()=>setOrbitIds(null)} aria-label={`Remove Orbit's limit to ${orbitIds.length} results`}><Sparkles size={13} aria-hidden="true"/><span>Orbit picked {orbitIds.length} {orbitIds.length===1?'result':'results'}</span><X size={13} aria-hidden="true"/></button>}
<label className="search-box"><Search size={16} aria-hidden="true"/><input aria-label="Search" placeholder="Search" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="Clear search" onClick={()=>setSearch('')}><X size={15}/></button>}</label>
<div className="event-list">{catalogLoading?<div className="empty-list">Loading local database…</div>:catalogError?<div className="empty-list" role="alert">{catalogError}<button onClick={()=>void refreshCatalog()}>Retry</button></div>:filtered.length?filtered.map(e=><button className={'event-row'+(selected?.id===e.id?' active':'')} key={e.id} onClick={()=>select(e)} data-tooltip={e.title} style={{'--kind':kindStyle[e.kind].color} as React.CSSProperties}><span className="row-icon"><KindIcon kind={e.kind} size={16}/><span className="sr-only">{categories[e.kind].label}: </span></span><span className="row-text"><strong>{catastropheName(e)}</strong><span className="row-meta">{e.country} · {fmtShort(e.date)}</span></span></button>):<div className="empty-list">No events match these filters.<button onClick={reset}>Reset filters</button></div>}</div>
<button className="method-link" onClick={()=>setInfo(true)}><Satellite size={16} aria-hidden="true"/>Data & method</button></aside>}
<main className="main"><div className="map-area"><div className="map" ref={container}/>{!sidebar&&<button type="button" className="reopen" onClick={openSidebar} aria-label="Open search and filters" title="Filters"><SlidersHorizontal size={18} color="#ffffff" aria-hidden="true"/></button>}<div className="map-heading panel"><div className="map-heading-row"><span className="live-label"><span/>Explorer</span><span className="map-breadcrumb">Earth <span>/</span> {selected?selected.country:'Global overview'}</span></div><div className="map-status"><span className="amber-dot"/>{analysedCount} analysed events <span>·</span> more coming soon</div></div>{stylesOpen&&<div className="map-styles panel" id="map-styles" role="group" aria-label="Map style">
  {basemaps.map(b=><button key={b.id} type="button" aria-pressed={basemap===b.id} onClick={()=>{setBasemap(b.id);store('earthsignal.basemap',b.id);if(b.id==='satellite')setSatelliteFailed(false);}}>{b.id==='satellite'?<Satellite size={17} aria-hidden="true"/>:<MapIcon size={17} aria-hidden="true"/>}<span><strong>{b.label}</strong><small>{b.id==='satellite'&&satelliteFailed?'Could not load: offline?':b.hint}</small></span>{basemap===b.id&&<Check size={16} aria-hidden="true"/>}</button>)}
  <label className="switch-row"><span><strong>Country borders</strong></span><input type="checkbox" role="switch" checked={borders} onChange={e=>setBorders(e.target.checked)}/></label>
</div>}
{satelliteFailed&&basemap==='map'&&<div className="map-warning" role="status">Satellite imagery could not load, so the map view is shown. Choose Satellite again under Map style once you are online.</div>}
{mapError&&<div className="map-warning">Some map resources could not load. The event list and navigator remain available.</div>}
<div className="map-controls panel"><button aria-label="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus size={18}/></button><button aria-label="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus size={18}/></button><hr/><button aria-label="Return to world view" onClick={closeSelected}><LocateFixed size={17}/></button><button aria-label="Map style" title="Map style" aria-expanded={stylesOpen} aria-controls="map-styles" className={stylesOpen?'active':''} onClick={()=>setStylesOpen(!stylesOpen)}><Layers size={17}/></button></div>
<div className="map-legend panel" role="group" aria-label="Legend: show one event type">{allKinds.map(k=><button key={k} onClick={()=>setKinds([k])} title={`Show only ${categories[k].label.toLowerCase()}`} style={{'--kind':kindStyle[k].color} as React.CSSProperties}><KindIcon kind={k} size={15}/>{categories[k].label}</button>)}</div>
{selected&&!chat&&(selected.analysisAvailable&&study?<section className="detail panel" aria-label="Event"><div className="detail-top"><span className="tag" style={{'--kind':kindStyle[selected.kind].color} as React.CSSProperties}><KindIcon kind={selected.kind} size={16}/>{categories[selected.kind].label}</span><button className="icon-button" aria-label="Close event" onClick={closeSelected}><X size={17}/></button></div><h2>{selected.title}</h2><div className="detail-location">{selected.country} <span>·</span> {fmt(selected.date)}</div><p>{selected.description}</p><ul className="facts">{study.facts.map(f=><li key={f.label}><strong>{f.value}</strong><span>{f.label}</span></li>)}</ul><button className="primary-button" onClick={()=>openAnalysis(selected)}>Open full analysis <ArrowRight size={16}/></button></section>
:<section className="detail panel soon" aria-label="Event, coming soon"><div className="detail-top"><span className="tag" style={{'--kind':kindStyle[selected.kind].color} as React.CSSProperties}><KindIcon kind={selected.kind} size={16}/>{categories[selected.kind].label}</span><button className="icon-button" aria-label="Close event" onClick={closeSelected}><X size={17}/></button></div><h2>{selected.title}</h2><dl><div><dt>Date</dt><dd>{fmt(selected.date)}</dd></div><div><dt>Coordinates</dt><dd>{coords(selected.coordinates)}</dd></div></dl><div className="soon-badge"><Clock size={15} aria-hidden="true"/>Coming soon</div></section>)}
{!chat&&<div className="astronaut-widget"><button onClick={openChat} aria-label="Chat with Orbit"><Astronaut/><span>Ask Orbit <Sparkles size={12}/></span></button></div>}
{chat&&<section className="chat panel" aria-label="Orbit chat"><div className="chat-header"><div className="chat-avatar"><Astronaut/></div><strong>Orbit</strong><button aria-label="Close chat" className="icon-button" onClick={()=>setChat(false)}><X size={18}/></button></div><div className="messages" aria-live="polite" ref={messagesEl}>{messages.map((m,i)=><div className={'message '+m.role} key={i}>{m.text}</div>)}{busy&&<div className="message assistant thinking"><span className="dots" aria-label="Orbit is thinking"><i/><i/><i/></span><button onClick={()=>abort.current?.abort()}>Cancel</button></div>}{!busy&&!orbitStatus.available&&!chatError&&<div className="chat-error" role="status">Orbit is offline right now.</div>}{chatError&&<div className="chat-error" role="alert">{chatError}</div>}{sources.length>0&&<div className="chat-sources">{sources.map(source=><a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}<ExternalLink size={10}/></a>)}</div>}</div><div className="suggestions">{['Etna','Wildfire in Spain','Flood in Nepal','Subsidence in Poland'].map(t=><button key={t} disabled={busy} onClick={()=>void ask(t)}>{t}</button>)}</div><form onSubmit={e=>{e.preventDefault();ask(input);}}><textarea aria-label="Message Orbit" rows={1} maxLength={8000} value={input} onChange={e=>setInput(e.target.value)} disabled={busy} placeholder="Ask Orbit…" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void ask(input);}}}/><button disabled={!input.trim()||busy} aria-label="Send message"><Send size={16}/></button></form></section>}
</div><section className={'bottom-panel'+(statsOpen?'':' collapsed')} aria-label="Map statistics"><div className="bottom-bar"><button className="bottom-toggle" aria-expanded={statsOpen} aria-controls="bottom-stats" onClick={()=>setStatsOpen(!statsOpen)} title={statsOpen?'Collapse statistics':'Expand statistics'}><ChevronDown size={16}/><span>Statistics</span></button><span className="scope"><LocateFixed size={13}/>Current view</span>{!statsOpen&&<span className="bottom-summary"><b>{visible.length}</b> of {filtered.length} in view<i>·</i><b>{analysedCount}</b> analysed</span>}</div>
{statsOpen&&<div className="bottom-content" id="bottom-stats"><div className="stats"><div className="stat" title="Filtered catalog entries located inside the current map view"><strong>{pad2(visible.length)}<small>/{filtered.length}</small></strong><span><b>Visible entries</b><small>In the current map view</small></span></div><div className="stat"><strong>{pad2(documentedVisible)}</strong><span><b>Documented events</b><small>With a reference or NISAR dates</small></span></div><div className="stat"><strong>{pad2(analysedCount)}</strong><span><b>Full analyses</b><small>3D tour and figures</small></span></div></div>
<div className="timeline" title="Catalog entries per month in the selected date range. These are not satellite measurements."><div className="timeline-title"><span>Catalog activity</span><small>{months.length?`${monthName(months[0].y,months[0].m,'short')} – ${monthName(months[months.length-1].y,months[months.length-1].m,'short')}`:''}</small></div><div className="bars">{months.map(({y,m},i)=><button key={y+'-'+m} className={monthly[i]?'has-data':''} title={`${monthName(y,m)}: ${monthly[i]} catalog ${monthly[i]===1?'entry':'entries'}. Click to filter.`} aria-label={`${monthName(y,m)}: ${monthly[i]} entries`} onClick={()=>{setFrom(`${y}-${String(m).padStart(2,'0')}-01`);setTo(`${y}-${String(m).padStart(2,'0')}-${new Date(Date.UTC(y,m,0)).getUTCDate()}`);}}><i style={{height:`${Math.max(3,monthly[i]/Math.max(1,...monthly)*24)}px`}}/><span>{'JFMAMJJASOND'[m-1]}</span></button>)}</div></div></div>}</section>
{analysis&&open&&<section className="analysis" aria-label={`Full analysis: ${analysis.title}`}><header className="an-head"><button className="an-back" onClick={()=>setAnalysis(null)}><ArrowLeft size={17} aria-hidden="true"/>Back to the globe</button><div className="an-title"><span className="tag" style={{'--kind':kindStyle[analysis.kind].color} as React.CSSProperties}><KindIcon kind={analysis.kind} size={16}/>{categories[analysis.kind].label}</span><h1>{analysis.title}</h1><small>{analysis.country} · {fmt(analysis.date)} · {coords(analysis.coordinates)}</small></div></header>
<nav className="an-tabs" role="tablist" aria-label="Analysis views"><span className="an-tabs-hint">{open.tabs.length} views</span>{open.tabs.map((t,i)=><button key={t.id} role="tab" aria-selected={tab===i} onClick={()=>setTab(i)}><b>{i+1}</b>{t.frame?<Play size={16} aria-hidden="true"/>:t.press?<Newspaper size={16} aria-hidden="true"/>:<Images size={16} aria-hidden="true"/>}{t.label}</button>)}</nav>
{open.tabs[tab]?.frame?<iframe key={open.tabs[tab].frame} className="an-frame" src={open.tabs[tab].frame} title={`${analysis.title}: ${open.tabs[tab].label}`} allow="fullscreen"/>:open.tabs[tab]?.press?<div className="an-figures"><div className="an-intro"><h2>In the news</h2><p>{open.tabs[tab].press!.intro}</p></div><ul className="an-press">{open.tabs[tab].press!.links.map(l=><li key={l.url}><a href={l.url} target="_blank" rel="noreferrer"><small>{l.source} · {l.date}</small><strong>{l.title}<ExternalLink size={16} aria-hidden="true"/></strong><span>{l.note}</span></a></li>)}</ul></div>:<div className="an-figures"><div className="an-intro"><h2>In short</h2><p>{open.headline}</p><ul className="facts">{open.facts.map(f=><li key={f.label}><strong>{f.value}</strong><span>{f.label}</span></li>)}</ul></div>{open.tabs[tab]?.figures?.map(f=><figure key={f.title}><figcaption><h2>{f.title}</h2><p>{f.caption}</p></figcaption>{f.pair?<div className="an-pair">{f.pair.map(x=><a key={x.src} href={x.src} target="_blank" rel="noreferrer"><img src={x.src} alt={x.label} loading="lazy"/><span>{x.label}</span></a>)}</div>:<a href={f.src} target="_blank" rel="noreferrer"><img src={f.src} alt={f.title} loading="lazy"/></a>}</figure>)}</div>}</section>}
</main></div>
{info&&<div className="modal-backdrop" onClick={()=>setInfo(false)}><section className="modal panel" role="dialog" aria-modal="true" aria-label="About EarthSignal" onClick={e=>e.stopPropagation()}><button className="modal-close icon-button" onClick={()=>setInfo(false)} aria-label="Close information"><X size={20}/></button><span className="brand-logo" aria-hidden="true"/><span className="eyebrow">Dancing with the SARs</span><h2>Every change<br/>has a story.</h2><p>EarthSignal was created for the NASA International Space Apps Challenge 2026. It shows how NISAR radar observations reveal changes on Earth, on examples anyone can explore.</p><div className="info-grid"><div><strong>{pad2(analysedCount)}</strong><span>Events with a full analysis</span></div><div><strong>{pad2(events.length-analysedCount)}</strong><span>Events coming soon</span></div></div><p><strong>Analyses:</strong> Etna, the Ávila wildfire, the Rasuwa flood and mining subsidence in Poland are computed from NISAR data and open as a 3D tour with figures. Greyed-out events are placeholders for analyses still to come; some of them are illustrative examples, not records of real disasters.</p><p><strong>Event dates</strong> are when the event happened (UTC), not when the satellite observed it.</p><p><strong>Orbit</strong> is a guide that runs on this computer and finds events on the globe. In the future it will be able to find any event and run the analysis for it.</p><a className="source-link" target="_blank" rel="noreferrer" href="https://nisar-docs.asf.alaska.edu/">Explore NISAR documentation <ExternalLink size={14}/></a><button className="primary-button" onClick={()=>setInfo(false)}>Start exploring <ArrowRight size={15}/></button></section></div>}
</div>
}

