// Landing-page case studies. Web assets live in public/media/cases/<id>/ and are derived from
// data/event_visualisation/ (not tracked in git); `source` names the original file for each asset.
export type CaseLayer={id:string;label:string;hint:string;color:string;src:string;source:string;on?:boolean};
export type CaseImage={src:string;source:string;label:string;date?:string;alt:string};
export type CaseStudy={
  id:'spain'|'etna'|'nepal';index:string;kind:string;title:string;place:string;eventDate:string;
  summary:string;stats:{value:string;unit?:string;label:string}[];notes:string[];
  width:number;height:number;before:CaseImage;after:CaseImage;layers:CaseLayer[];look:CaseLook;
};
// How a case is dressed on the landing page (prototype style): big region word and sub-title, colour theme,
// and the labels on the frame around its visualization.
export type CaseLook={region:string;sub:string;code:string;theme:'fire'|'ice';panel:string;status:string;caption:string};
const BOTH='#ff5fd2',BRIGHT='#ffa94d',COHERENCE='#4dc9ff';
const composite='NISAR radar composite, not a natural-colour photograph.';

export const spain:CaseStudy={
  look:{region:'Spain',sub:'Wildfire',code:'ES',theme:'fire',panel:'SAR difference',status:'Signal visualization',caption:'Wildfire change detection'},
  id:'spain',index:'01',kind:'Forest wildfire',title:'Ávila wildfire',place:'Near Burgohondo, Spain',eventDate:'22 July 2026',
  summary:'A wildfire broke out near Burgohondo in the province of Ávila. Burnt vegetation scatters radar differently from living forest, so the burn scar appears as a change in radar brightness between two NISAR passes.',
  stats:[{value:'108.5',unit:'km²',label:'Radar-brightness change detected by our model'},{value:'36',unit:'days',label:'Between passes: 21 Jul → 26 Aug 2026'}],
  notes:['One detection method (radar brightness) was available for this case, so there is no two-method confirmation.'],
  width:1600,height:1158,
  before:{src:'/media/cases/spain/before.webp',source:'data/event_visualisation/Spain/spain_fire_v2/BEFORE.jpg',label:'Before',date:'21 Jul 2026',alt:`Radar view of the Ávila area on 21 July 2026, before the wildfire. ${composite}`},
  after:{src:'/media/cases/spain/after.webp',source:'data/event_visualisation/Spain/spain_fire_v2/AFTER.jpg',label:'After',date:'26 Aug 2026',alt:`Radar view of the same area on 26 August 2026, after the wildfire. ${composite}`},
  layers:[{id:'backscatter',label:'Radar-brightness change',hint:'GCOV backscatter · 108.5 km²',color:BRIGHT,src:'/media/cases/spain/backscatter.webp',source:'data/event_visualisation/Spain/spain_fire_v2/mask_backscatter.png',on:true}],
};

export const etna:CaseStudy={
  look:{region:'Etna',sub:'Eruption',code:'IT',theme:'fire',panel:'Volcanic signal',status:'Change analysis',caption:'Volcanic activity analysis'},
  id:'etna',index:'02',kind:'Volcanic eruption',title:'Etna eruption',place:'Sicily, Italy',eventDate:'6 August 2026',
  summary:'Fresh lava and ash reshape a volcano’s surface. Between two NISAR passes the radar brightness changes and the signal loses coherence. Where both methods agree, the detection is at its most reliable.',
  stats:[{value:'0.3',unit:'km²',label:'Change confirmed by both methods'},{value:'3.7',unit:'km²',label:'Radar-brightness change'},{value:'6.2',unit:'km²',label:'Coherence loss'}],
  notes:['Passes: 23 Jul → 28 Aug 2026.','Ground-motion layer is illustrative: movement along the radar line of sight, ±8 cm; red and blue are opposite directions.'],
  width:1485,height:1600,
  before:{src:'/media/cases/etna/before.webp',source:'data/event_visualisation/Etna/etna/BEFORE.jpg',label:'Before',date:'23 Jul 2026',alt:`Radar view of Mount Etna on 23 July 2026, before the eruption. ${composite}`},
  after:{src:'/media/cases/etna/after.webp',source:'data/event_visualisation/Etna/etna/AFTER.jpg',label:'After',date:'28 Aug 2026',alt:`Radar view of Mount Etna on 28 August 2026, after the eruption. ${composite}`},
  layers:[
    {id:'high-confidence',label:'Confirmed by both methods',hint:'0.3 km²',color:BOTH,src:'/media/cases/etna/high-confidence.webp',source:'data/event_visualisation/Etna/etna/mask_high_confidence.png',on:true},
    {id:'backscatter',label:'Radar-brightness change',hint:'GCOV · 3.7 km²',color:BRIGHT,src:'/media/cases/etna/backscatter.webp',source:'data/event_visualisation/Etna/etna/mask_backscatter.png',on:true},
    {id:'coherence',label:'Coherence loss',hint:'GUNW · 6.2 km²',color:COHERENCE,src:'/media/cases/etna/coherence.webp',source:'data/event_visualisation/Etna/etna/mask_coherence.png'},
    {id:'displacement',label:'Ground motion (illustrative)',hint:'Line of sight · ±8 cm',color:'linear-gradient(90deg,#3d7fd9,#f5efe9,#d9483d)',src:'/media/cases/etna/displacement.webp',source:'data/event_visualisation/Etna/etna/displacement.png'},
  ],
};

