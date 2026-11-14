import {test} from 'node:test';import assert from 'node:assert/strict';
import {Catalog,readSeed} from './catalog.ts';import {Orbit} from './orbit.ts';import {LMStudio,type Message} from './lmstudio.ts';
import type {ChatInput} from './contracts.ts';
const context:ChatInput['context']={selectedEventId:null,bounds:[-180,-85,180,85],filters:{search:'',kinds:['flood','wildfire','volcano','earthquake','ice'],from:'2025-01-01',to:'2026-12-31',documentedOnly:false,viewOnly:false},revision:7};
const call=(name:string,args:unknown):Message=>({role:'assistant',content:null,tool_calls:[{id:'call-'+name,type:'function',function:{name,arguments:JSON.stringify(args)}}]});
const search={q:null,kinds:['wildfire'],countries:['ES'],region:null,from:null,to:null,documentedOnly:null,analysisAvailable:null,withinView:false,sort:'newest'};
function model(sequence:Message[]){const lm=new LMStudio();lm.status=async()=>({available:true,model:'test',models:['test'],message:'ok'});lm.complete=async()=>{const m=sequence.shift();if(!m)throw new Error('No test response');return m;};return lm;}
test('real database results power navigation, session and source output',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([call('search_events',search),call('focus_event',{eventId:'spain'}),{role:'assistant',content:'Scenariusz demonstracyjny w Hiszpanii.'}]));
    const r=await orbit.chat({message:'Dowolna prośba użytkownika',context});
    assert.deepEqual(r.actions,[{type:'show_results',eventIds:['spain']},{type:'focus_event',eventId:'spain'}]);assert.equal(r.events[0].catalogVerified,false);assert.equal(r.revision,7);assert.ok(r.sessionId);
  }finally{c.close();}
});
test('invented event and unknown tools do not cause navigation',async()=>{
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model([call('focus_event',{eventId:'imaginary-disaster'}),call('execute_sql',{sql:'DELETE FROM events'}),{role:'assistant',content:'Nie znaleziono rekordu.'}]));
    const r=await orbit.chat({message:'test',context});assert.deepEqual(r.actions,[]);assert.equal(c.search().total,13);
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
    const orbit=new Orbit(c,model([]));await assert.rejects(orbit.chat({message:'test',sessionId:'2ddf521e-1b4c-4df4-883f-40b570f48436',context}),/wygasła/);
    assert.throws(()=>new LMStudio({LMSTUDIO_BASE_URL:'https://example.com/v1'}),/loopback/);
  }finally{c.close();}
});
