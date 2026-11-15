import {test} from 'node:test';import assert from 'node:assert/strict';
import {Catalog,readSeed} from './catalog.ts';import {Orbit} from './orbit.ts';import {LMStudio,type Message} from './lmstudio.ts';
import type {ChatInput} from './contracts.ts';
import {chatSchema} from './contracts.ts';
const context:ChatInput['context']={selectedEventId:null,bounds:[-180,-85,180,85],filters:{search:'',kinds:['flood','wildfire','volcano','earthquake','ice'],from:'2025-01-01',to:'2026-12-31',documentedOnly:false,viewOnly:false},revision:7};
const call=(name:string,args:unknown):Message=>({role:'assistant',content:null,tool_calls:[{id:'call-'+name,type:'function',function:{name,arguments:JSON.stringify(args)}}]});
const search={q:null,kinds:['wildfire'],countries:['ES'],region:null,from:null,to:null,documentedOnly:null,analysisAvailable:null,withinView:false,sort:'newest'};
function model(sequence:Message[]){const lm=new LMStudio();lm.status=async()=>({available:true,model:'test',models:['test'],message:'ok'});lm.complete=async()=>{const m=sequence.shift();if(!m)throw new Error('No test response');return m;};return lm;}
test('real database results power navigation, session and source output',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([call('search_events',search),call('focus_event',{eventId:'spain'}),{role:'assistant',content:'Scenariusz demonstracyjny w Hiszpanii.'}]));
    const r=await orbit.chat({message:'Dowolna prośba użytkownika',context});
    assert.deepEqual(r.actions,[{type:'show_results',eventIds:['spain']},{type:'focus_event',eventId:'spain'}]);assert.equal(r.events[0].catalogVerified,true);assert.equal(r.revision,7);assert.ok(r.sessionId);
  }finally{c.close();}
});
test('invented event and unknown tools do not cause navigation',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([call('focus_event',{eventId:'imaginary-disaster'}),call('execute_sql',{sql:'DELETE FROM events'}),{role:'assistant',content:'Nie znaleziono rekordu.'},{role:'assistant',content:'Nie znaleziono rekordu.'}]));
    await assert.rejects(orbit.chat({message:'test',context}),/did not finish/);assert.equal(c.search().total,15);
  }finally{c.close();}
});
test('model failure cannot commit a partially prepared navigation',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([call('search_events',search)]));
    await assert.rejects(orbit.chat({message:'test',context}),/No test response/);
  }finally{c.close();}
});
test('expired conversation is explicit and remote model endpoints are forbidden',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([]));await assert.rejects(orbit.chat({message:'test',sessionId:'2ddf521e-1b4c-4df4-883f-40b570f48436',context}),/expired/);
    assert.throws(()=>new LMStudio({LMSTUDIO_BASE_URL:'https://example.com/v1'}),/loopback/);
  }finally{c.close();}
});
test('results the browser never displayed are not used as the ordered list',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const prompts:string[]=[];const lm=model([call('search_events',{...search,kinds:['volcano'],countries:null,region:'Europe'}),{role:'assistant',content:'Two volcanoes.'},call('catalog_help',{}),{role:'assistant',content:'Which one?'},call('catalog_help',{}),{role:'assistant',content:'Which one?'}]);
    const complete=lm.complete;lm.complete=async(m,messages,t)=>{prompts.push(String(messages[0].content));return complete.call(lm,m,messages,t);};
    const orbit=new Orbit(c,lm);const first=await orbit.chat({message:'volcanoes in Europe',context});
    const shown=first.actions.find(a=>a.type==='show_results');assert.ok(shown&&shown.type==='show_results'&&shown.eventIds.length===2);
    // When the browser shows those results (in any order), the previous search remains available for refinements.
    await orbit.chat({message:'only the first',sessionId:first.sessionId,context:{...context,listedIds:[...shown.eventIds].reverse()}});
    assert.match(prompts.at(-1)!,/Previous search arguments: \{/);
    // Navigation was skipped in the browser, which lists only Mozambique: the stale search must not be reused.
    await orbit.chat({message:'open the second one',sessionId:first.sessionId,context:{...context,listedIds:['mozambique']}});
    assert.match(prompts.at(-1)!,/display order[^\n]*\["mozambique"\]/);assert.match(prompts.at(-1)!,/Previous search arguments: null/);
  }finally{c.close();}
});
test('cancelling a request stops the model call and frees the conversation',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const lm=model([call('catalog_help',{}),{role:'assistant',content:'Ready again.'}]);const complete=lm.complete;let calls=0,started=()=>{};
    const waiting=new Promise<void>(resolve=>{started=resolve;});
    lm.complete=async(m,messages,t,signal)=>{if(calls++===0){started();return new Promise((_,reject)=>signal!.addEventListener('abort',()=>reject(new Error('aborted'))));}return complete.call(lm,m,messages,t);};
    const orbit=new Orbit(c,lm),controller=new AbortController();
    const first=orbit.chat({message:'slow',context},controller.signal);await waiting;controller.abort();await assert.rejects(first);
    const [sessionId]=orbit.sessions.keys();assert.equal(orbit.sessions.get(sessionId)!.busy,false);
    assert.equal((await orbit.chat({message:'again',sessionId,context})).text,'Ready again.');
  }finally{c.close();}
});
test('optional search filters and an empty catalog result stay explicit, with no focus action',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    let toolOutput:any;const lm=model([call('search_events',{kinds:['flood'],countries:['DE']}),{role:'assistant',content:'Keine passenden Ereignisse im lokalen Katalog gefunden.'}]);
    const complete=lm.complete;lm.complete=async(m,messages,t,signal)=>{const tool=messages.find(x=>x.role==='tool');if(tool)toolOutput=JSON.parse(tool.content!);return complete.call(lm,m,messages,t,signal);};
    const r=await new Orbit(c,lm).chat({message:'Zeige Überschwemmungen in Deutschland.',context});
    assert.deepEqual(r.actions,[{type:'show_results',eventIds:[]}]);assert.deepEqual(r.events,[]);
    assert.equal(toolOutput.total,0);assert.match(toolOutput.catalogMessage,/local catalog/);
  }finally{c.close();}
});
test('long multilingual messages are preserved, bounded and sent with a required first tool',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const message='Por favor, explique les événements. Proszę sprawdzić katalog. '.repeat(85);
    assert.ok(message.length>4000);chatSchema.parse({message,context});
    assert.throws(()=>chatSchema.parse({message:'a'.repeat(8001),context}));
    const lm=model([call('catalog_help',{}),{role:'assistant',content:'Que souhaitez-vous explorer ?'}]);let first=true;
    const complete=lm.complete;lm.complete=async(m,messages,t,signal,choice)=>{if(first){assert.equal(choice,'required');assert.equal(messages.at(-1)?.content,message.trim());assert.match(messages[0].content!,/language of the latest user message/);first=false;}return complete.call(lm,m,messages,t,signal);};
    assert.deepEqual((await new Orbit(c,lm).chat({message,context})).actions,[]);
  }finally{c.close();}
});

test('an ungrounded no-results answer triggers a real search instead of committing navigation',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const lm=model([{role:'assistant',content:'No floods exist.'},call('search_events',{kinds:['flood'],region:'Africa'}),{role:'assistant',content:'Flooding along the Limpopo is in the catalog.'}]);
    const r=await new Orbit(c,lm).chat({message:'Find floods in Africa',context});
    assert.deepEqual(r.actions,[{type:'show_results',eventIds:['mozambique']},{type:'focus_event',eventId:'mozambique'}]);
    assert.deepEqual(r.toolsUsed,['search_events']);
  }finally{c.close();}
});
