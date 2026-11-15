export type Kind='flood'|'wildfire'|'volcano'|'earthquake'|'ice';
export type EventRecord={id:string;title:string;country:string;aliases:string[];kind:Kind;date:string;coordinates:[number,number];description:string;observations?:string[];source?:string;catalogVerified:boolean;analysisAvailable:boolean;countryCode:string;region:string};
// Event types and their names. Icons and colours live in the frontend (eventKinds.tsx), so this module stays usable
// by the server without React.
export const categories:Record<Kind,{label:string}>={flood:{label:'Floods'},wildfire:{label:'Wildfires'},volcano:{label:'Volcanoes'},earthquake:{label:'Earthquakes'},ice:{label:'Ice & glaciers'}};
export const normalize=(s:string)=>s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/ł/g,'l');
export function inBounds(point:[number,number],b:number[]|null){if(!b)return true;const [w,s,e,n]=b;const lon=((point[0]+180)%360+360)%360-180; if(point[1]<s||point[1]>n)return false;if(e-w>=360)return true;const west=((w+180)%360+360)%360-180,east=((e+180)%360+360)%360-180;return west<=east?lon>=west&&lon<=east:lon>=west||lon<=east;}
/** Every word of the query must occur in the record's title, place, description or aliases, in any order. */
export function matchesQuery(e:EventRecord,query:string){const tokens=normalize(query).match(/[\p{L}\p{N}]+/gu);if(!tokens)return true;const text=normalize([e.title,e.country,e.region,e.description,...e.aliases].join(' '));return tokens.every(t=>text.includes(t));}
export function filterEvents(items:EventRecord[],search:string,kinds:Kind[],from:string,to:string,verifiedOnly:boolean,bounds:number[]|null){return items.filter(e=>matchesQuery(e,search)&&kinds.includes(e.kind)&&e.date>=from&&e.date<=to&&(!verifiedOnly||e.catalogVerified)&&inBounds(e.coordinates,bounds));}
/** Narrowest west→east longitude interval covering all points; east may exceed 180 when the interval crosses the antimeridian. */
export function lonSpan(lons:number[]):[number,number]|null{
  const sorted=[...new Set(lons.map(l=>((l+180)%360+360)%360-180))].sort((a,b)=>a-b);
  if(!sorted.length)return null;
  let gap=sorted[0]+360-sorted[sorted.length-1],span:[number,number]=[sorted[0],sorted[sorted.length-1]];
  for(let i=0;i<sorted.length-1;i++)if(sorted[i+1]-sorted[i]>gap){gap=sorted[i+1]-sorted[i];span=[sorted[i+1],sorted[i]+360];}
  return span;
}