// The same slice of Etna on a cloudy day: optical imagery is blocked, radar is not.
export const etnaCloud={
  width:989,height:1665,
  before:{src:'/media/cases/etna/cloud-sentinel2.webp',source:'data/event_visualisation/Etna/2_etna_chmura_sentinel2.jpg',label:'Optical · Sentinel-2',alt:'Optical Sentinel-2 image of Mount Etna with a white cloud covering the summit.'} as CaseImage,
  after:{src:'/media/cases/etna/cloud-nisar.webp',source:'data/event_visualisation/Etna/2_etna_chmura_nisar.jpg',label:'Radar · NISAR',alt:`NISAR radar view of the same area, with the summit and lava fields visible through the cloud. ${composite}`} as CaseImage,
};

export const nepal:CaseStudy={
  look:{region:'Nepal',sub:'Flood',code:'NP',theme:'ice',panel:'Flood detection',status:'Terrain scan',caption:'Glacier outburst flood'},
  id:'nepal',index:'03',kind:'Glacier outburst flood',title:'Rasuwa glacier-collapse flood',place:'Bhote Koshi valley, Nepal',eventDate:'26 August 2026',
  summary:'A glacier collapse high above the Bhote Koshi valley sent water and debris downstream. Two independent radar methods trace the flood path along the valley floor, past Timure and on to Syabrubesi.',
  stats:[{value:'6.0',unit:'km²',label:'Change confirmed by both methods'},{value:'10.3',unit:'km²',label:'Radar-brightness change'},{value:'15.9',unit:'km²',label:'Coherence loss'},{value:'≈29',unit:'km',label:'Trace from its origin to Syabrubesi'}],
  notes:['Passes: 19 Aug → 31 Aug 2026.','Steep slopes and radar shadow (about 5% of the area) are blind spots: no colour there does not mean no damage.','Ground-motion layer is illustrative: movement along the radar line of sight, ±4 cm.'],
  width:1459,height:1600,
  before:{src:'/media/cases/nepal/before.webp',source:'data/event_visualisation/Nepal/nepal_flood/BEFORE.jpg',label:'Before',date:'19 Aug 2026',alt:`Radar view of the Rasuwa area on 19 August 2026, before the flood. ${composite}`},
  after:{src:'/media/cases/nepal/after.webp',source:'data/event_visualisation/Nepal/nepal_flood/AFTER.jpg',label:'After',date:'31 Aug 2026',alt:`Radar view of the same area on 31 August 2026, after the flood. ${composite}`},
  layers:[
    {id:'high-confidence',label:'Confirmed by both methods',hint:'6.0 km²',color:BOTH,src:'/media/cases/nepal/high-confidence.webp',source:'data/event_visualisation/Nepal/nepal_flood/mask_high_confidence.png',on:true},
    {id:'backscatter',label:'Radar-brightness change',hint:'GCOV · 10.3 km²',color:BRIGHT,src:'/media/cases/nepal/backscatter.webp',source:'data/event_visualisation/Nepal/nepal_flood/mask_backscatter.png'},
    {id:'coherence',label:'Coherence loss',hint:'GUNW · 15.9 km²',color:COHERENCE,src:'/media/cases/nepal/coherence.webp',source:'data/event_visualisation/Nepal/nepal_flood/mask_coherence.png'},
    {id:'displacement',label:'Ground motion (illustrative)',hint:'Line of sight · ±4 cm',color:'linear-gradient(90deg,#3d7fd9,#f5efe9,#d9483d)',src:'/media/cases/nepal/displacement.webp',source:'data/event_visualisation/Nepal/nepal_flood/displacement.png'},
  ],
};

