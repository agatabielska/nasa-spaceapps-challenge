// Finished analyses, keyed by catalog event id. Everything shown in the "full analysis" view of the app lives in
// public/analysis/<id>/ and is produced by the Python pipeline in llm-based-model/ (branch KOBRAncz):
// tour.html = make_map3d.py --lang en, timeline.html = make_timeline.py, figures = analyze_case.py,
// validate_case.py, compare_optical.py, subsidence_series.py, subsidence_detail.py and gis_check.py.
export type Figure={title:string;caption:string;src?:string;pair?:{src:string;label:string}[]};
/** One tab of the analysis view: an embedded interactive page, or a column of figures. */
export type AnalysisTab={id:string;label:string;frame?:string;figures?:Figure[]};
export type Analysis={headline:string;facts:{value:string;label:string}[];tabs:AnalysisTab[]};
const a=(id:string,file:string)=>`/analysis/${id}/${file}`;
const layers='Every layer behind the result: radar before and after, change in both polarisations, coherence and its loss, ground displacement, raw phase, and the detected change.';

export const analyses:Record<string,Analysis>={
  nepal:{
    headline:'Two independent radar methods trace the flood for about 40 km down the valley, five days after the glacier collapsed.',
    facts:[{value:'6.0 km²',label:'changed surface, both methods agree'},{value:'≈40 km',label:'length of the trace'},{value:'5 days',label:'from the event to the radar pass'}],
    tabs:[
      {id:'tour',label:'3D tour',frame:a('nepal','tour.html?tour')},
      {id:'figures',label:'Summary & figures',figures:[
        {title:'Optical satellite vs radar, five days after',caption:'The same area, five hours apart. Cloud hides most of the valley from the optical satellite; the radar image is clear.',pair:[{src:a('nepal','cloud-optical.webp'),label:'Sentinel-2 (optical) · 1 Sep 2026'},{src:a('nepal','cloud-radar.webp'),label:'NISAR (radar) · 31 Aug 2026'}]},
        {title:'All analysis layers',caption:layers,src:a('nepal','summary.webp')},
      ]},
    ],
  },
  etna:{
    headline:'Radar shows where Etna’s surface changed during the eruption, including under the cloud that hid the summit from optical satellites.',
    facts:[{value:'3.7 km²',label:'radar-brightness change'},{value:'6.2 km²',label:'coherence loss'},{value:'±8 cm',label:'scale of the ground-motion map'}],
    tabs:[
      {id:'tour',label:'3D tour',frame:a('etna','tour.html?tour')},
      {id:'figures',label:'Summary & figures',figures:[
        {title:'Optical satellite vs radar on a cloudy day',caption:'16 August 2026. A cloud covers the summit and the fresh lava in the optical image; radar shows both.',pair:[{src:'/media/cases/etna/cloud-sentinel2.webp',label:'Sentinel-2 (optical)'},{src:'/media/cases/etna/cloud-nisar.webp',label:'NISAR (radar)'}]},
        {title:'All analysis layers',caption:layers,src:a('etna','summary.webp')},
      ]},
    ],
  },
  spain:{
    headline:'Radar found about a third of the burnt area that optical satellites mapped: here the two kinds of imagery complement each other.',
    facts:[{value:'70.2 km²',label:'detected by radar and confirmed by optical imagery'},{value:'36%',label:'of the burnt area found by radar'},{value:'65%',label:'of radar detections confirmed'}],
    tabs:[
      {id:'tour',label:'3D tour',frame:a('spain','tour.html?tour')},
      {id:'figures',label:'Summary & figures',figures:[
        {title:'Radar against the optical reference',caption:'Left: NISAR change score. Middle: burn severity from Sentinel-2. Right: green = both, red = NISAR only, blue = optical only.',src:a('spain','validation.webp')},
        {title:'While the fire was burning',caption:'26 July 2026. Smoke covers the active fire front in the optical image; radar sees the ground beneath it. The burn scar itself is clearer in optical imagery.',pair:[{src:a('spain','smoke-optical.webp'),label:'Sentinel-2 (optical)'},{src:a('spain','smoke-radar.webp'),label:'NISAR (radar)'}]},
        {title:'Where the detection sits on the ground',caption:'Sentinel-2 before and after the fire, a burn composite, and the NISAR detection outlined in red on the after image.',src:a('spain','satellite-check.webp')},
        {title:'All analysis layers',caption:'Radar before and after, change in both polarisations, and the detected change.',src:a('spain','summary.webp')},
      ]},
    ],
  },
  silesia:{
    headline:'The ground above active coal mines sank by up to 71 cm in four months. Every sinking bowl was confirmed by a second satellite track.',
    facts:[{value:'25',label:'sinking bowls, 11.1 km² in total'},{value:'71 cm',label:'deepest sinking in 120 days'},{value:'25 of 25',label:'bowls lie inside licensed coal-mining areas'}],
    tabs:[
      {id:'detail',label:'Krzyżowice in detail',frame:a('silesia','krzyzowice-timeline.html')},
      {id:'timeline',label:'Whole region',frame:a('silesia','timeline.html')},
      {id:'figures',label:'Summary & figures',figures:[
        {title:'Subsidence map, 18 June to 16 October 2026',caption:'Cumulative sinking from nine consecutive NISAR interferograms. Only bowls confirmed by a second satellite track are shown.',src:a('silesia','map.webp')},
        {title:'The six largest bowls over time',caption:'Measured sinking (solid) and a projection to the end of the year at the current rate (dashed, with its uncertainty band).',src:a('silesia','bowls.webp')},
        {title:'Checked against official mining areas',caption:'All 25 bowls lie inside licensed hard-coal mining areas, which cover 23% of the region (source: PIG-PIB, MIDAS database).',src:a('silesia','mining-areas.webp')},
        {title:'Krzyżowice cluster at 20 m',caption:'Total sinking, the last 12-day interval alone, and the raw interferogram of that interval.',src:a('silesia','detail-20m.webp')},
        {title:'Interval by interval',caption:'Sinking in each interval separately: where the ground was moving in a given period.',src:a('silesia','intervals-20m.webp')},
      ]},
    ],
  },
};
