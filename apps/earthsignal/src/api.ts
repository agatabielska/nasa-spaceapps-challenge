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
async function request(path:string,body?:unknown){
  let res:Response;
  try {res=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(240000)});}
  catch{throw new APIError('Nie można połączyć się z lokalnym backendem. Uruchom npm run dev.','API_UNAVAILABLE');}
  let data;try{data=await res.json();}catch{throw new APIError('Backend nie zwrócił poprawnej odpowiedzi. Uruchom npm run dev.','API_UNAVAILABLE');}
  if(!res.ok)throw new APIError(data.error?.message??'Local API error',data.error?.code??'API_ERROR');
  return data;
}
export async function loadCatalog(){return z.object({events:z.array(eventSchema),total:z.number()}).parse(await request('/api/events'));}
export async function loadOrbitStatus():Promise<OrbitStatus>{return z.object({available:z.boolean(),model:z.string().nullable(),models:z.array(z.string()),message:z.string()}).parse(await request('/api/orbit/status'));}
export async function sendOrbit(input:ChatInput){return replySchema.parse(await request('/api/orbit/chat',input));}
