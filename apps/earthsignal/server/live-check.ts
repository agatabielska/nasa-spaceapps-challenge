import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {replySchema} from '../src/api.ts';
import type {ChatInput} from './contracts.ts';
const base=`http://127.0.0.1:${process.env.API_PORT??8787}`;
const context:ChatInput['context']={selectedEventId:null,bounds:[-180,-85,180,85],filters:{search:'',kinds:['flood','wildfire','volcano','earthquake','ice'],from:'2025-01-01',to:'2026-12-31',documentedOnly:false,viewOnly:false},revision:0,listedIds:[]};
const catalog=await fetch(base+'/api/events').then(r=>r.json());
const known=new Set(catalog.events.map((e:{id:string})=>e.id));
let sessionId:string|undefined;
const report:{label:string;seconds:number;text:string;tools:string[];ids:string[]}[]=[];
async function ask(label:string,message:string,expected:string[]|null,language:RegExp,focus?:string){
  const start=performance.now();
  const res=await fetch(base+'/api/orbit/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,sessionId,context}),signal:AbortSignal.timeout(180000)});
  const raw=await res.json();assert.equal(res.status,200,JSON.stringify(raw));
  const data=replySchema.parse(raw);sessionId=data.sessionId;
  const shown=data.actions.find(a=>a.type==='show_results');
  if(expected!==null){assert.ok(shown&&shown.type==='show_results',JSON.stringify(data));assert.deepEqual(shown.eventIds,expected);context.listedIds=shown.eventIds;}
  if(focus)assert.ok(data.actions.some(a=>(a.type==='focus_event'||a.type==='start_guide')&&a.eventId===focus),JSON.stringify(data));
  if(expected?.length===0){assert.ok(!data.actions.some(a=>a.type==='focus_event'||a.type==='start_guide'));context.selectedEventId=null;}
  for(const action of data.actions)if(action.type==='focus_event'||action.type==='start_guide'){assert.ok(known.has(action.eventId));context.selectedEventId=action.eventId;}
  assert.ok(data.toolsUsed.length>0,'Every answer must be grounded in a successful tool cycle');
  assert.match(data.text,language);assert.doesNotMatch(data.text,/<think>|<tool_call>|catalogVerified|analysisAvailable/);
  const item={label,seconds:Math.round((performance.now()-start)/100)/10,text:data.text,tools:data.toolsUsed,ids:shown&&shown.type==='show_results'?shown.eventIds:[]};report.push(item);console.log(JSON.stringify(item));
  return data;
}
await ask('PL short','Wskaż pożary w Hiszpanii.',['spain'],/katalog|pożar|przykład|ilustracyj/i,'spain');
await ask('DE follow-up','Und jetzt solche Ereignisse in Kanada.',['canada'],/Katalog|Brand|Brände|gefunden|Demonstrationseintrag/i,'canada');
await ask('FR new topic','Trouve les inondations en Afrique.',['mozambique'],/inondation|catalogue|trouv/i,'mozambique');
await ask('EN multiple results','Show the volcano events in Europe.',['etna','iceland'],/catalog|volcan|event/i);
await ask('FR ordered navigation','Ouvre le deuxième événement de cette liste.',null,/événement|Islande|catalogue|démonstration|affich/i,'iceland');
sessionId=undefined;context.listedIds=[];context.selectedEventId=null;
await ask('ES short','Muéstrame los incendios forestales de España.',['spain'],/incendio|catálogo|España|demostración/i,'spain');
await ask('DE no results','Suche Überschwemmungen in Deutschland. Das ist eine neue Suche. Réponds en allemand. Keine anderen Länder.',[],/Katalog|gefunden|Deutschland/i);
const details='Chcę wykorzystać mapę podczas prezentacji edukacyjnej. Zależy mi na odróżnieniu danych demonstracyjnych od udokumentowanych przykładów i na tym, żeby nie traktować radaru jak zwykłego zdjęcia. Nie potrzebuję szacunków szkód ani informacji spoza katalogu. ';
await ask('PL long',details.repeat(5)+'Moje właściwe polecenie: zacznij nowe wyszukiwanie i pokaż tylko powodzie w Afryce, niezależnie od wcześniejszych krajów. Odpowiedz krótko po polsku.',['mozambique'],/katalog|powódź|powodz|Mozambik/i,'mozambique');
const ready=catalog.events.filter((e:{analysisAvailable:boolean;kind:string;region:string})=>e.analysisAvailable&&e.kind==='flood'&&e.region==='Africa').map((e:{id:string})=>e.id);
await ask('PL unavailable analysis','Teraz wyświetl tylko te wydarzenia z gotową analizą NISAR.',ready,/katalog|analiz|znal|brak/i);
sessionId=undefined;context.listedIds=[];context.selectedEventId=null;
await ask('EN greeting','Hello, how can you help me?',null,/catalog|event|search|map/i);
const times=report.map(r=>r.seconds).sort((a,b)=>a-b);
const summary={model:process.env.LMSTUDIO_MODEL,date:new Date().toISOString(),medianSeconds:times[Math.floor(times.length/2)],maxSeconds:times.at(-1),report};
await mkdir(new URL('../.local/',import.meta.url),{recursive:true});
await writeFile(new URL('../.local/orbit-live-report.json',import.meta.url),JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify({passed:report.length,medianSeconds:summary.medianSeconds,maxSeconds:summary.maxSeconds,report:'.local/orbit-live-report.json'}));
