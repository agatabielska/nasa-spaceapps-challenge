import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Gemini} from './gemini.ts';
import {createModel} from './model-provider.ts';
import {LMStudio} from './lmstudio.ts';
import {Catalog,readSeed} from './catalog.ts';
import {Orbit,tools} from './orbit.ts';
import type {ChatInput} from './contracts.ts';

const env={GEMINI_API_KEY:'test-secret-never-expose',GEMINI_MODEL:'gemini-3.8-flash'};
const answer=(text:string)=>({candidates:[{finishReason:'STOP',content:{role:'model',parts:[{text}]}}]});
const functionTurn=(name:string,args:unknown,id?:string)=>({candidates:[{finishReason:'STOP',content:{role:'model',parts:[
  {functionCall:{name,args,...(id?{id}:{})},thoughtSignature:'opaque-signature'},
]}}]});
function mock(responses:unknown[]){
  const requests:{url:string;init:RequestInit;body:any}[]=[];
  const model=new Gemini(env,async(url,init)=>{
    requests.push({url:String(url),init:init!,body:JSON.parse(init!.body as string)});
    const next=responses.shift();assert.notEqual(next,undefined,'Unexpected additional API call');
    return next instanceof Response?next:Response.json(next);
  });
  return {model,requests};
}
const context:ChatInput['context']={selectedEventId:null,bounds:[-180,-85,180,85],filters:{search:'',kinds:['flood','wildfire','volcano','earthquake','ice','subsidence'],from:'2025-01-01',to:'2026-12-31',documentedOnly:false,viewOnly:false},revision:4,listedIds:[]};

test('provider selection preserves local setup and handles missing cloud credentials without a network call',async()=>{
  assert.ok(createModel({}) instanceof LMStudio);
  assert.ok(createModel({ORBIT_PROVIDER:'gemini'}) instanceof Gemini);
  assert.throws(()=>createModel({ORBIT_PROVIDER:'unexpected'}),/ORBIT_PROVIDER/);
  assert.throws(()=>new Gemini({...env,GEMINI_MODEL:'https://other.example'}),/model ID/);
  const g=new Gemini({},async()=>{throw new Error('Status must not call the API');});
  assert.equal((await g.status()).available,false);
  await assert.rejects(g.complete('gemini-3.8-flash',[],tools),{code:'MODEL_AUTH'});
});

test('Gemini uses a fixed Google endpoint, server-side header, JSON schemas and mandatory grounding',async()=>{
  const {model,requests}=mock([functionTurn('search_events',{countries:['ES'],kinds:['wildfire']})]);
  const status=await model.status();assert.equal(requests.length,0);assert.equal(status.available,true);
  const long='Proszę uwzględnić cały opis. '.repeat(100)+'Wskaż pożary w Hiszpanii.';
  await model.complete(model.model,[{role:'system',content:'Keep the Orbit format.'},{role:'user',content:long}],tools,undefined,'required');
  const {url,init,body}=requests[0];
  assert.equal(url,'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent');
  assert.equal(init.redirect,'error');assert.equal(new Headers(init.headers).get('x-goog-api-key'),env.GEMINI_API_KEY);
  assert.ok(!url.includes(env.GEMINI_API_KEY));assert.ok(!JSON.stringify(body).includes(env.GEMINI_API_KEY));
  assert.equal(body.contents[0].parts[0].text,long);
  assert.equal(body.toolConfig.functionCallingConfig.mode,'ANY');
  assert.deepEqual(body.tools[0].functionDeclarations[0].parametersJsonSchema,tools[0].function.parameters);
  assert.equal(body.generationConfig.thinkingConfig.thinkingLevel,'LOW');
  assert.equal(body.generationConfig.maxOutputTokens,2048);
});

