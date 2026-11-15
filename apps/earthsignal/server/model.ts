import { z } from 'zod';

export type ToolCall = {id:string;type:'function';function:{name:string;arguments:string}};
export type Message = {role:string;content:string|null;tool_calls?:ToolCall[];tool_call_id?:string;
  // Native model parts stay on the server, including Gemini's opaque thought signatures.
  providerParts?:Record<string,unknown>[]};
export type ModelStatus = {available:boolean;model:string|null;models:string[];message:string};
export interface OrbitModel {
  status():Promise<ModelStatus>;
  complete(model:string,messages:Message[],tools:unknown[],signal?:AbortSignal,toolChoice?:'auto'|'required'):Promise<Message>;
}
export const outputSchema=z.object({role:z.literal('assistant'),content:z.string().nullable().optional(),tool_calls:z.array(z.object({
  id:z.string().min(1).max(200),type:z.literal('function'),function:z.object({name:z.string().min(1).max(100),arguments:z.string().max(16000)}),
})).max(6).optional()});
