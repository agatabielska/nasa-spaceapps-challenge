import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import { ServiceError } from './contracts.ts';
import { outputSchema, type Message, type OrbitModel, type ModelStatus } from './model.ts';

const partSchema=z.object({
  text:z.string().optional(),thought:z.boolean().optional(),thoughtSignature:z.string().optional(),
  functionCall:z.object({name:z.string().min(1).max(100),args:z.record(z.string(),z.unknown()).optional(),id:z.string().min(1).max(200).optional()}).passthrough().optional(),
}).passthrough();
const responseSchema=z.object({
  promptFeedback:z.object({blockReason:z.string().optional()}).optional(),
  candidates:z.array(z.object({finishReason:z.string().optional(),content:z.object({parts:z.array(partSchema)}).optional()})).optional(),
});
const declarationSchema=z.object({type:z.literal('function'),function:z.object({
  name:z.string(),description:z.string(),parameters:z.record(z.string(),z.unknown()),
})});

// Keep complete native model turns: reconstructing only function names/arguments loses
// Gemini 3 thought signatures and breaks the next request in a tool cycle.
function contentsFor(messages:Message[]){
  const contents:{role:'user'|'model';parts:Record<string,unknown>[]}[]=[];
  const calls=new Map<string,{name:string;id?:string}>();
  for(const message of messages){
    if(message.role==='system')continue;
    if(message.role==='tool'){
      const call=calls.get(message.tool_call_id??'');
      if(!call)throw new ServiceError(502,'MODEL_OUTPUT','Orbit could not match a search response. Please try again.');
      const part={functionResponse:{...call,response:JSON.parse(message.content??'{}')}};
      const previous=contents.at(-1);
      if(previous?.role==='user'&&previous.parts.every(p=>'functionResponse' in p))previous.parts.push(part);
      else contents.push({role:'user',parts:[part]});
    }else if(message.role==='assistant'){
      if(message.providerParts){
        const nativeCalls=message.providerParts.flatMap(p=>p.functionCall?[p.functionCall as {name:string;id?:string}]:[]);
        for(const [index,call] of (message.tool_calls??[]).entries()){
          const native=nativeCalls[index];calls.set(call.id,{name:call.function.name,...(native?.id?{id:native.id}:{})});
        }
        contents.push({role:'model',parts:message.providerParts});
      }else if(message.tool_calls?.length){
        throw new ServiceError(502,'MODEL_OUTPUT','Orbit is missing the model search context. Please try again.');
      }else if(message.content)contents.push({role:'model',parts:[{text:message.content}]});
    }else if(message.role==='user')contents.push({role:'user',parts:[{text:message.content??''}]});
  }
  return contents;
}

