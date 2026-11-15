import {test} from 'node:test';import assert from 'node:assert/strict';
import {LMStudio} from './lmstudio.ts';
test('malformed model tool arguments are rejected before orchestration',async()=>{
  const lm=new LMStudio();lm.request=async()=>({choices:[{message:{role:'assistant',content:null,tool_calls:[{id:'x',type:'function',function:{name:'focus_event',arguments:{eventId:'spain'}}}]}}]});
  await assert.rejects(lm.complete('test',[],[]),/invalid answer or tool format/);
});
test('truncated model output is reported instead of interpreted as navigation',async()=>{
  const lm=new LMStudio();lm.request=async()=>({choices:[{finish_reason:'length',message:{role:'assistant',content:'partial'}}]});
  await assert.rejects(lm.complete('test',[],[]),/did not finish/);
});
test('Orbit profile requests direct answers and can require a grounding tool',async()=>{
  const lm=new LMStudio();let request:any;
  lm.request=async(_path,body)=>{request=body;return {choices:[{finish_reason:'stop',message:{role:'assistant',content:'Gotowe.'}}],usage:{completion_tokens_details:{reasoning_tokens:0}}};};
  await lm.complete('earthsignal/orbit-qwen3.6',[],[],undefined,'required');
  assert.equal(request.reasoning_effort,'none');assert.equal(request.tool_choice,'required');
  assert.equal(request.max_tokens,900);assert.equal(request.stream,false);
});
test('reasoning and raw tool markup never reach Orbit chat',async()=>{
  const lm=new LMStudio();
  lm.request=async()=>({choices:[{message:{role:'assistant',content:'',reasoning_content:'internal'}}]});
  await assert.rejects(lm.complete('earthsignal/orbit-qwen3.6',[],[]),/fast model profile/);
  lm.request=async()=>({choices:[{message:{role:'assistant',content:'<tool_call>search_events</tool_call>'}}]});
  await assert.rejects(lm.complete('test',[],[]),/internal tool syntax/);
});
