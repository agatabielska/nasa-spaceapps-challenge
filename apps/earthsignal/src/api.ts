import { z } from 'zod';
import { eventSchema, type ChatInput } from '../server/contracts.ts';

const id=z.string().max(100);
export const replySchema=z.object({
  sessionId:z.string().uuid(),text:z.string(),model:z.string(),revision:z.number(),toolsUsed:z.array(z.string()),
  events:z.array(eventSchema),sources:z.array(z.object({title:z.string(),url:z.string().url().refine(s=>/^https?:/.test(s))})),
  actions:z.array(z.discriminatedUnion('type',[
    z.object({type:z.literal('show_results'),eventIds:z.array(id)}),
    z.object({type:z.literal('focus_event'),eventId:id}),z.object({type:z.literal('start_guide'),eventId:id}),
    z.object({type:z.literal('reset_map')}),
  ])),
});
export type OrbitStatus={available:boolean;model:string|null;models:string[];message:string};
export class APIError extends Error {code:string;constructor(message:string,code:string){super(message);this.code=code;}}
// AbortSignal.any where the browser has it (Safari 17.4+, Firefox 124+), otherwise an equivalent controller.
function anySignal(signals:AbortSignal[]):AbortSignal{
  if('any' in AbortSignal)return AbortSignal.any(signals);
  const controller=new AbortController();
  for(const s of signals){if(s.aborted){controller.abort(s.reason);break;}s.addEventListener('abort',()=>controller.abort(s.reason),{once:true});}
  return controller.signal;
}
async function request(path:string,body?:unknown,signal?:AbortSignal){
  let res:Response;
  const limit=AbortSignal.timeout(240000);
  try {res=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,signal:signal?anySignal([signal,limit]):limit});}
  catch{
    if(signal?.aborted)throw new APIError('Request cancelled.','CANCELLED');
    if(limit.aborted)throw new APIError('EarthSignal did not answer in time. Please try again.','API_TIMEOUT');
    throw new APIError('Cannot reach EarthSignal. Please try again shortly.','API_UNAVAILABLE');
  }
  let data;try{data=await res.json();}catch{throw new APIError('EarthSignal returned an invalid response. Please try again.','API_UNAVAILABLE');}
  if(!res.ok)throw new APIError(data.error?.message??'EarthSignal API error',data.error?.code??'API_ERROR');
  return data;
}
export async function loadCatalog(){return z.object({events:z.array(eventSchema),total:z.number()}).parse(await request('/api/events'));}
export async function loadOrbitStatus():Promise<OrbitStatus>{return z.object({available:z.boolean(),model:z.string().nullable(),models:z.array(z.string()),message:z.string()}).parse(await request('/api/orbit/status'));}
export async function sendOrbit(input:ChatInput,signal?:AbortSignal){return replySchema.parse(await request('/api/orbit/chat',input,signal));}