test('real Orbit search cycle preserves signatures and coordinates while returning the unchanged browser contract',async()=>{
  const text='Ávila wildfire\n2026-08-12 · 40.66, -4.70\nPożar w Hiszpanii.';
  const {model,requests}=mock([functionTurn('search_events',{countries:['ES'],kinds:['wildfire']},'google-call-1'),answer(text)]);
  const c=new Catalog(':memory:',readSeed());
  try{
    const reply=await new Orbit(c,model).chat({message:'Wskaż pożary w Hiszpanii.',context});
    assert.equal(reply.text,text);assert.equal(reply.model,env.GEMINI_MODEL);assert.equal(reply.revision,4);
    assert.deepEqual(reply.actions,[{type:'show_results',eventIds:['spain']},{type:'focus_event',eventId:'spain'}]);
    assert.ok(!JSON.stringify(reply).includes('opaque-signature'));assert.ok(!JSON.stringify(reply).includes(env.GEMINI_API_KEY));
    const contents=requests[1].body.contents;
    assert.equal(contents[1].parts[0].thoughtSignature,'opaque-signature');
    assert.deepEqual(contents[2].parts[0].functionResponse.id,'google-call-1');
    assert.equal(contents[2].parts[0].functionResponse.name,'search_events');
    assert.equal(contents[2].parts[0].functionResponse.response.total,1);
    const event=c.get('spain')!;
    assert.deepEqual(contents[2].parts[0].functionResponse.response.events[0].coordinates,{latitude:event.coordinates[1],longitude:event.coordinates[0]});
    assert.equal(requests[1].body.toolConfig.functionCallingConfig.mode,'AUTO');
    assert.match(requests[1].body.systemInstruction.parts[0].text,/language of the latest user message/);
  }finally{c.close();}
});

test('parallel native calls without IDs are grouped into one response turn and thoughts never reach the user',async()=>{
  const turn={candidates:[{finishReason:'STOP',content:{parts:[
    {text:'private reasoning',thought:true,thoughtSignature:'signature-1'},
    {functionCall:{name:'get_event',args:{eventId:'etna'}},thoughtSignature:'signature-2'},
    {functionCall:{name:'get_event',args:{eventId:'spain'}}},
  ]}}]};
  const {model,requests}=mock([turn,answer('Gotowe.')]);
  const c=new Catalog(':memory:',readSeed());try{
    const reply=await new Orbit(c,model).chat({message:'Porównaj Etnę i pożar w Hiszpanii.',context});
    assert.equal(reply.text,'Gotowe.');assert.equal(reply.events.length,2);
    const contents=requests[1].body.contents;assert.deepEqual(contents[1].parts,turn.candidates[0].content.parts);
    assert.equal(contents[2].parts.length,2);
    assert.ok(!('id' in contents[2].parts[0].functionResponse));
    assert.equal(contents[2].parts[1].functionResponse.response.id,'spain');
  }finally{c.close();}
});

test('a multilingual follow-up retains real ordered results and can open an available guide',async()=>{
  const {model,requests}=mock([
    functionTurn('search_events',{kinds:['volcano'],region:'Europe'}),answer('Etna\nIceland'),
    functionTurn('focus_event',{eventId:'iceland'}),answer('Islande : pas encore analysé.'),
    functionTurn('start_guide',{eventId:'etna'}),answer('Etna\n2026-08-07 · 37.75, 15.00\nOtwieram analizę.'),
  ]);
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model);
    const first=await orbit.chat({message:'Show volcanoes in Europe',context});
    const second=await orbit.chat({message:'Ouvre le deuxième événement.',sessionId:first.sessionId,context:{...context,listedIds:['etna','iceland']}});
    assert.deepEqual(second.actions,[{type:'focus_event',eventId:'iceland'}]);
    assert.match(requests[2].body.systemInstruction.parts[0].text,/display order[^\n]*\["etna","iceland"\]/);
    const third=await orbit.chat({message:'Jednak otwórz analizę Etny.',sessionId:first.sessionId,context:{...context,selectedEventId:'iceland',listedIds:['etna','iceland']}});
    assert.deepEqual(third.actions,[{type:'start_guide',eventId:'etna'}]);
  }finally{c.close();}
});

test('no matches remain empty and an unavailable guide cannot be opened by the cloud model',async()=>{
  const {model}=mock([
    functionTurn('search_events',{kinds:['flood'],countries:['DE']}),answer('Dazu gibt es noch keine Analyse.'),
    functionTurn('get_event',{eventId:'canada'}),functionTurn('start_guide',{eventId:'canada'}),answer('Pas encore analysé.'),
  ]);
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model);
    const reply=await orbit.chat({message:'Suche Überschwemmungen in Deutschland.',context});
    assert.deepEqual(reply.actions,[{type:'show_results',eventIds:[]}]);assert.deepEqual(reply.events,[]);
    const next=await orbit.chat({message:'Ouvre l’analyse au Canada.',context});
    assert.ok(!next.actions.some(a=>a.type==='start_guide'));
  }finally{c.close();}
});

test('upstream failures are specific and never disclose keys, request bodies or provider error text',async()=>{
  for(const [status,code] of [[400,'MODEL_CONFIG'],[401,'MODEL_AUTH'],[403,'MODEL_AUTH'],[404,'MODEL_UNAVAILABLE'],[429,'MODEL_RATE_LIMIT'],[500,'MODEL_UNREACHABLE']] as const){
    const {model}=mock([new Response(env.GEMINI_API_KEY+' upstream private details',{status})]);
    await assert.rejects(model.complete(model.model,[{role:'user',content:'Etna'}],tools),error=>{
      assert.equal((error as {code:string}).code,code);assert.ok(!String(error).includes(env.GEMINI_API_KEY));assert.ok(!String(error).includes('upstream private details'));return true;
    });
  }
});

