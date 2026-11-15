import { ServiceError } from './contracts.ts';
import { z } from 'zod';

export type Message = {role:string;content:string|null;tool_calls?:ToolCall[];tool_call_id?:string};
export type ToolCall = {id:string;type:'function';function:{name:string;arguments:string}};
const outputSchema=z.object({role:z.literal('assistant'),content:z.string().nullable().optional(),tool_calls:z.array(z.object({
  id:z.string().min(1).max(200),type:z.literal('function'),function:z.object({name:z.string().max(100),arguments:z.string().max(16000)}),
})).max(6).optional()});
export class LMStudio {
  base:string; model:string; token:string;
  constructor(env:NodeJS.ProcessEnv=process.env) {
    this.base=(env.LMSTUDIO_BASE_URL??'http://127.0.0.1:1234/v1').replace(/\/$/,'');
    const url=new URL(this.base);
    if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||!['http:','https:'].includes(url.protocol)||url.username||url.password)throw new Error('LMSTUDIO_BASE_URL must be a loopback URL');
    this.model=env.LMSTUDIO_MODEL??'';this.token=env.LMSTUDIO_API_KEY??'';
  }
  async request(path:string, body?:unknown, timeout=5000, signal?:AbortSignal) {
    let response:Response;
    const limit=AbortSignal.timeout(timeout);
    try {response=await fetch(this.base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(this.token?{Authorization:'Bearer '+this.token}:{})},body:body?JSON.stringify(body):undefined,signal:signal?AbortSignal.any([signal,limit]):limit,redirect:'error'});}
    catch {
      if(signal?.aborted)throw new ServiceError(499,'CANCELLED','The request was cancelled.');
      if(limit.aborted)throw new ServiceError(504,'MODEL_TIMEOUT','LM Studio did not answer in time. Try a shorter question or check the model load.');
      throw new ServiceError(503,'MODEL_UNREACHABLE','LM Studio is not responding. Start its local server on port 1234 and load a model.');
    }
    if(!response.ok) {
      if(response.status===401)throw new ServiceError(503,'MODEL_AUTH','LM Studio requires a token. Set LMSTUDIO_API_KEY in .env.local.');
      throw new ServiceError(502,'MODEL_ERROR',`LM Studio rejected the request (HTTP ${response.status}). Check the model and its tool support in LM Studio.`);
    }
    return response.json();
  }
  async status(){
    try {const data=await this.request('/models');const models=(data.data??[]).map((m:{id:string})=>m.id).filter((id:unknown)=>typeof id==='string');
      const selected=this.model|| (models.length===1?models[0]:null);
      return {available:!!selected&&models.includes(selected),model:selected,models,message:!models.length?'Load a model in LM Studio.':!selected?'Choose a model in .env.local (LMSTUDIO_MODEL).':!models.includes(selected)?'The configured model is not available.':'Local model ready'};
    }catch(e){return {available:false,model:null,models:[] as string[],message:e instanceof Error?e.message:'LM Studio unavailable'};}
  }
  async complete(model:string,messages:Message[],tools:unknown[],signal?:AbortSignal,toolChoice:'auto'|'required'='auto'){
    const data=await this.request('/chat/completions',{model,messages,tools,tool_choice:toolChoice,temperature:0.2,top_p:0.8,top_k:20,max_tokens:900,stream:false,...(model.includes('orbit-qwen3.6')?{reasoning_effort:'none'}:{})},60000,signal);
    const choice=data.choices?.[0];
    if(model.includes('orbit-qwen3.6')&&(data.usage?.completion_tokens_details?.reasoning_tokens>0||choice?.message?.reasoning_content?.trim()))throw new ServiceError(502,'MODEL_THINKING','Orbit’s fast model profile is not active. Reload earthsignal/orbit-qwen3.6 with thinking disabled.');
    if(!choice?.message||choice.finish_reason==='length')throw new ServiceError(502,'MODEL_OUTPUT','The model did not finish its answer. Try a shorter question or increase the context length.');
    const parsed=outputSchema.safeParse(choice.message);
    if(!parsed.success)throw new ServiceError(502,'MODEL_OUTPUT','The model returned an invalid answer or tool format. Check the chat template in LM Studio.');
    if(/<\/?(?:think|tool_call|function)(?:[\s=>]|$)/i.test(parsed.data.content??''))throw new ServiceError(502,'MODEL_OUTPUT','The model returned internal tool syntax. Reload the Orbit model profile and check the chat template.');
    return {...parsed.data,content:parsed.data.content??null} as Message;
  }
}