// Pre-rendered fly-through of data/event_visualisation/Nepal/map3d.html, scrubbed by scroll.
export const flight={
  count:132,width:1280,height:720,km:28.8,
  frame:(i:number)=>`/media/cases/nepal/flight/f_${String(i).padStart(3,'0')}.webp`,
  source:'data/event_visualisation/Nepal/map3d.html',
  // Stop positions are measured along the recorded camera route (frames are evenly spaced by distance), at the
  // points map3d.html captions: trace start, upper valley, Timure (0.54) and Syabrubesi; the one-method-only
  // (yellow) area lies just above Syabrubesi, at about 0.90.
  beats:[
    {from:0,at:0,stop:'Trace origin',text:'The trace begins high in the mountains. Pink marks change confirmed by two independent radar methods.'},
    {from:.17,at:.228,stop:'Upper valley',text:'The change runs down a narrow valley. Radar needs neither sunlight nor a clear sky, so it still sees the valley floor.'},
    {from:.48,at:.541,stop:'Timure',text:'Near the border crossing the detected change follows the valley floor, the way the flood wave travelled.'},
    {from:.84,at:1,stop:'Syabrubesi',text:'Yellow marks change seen by one method only: a weaker signal, shown separately. About 29 km downstream, the change is still visible from orbit.'},
  ],
};

// Event types on the About globe. color tints each type (fire orange, quake yellow, crops green, ice blue, lava red);
// place is where the camera flies for it (our case-study sites, example regions where we have no case yet);
// picture is a radar composite from the matching case study, or null for a labelled placeholder.
export const detected=[
  {id:'wildfires',label:'Forest wildfires',color:'#ff9a3c',place:{lat:40.65,lon:-4.7,name:'Ávila, Spain',example:false},picture:{src:'/media/cases/spain/after.webp',caption:'NISAR radar composite of the Ávila burn area, Spain'},text:'Burn scars change how the surface scatters radar. Comparing passes before and after a fire outlines the affected area.',target:'spain',cta:'See the Spain case'},
  {id:'earthquakes',label:'Earthquakes',color:'#ffd84d',place:{lat:38.3,lon:140.9,name:'Japan',example:true},picture:null,text:'Repeat radar passes can reveal ground shifts of a few centimetres along a fault.',target:null,cta:'Coming soon'},
  {id:'farming',label:'Farming activities',color:'#7ddc6f',place:{lat:41.9,lon:-93.1,name:'US Midwest',example:true},picture:null,text:'Radar brightness follows crops through the season: growth, harvest and changing soil moisture.',target:null,cta:'Coming soon'},
  {id:'glaciers',label:'Glacier movement',color:'#9be7ff',place:{lat:28.2,lon:85.4,name:'Rasuwa, Nepal',example:false},picture:{src:'/media/cases/nepal/after.webp',caption:'NISAR radar composite of the Rasuwa flood area, Nepal'},text:'Flowing ice and sudden collapses leave traces in both radar brightness and coherence.',target:'nepal',cta:'See the Nepal case'},
  {id:'volcanoes',label:'Volcanoes',color:'#ff6b6b',place:{lat:37.75,lon:15,name:'Etna, Italy',example:false},picture:{src:'/media/cases/etna/after.webp',caption:'NISAR radar composite of Mount Etna, Italy'},text:'New lava and ash reshape the surface, even under a cloud cap that hides the summit from optical satellites.',target:'etna',cta:'See the Etna case'},
] as const;