export class Gemini implements OrbitModel {
  private key:string;
  private transport:typeof fetch;
  private timeoutMs:number;
  readonly model:string;
  constructor(env:NodeJS.ProcessEnv=process.env,transport:typeof fetch=fetch){
    this.transport=transport;
    this.key=(env.GEMINI_API_KEY??'').trim();
    this.timeoutMs=Number(env.GEMINI_REQUEST_TIMEOUT_MS??45000);
    if(!Number.isInteger(this.timeoutMs)||this.timeoutMs<1000||this.timeoutMs>45000)throw new Error('GEMINI_REQUEST_TIMEOUT_MS must be an integer from 1000 to 45000');
    this.model=(env.GEMINI_MODEL??'gemini-3.8-flash').replace(/^models\//,'').trim();
    if(!/^gemini-[a-z0-9.-]+$/.test(this.model))throw new Error('GEMINI_MODEL must be a Gemini model ID, for example gemini-3.8-flash');
  }
  async status():Promise<ModelStatus>{
    // A status poll never generates tokens or adds a network round trip to every chat.
    // Credentials and model access are verified by the first real completion.
    return {available:!!this.key,model:this.key?this.model:null,models:this.key?[this.model]:[],
      message:this.key?'Orbit configured; API access is checked when answering.':'Set GEMINI_API_KEY on the server to enable Orbit.'};
  }
  async request(body:unknown,signal?:AbortSignal,stage:'tool_selection'|'response'='response'):Promise<unknown>{
    if(!this.key)throw new ServiceError(503,'MODEL_AUTH','Orbit is not configured. Please contact the site owner.');
    const limit=AbortSignal.timeout(this.timeoutMs),started=Date.now();
    let phase:'waiting_headers'|'reading_body'='waiting_headers',upstreamStatus:number|undefined;
    try{
      // A fixed Google endpoint prevents accidentally sending the key to another server.
      // Never include credentials in URLs, logs or upstream error messages.
      const response=await this.transport(`https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent`,{
        method:'POST',headers:{'Content-Type':'application/json','x-goog-api-key':this.key},
        body:JSON.stringify(body),signal:signal?AbortSignal.any([signal,limit]):limit,redirect:'error',
      });
      upstreamStatus=response.status;phase='reading_body';
      if(!response.ok){
        if(response.status===401||response.status===403)throw new ServiceError(503,'MODEL_AUTH','Orbit cannot connect to its AI service. Please contact the site owner.');
        if(response.status===429)throw new ServiceError(429,'MODEL_RATE_LIMIT','Orbit is busy or its usage limit has been reached. Please try again later.');
        if(response.status===404)throw new ServiceError(503,'MODEL_UNAVAILABLE','The configured Orbit model is unavailable. Please contact the site owner.');
        if(response.status===400)throw new ServiceError(502,'MODEL_CONFIG','Orbit could not process this request. Please try again; if this continues, contact the site owner.');
        throw new ServiceError(503,'MODEL_UNREACHABLE','Orbit is temporarily unavailable. Please try again shortly.');
      }
      try{return await response.json();}catch(error){
        if(signal?.aborted||limit.aborted)throw error;
        throw new ServiceError(502,'MODEL_OUTPUT','Orbit received an incomplete answer. Please try again.');
      }
    }catch(error){
      if(signal?.aborted)throw new ServiceError(499,'CANCELLED','The request was cancelled.');
      const failure=limit.aborted?new ServiceError(504,'MODEL_TIMEOUT','Orbit took too long to answer. Please try again.'):
        error instanceof ServiceError?error:new ServiceError(503,'MODEL_UNREACHABLE','Orbit is temporarily unavailable. Please try again shortly.');
      // Only fixed fields: upstream messages, credentials and conversation content are never logged.
      console.warn(JSON.stringify({event:'orbit.model_failure',provider:'gemini',model:this.model,
        code:failure.code,stage,phase,elapsedMs:Date.now()-started,upstreamStatus}));
      throw failure;
    }
  }
  async complete(model:string,messages:Message[],tools:unknown[],signal?:AbortSignal,toolChoice:'auto'|'required'='auto'):Promise<Message>{
    if(model!==this.model)throw new ServiceError(503,'MODEL_UNAVAILABLE','The configured Orbit model is unavailable.');
    const declarations=tools.map(tool=>{const {name,description,parameters}=declarationSchema.parse(tool).function;
      return {name,description,parametersJsonSchema:parameters};});
    const raw=await this.request({
      systemInstruction:{parts:[{text:messages.filter(m=>m.role==='system').map(m=>m.content??'').join('\n')}]},
      contents:contentsFor(messages),tools:[{functionDeclarations:declarations}],
      toolConfig:{functionCallingConfig:{mode:toolChoice==='required'?'ANY':'AUTO'}},
      generationConfig:{temperature:1,maxOutputTokens:2048,...(/^gemini-[34]/.test(model)?{
        thinkingConfig:{thinkingLevel:/^gemini-3\.(?:1|5)-flash-lite$/.test(model)?'MINIMAL':'LOW'},
      }:{})},
    },signal,toolChoice==='required'?'tool_selection':'response');
    const parsed=responseSchema.safeParse(raw);
    if(!parsed.success)throw new ServiceError(502,'MODEL_OUTPUT','Orbit received an invalid answer. Please try again.');
    const candidate=parsed.data.candidates?.[0];
    if(parsed.data.promptFeedback?.blockReason||candidate?.finishReason==='SAFETY')throw new ServiceError(422,'MODEL_BLOCKED','Orbit could not answer this question. Please rephrase it around an event on the map.');
    if(candidate?.finishReason==='MAX_TOKENS')throw new ServiceError(502,'MODEL_OUTPUT','Orbit did not finish its answer. Please try again.');
    if(candidate?.finishReason!=='STOP'||!candidate.content)throw new ServiceError(502,'MODEL_OUTPUT','Orbit could not finish its answer. Please try again.');
    const parts=candidate.content.parts;
    const toolCalls=parts.flatMap(part=>part.functionCall?[{id:part.functionCall.id??randomUUID(),type:'function' as const,
      function:{name:part.functionCall.name,arguments:JSON.stringify(part.functionCall.args??{})}}]:[]);
    const content=parts.filter(p=>!p.thought&&p.text!==undefined).map(p=>p.text).join('')||null;
    const result=outputSchema.safeParse({role:'assistant',content,...(toolCalls.length?{tool_calls:toolCalls}:{})});
    if(!result.success||(!content&&!toolCalls.length)||/<\/?(?:think|tool_call|function)(?:[\s=>]|$)/i.test(content??''))throw new ServiceError(502,'MODEL_OUTPUT','Orbit received an invalid answer. Please try again.');
    return {...result.data,content,providerParts:parts};
  }
}
