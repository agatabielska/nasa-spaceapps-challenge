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