test('partial, blocked, malformed and oversized outputs cannot trigger navigation',async()=>{
  for(const raw of [
    {candidates:[{finishReason:'MAX_TOKENS',content:{parts:[{functionCall:{name:'focus_event',args:{eventId:'etna'}}}]}}]},
    {promptFeedback:{blockReason:'SAFETY'}},
    {candidates:[{finishReason:'STOP',content:{parts:[{functionCall:{name:'focus_event',args:'not an object'}}]}}]},
    {candidates:[{finishReason:'STOP',content:{parts:Array.from({length:7},()=>({functionCall:{name:'reset_map',args:{}}}))}}]},
    answer('<tool_call>search_events</tool_call>'),
    {unexpected:'response'},
  ]){
    const {model}=mock([raw]);await assert.rejects(model.complete(model.model,[],tools));
  }
  const {model}=mock([functionTurn('search_events',{countries:['ES'],kinds:['wildfire']}),new Response('busy',{status:429})]);
  const c=new Catalog(':memory:',readSeed());try{
    const orbit=new Orbit(c,model);await assert.rejects(orbit.chat({message:'Pożary w Hiszpanii',context}),{code:'MODEL_RATE_LIMIT'});
    assert.deepEqual([...orbit.sessions.values()][0].messages,[]);
    assert.deepEqual([...orbit.sessions.values()][0].resultIds,[]);
    assert.equal([...orbit.sessions.values()][0].busy,false);
  }finally{c.close();}
});

test('network errors are sanitised and cancellation is passed through to Google',async()=>{
  const g=new Gemini(env,async()=>{throw new Error(env.GEMINI_API_KEY);});
  await assert.rejects(g.complete(g.model,[],tools),{code:'MODEL_UNREACHABLE'});
  const controller=new AbortController();let received:AbortSignal|undefined;
  const waiting=new Gemini(env,async(_url,init)=>{received=init!.signal!;controller.abort();received.throwIfAborted();throw new Error('unreachable');});
  await assert.rejects(waiting.complete(waiting.model,[],tools,controller.signal),{code:'CANCELLED'});
  assert.equal(received!.aborted,true);
});

test('Flash-Lite uses minimal thinking while the Flash profile stays on LOW',async()=>{
  let body:any;
  const model=new Gemini({...env,GEMINI_MODEL:'gemini-3.5-flash-lite'},async(_url,init)=>{
    body=JSON.parse(init!.body as string);return Response.json(answer('Gotowe.'));
  });
  await model.complete(model.model,[{role:'user',content:'Etna'}],tools);
  assert.equal(body.generationConfig.thinkingConfig.thinkingLevel,'MINIMAL');
});

test('deadline diagnostics identify the blocked stage without exposing prompts or credentials',async t=>{
  const logs:string[]=[];t.mock.method(console,'warn',(line:string)=>logs.push(line));
  assert.throws(()=>new Gemini({...env,GEMINI_REQUEST_TIMEOUT_MS:'0'}),/GEMINI_REQUEST_TIMEOUT_MS/);
  assert.throws(()=>new Gemini({...env,GEMINI_REQUEST_TIMEOUT_MS:'600000'}),/GEMINI_REQUEST_TIMEOUT_MS/);
  const model=new Gemini({...env,GEMINI_REQUEST_TIMEOUT_MS:'1000'},async(_url,init)=>{
    // Keep the event loop alive like a real socket while the deadline signal fires.
    await new Promise<void>((resolve,reject)=>{
      const timer=setTimeout(resolve,2000);
      init!.signal!.addEventListener('abort',()=>{clearTimeout(timer);reject(init!.signal!.reason);},{once:true});
    });
    return Response.json(answer('too late'));
  });
  await assert.rejects(model.complete(model.model,[{role:'user',content:'private question'}],tools,undefined,'required'),{code:'MODEL_TIMEOUT'});
  const entry=JSON.parse(logs[0]);
  assert.equal(entry.code,'MODEL_TIMEOUT');assert.equal(entry.stage,'tool_selection');
  assert.equal(entry.phase,'waiting_headers');assert.ok(entry.elapsedMs>=900);
  assert.ok(!logs[0].includes(env.GEMINI_API_KEY));assert.ok(!logs[0].includes('private question'));
});
