import assert from 'node:assert/strict';
const base=`http://127.0.0.1:${process.env.API_PORT??8787}`;
const context={selectedEventId:null as string|null,bounds:[-180,-85,180,85],filters:{search:'',kinds:['flood','wildfire','volcano','earthquake','ice'],from:'2025-01-01',to:'2026-12-31',documentedOnly:false,viewOnly:false},revision:0};
let sessionId:string|undefined;
const health=await fetch(base+'/api/health').then(r=>r.json());assert.equal(health.database,'sqlite');
for(const [message,expected] of [
  ['Wskaż pożary w Hiszpanii','spain'],
  ['A teraz pokaż takie zdarzenia w Kanadzie.','canada'],
  ['Znajdź powodzie w Afryce.','mozambique'],
] as const){
  const started=Date.now();
  const response=await fetch(base+'/api/orbit/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,sessionId,context}),signal:AbortSignal.timeout(240000)});
  const data=await response.json();
  assert.equal(response.status,200,JSON.stringify(data));sessionId=data.sessionId;
  const results=data.actions.find((a:{type:string})=>a.type==='show_results');
  assert.ok(results?.eventIds.includes(expected),JSON.stringify(data));
  assert.ok(data.toolsUsed.includes('search_events'));
  const focus=data.actions.find((a:{type:string})=>a.type==='focus_event');context.selectedEventId=focus?.eventId??null;
  assert.equal(focus?.eventId,expected,'A single result must navigate to its actual event');
  console.log(JSON.stringify({message,model:data.model,seconds:Math.round((Date.now()-started)/100)/10,results:results.eventIds,text:data.text}));
}
const none=await fetch(base+'/api/orbit/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'Teraz wyświetl tylko wydarzenia z gotową analizą NISAR.',sessionId,context}),signal:AbortSignal.timeout(240000)});
const empty=await none.json();assert.equal(none.status,200,JSON.stringify(empty));
assert.deepEqual(empty.actions.find((a:{type:string})=>a.type==='show_results')?.eventIds,[],JSON.stringify(empty));
console.log(JSON.stringify({message:'Only completed analyses',text:empty.text,results:[]}));
console.log('Live LM Studio search and conversational navigation passed.');
