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
  async request(path:string, body?:unknown, timeout=5000) {
    let response:Response;
    try {response=await fetch(this.base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(this.token?{Authorization:'Bearer '+this.token}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(timeout),redirect:'error'});}
    catch {throw new ServiceError(503,'MODEL_UNREACHABLE','LM Studio nie odpowiada. Uruchom lokalny serwer na porcie 1234 i załaduj model.');}
    if(!response.ok) {
      if(response.status===401)throw new ServiceError(503,'MODEL_AUTH','LM Studio wymaga tokenu. Ustaw LMSTUDIO_API_KEY w .env.local.');
      throw new ServiceError(502,'MODEL_ERROR',`LM Studio odrzuciło żądanie (HTTP ${response.status}). Sprawdź model i jego obsługę narzędzi w LM Studio.`);
    }
    return response.json();
  }
  async status(){
    try {const data=await this.request('/models');const models=(data.data??[]).map((m:{id:string})=>m.id).filter((id:unknown)=>typeof id==='string');
      const selected=this.model|| (models.length===1?models[0]:null);
      return {available:!!selected&&models.includes(selected),model:selected,models,message:!models.length?'Załaduj model w LM Studio.':!selected?'Wybierz model w .env.local (LMSTUDIO_MODEL).':!models.includes(selected)?'Skonfigurowany model nie jest dostępny.':'Lokalny model gotowy'};
    }catch(e){return {available:false,model:null,models:[] as string[],message:e instanceof Error?e.message:'LM Studio niedostępne'};}
  }
  async complete(model:string,messages:Message[],tools:unknown[]){
    const data=await this.request('/chat/completions',{model,messages,tools,tool_choice:'auto',temperature:0.1,max_tokens:1600,stream:false},90000);
    const choice=data.choices?.[0];
    if(!choice?.message||choice.finish_reason==='length')throw new ServiceError(502,'MODEL_OUTPUT','Model nie ukończył odpowiedzi. Spróbuj krótszego pytania lub zwiększ limit kontekstu.');
    const parsed=outputSchema.safeParse(choice.message);
    if(!parsed.success)throw new ServiceError(502,'MODEL_OUTPUT','Model zwrócił niepoprawny format odpowiedzi lub narzędzi. Sprawdź szablon czatu w LM Studio.');
    return {...parsed.data,content:parsed.data.content??null} as Message;
  }
}
