import type { IncomingMessage, ServerResponse } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { ZodError } from 'zod';
import type { Catalog } from './catalog.ts';
import type { LMStudio } from './lmstudio.ts';
import type { Orbit } from './orbit.ts';
import { chatSchema,searchSchema,ServiceError } from './contracts.ts';

// Largest request body accepted. A chat message may hold 4000 characters (up to 4 bytes each in UTF-8) plus the
// map context the browser sends with it.
export const BODY_LIMIT=40000;
function json(res:ServerResponse,status:number,data:unknown){if(res.destroyed)return;res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data));}
async function body(req:IncomingMessage){let content='';for await(const chunk of req){content+=chunk;if(Buffer.byteLength(content)>BODY_LIMIT)throw new ServiceError(413,'BODY_LIMIT','Message too large');}try{return JSON.parse(content);}catch{throw new ServiceError(400,'INVALID_JSON','Invalid JSON body');}}
// A malformed percent-encoding in the URL is the client's mistake: answer 400 instead of failing with 500.
function decode(part:string){try{return decodeURIComponent(part);}catch{throw new ServiceError(400,'BAD_PATH','Malformed URL encoding');}}

/** The HTTP handler: local API plus the built app. `port` is read per request, so tests can listen on any port. */
export function createHandler({catalog,lm,orbit,root,port}:{catalog:Catalog;lm:LMStudio;orbit:Orbit;root:string;port:()=>number}){
  return async(req:IncomingMessage,res:ServerResponse)=>{
  try {
    // Keep the local database/model API inaccessible to unrelated browser origins.
    const origin=req.headers.origin;
    const p=port(),origins=new Set(['http://127.0.0.1:5173','http://localhost:5173',`http://127.0.0.1:${p}`,`http://localhost:${p}`]);
    if(origin&&!origins.has(origin))throw new ServiceError(403,'ORIGIN','Origin is not permitted');
    if(req.headers.host&&!['127.0.0.1','localhost','[::1]'].some(h=>req.headers.host===`${h}:${p}`||req.headers.host===h))throw new ServiceError(403,'HOST','Host is not permitted');
    const url=new URL(req.url??'/',`http://127.0.0.1:${p}`);
    if(req.method==='GET'&&url.pathname==='/api/events')return json(res,200,catalog.search({}));
    if(req.method==='POST'&&url.pathname==='/api/events/search')return json(res,200,catalog.search(searchSchema.parse(await body(req))));
    if(req.method==='GET'&&url.pathname.startsWith('/api/events/')){
      const event=catalog.get(decode(url.pathname.slice('/api/events/'.length)));
      if(!event)throw new ServiceError(404,'NOT_FOUND','Event not found');return json(res,200,event);
    }
    if(req.method==='GET'&&url.pathname==='/api/health')return json(res,200,{ok:true,database:'sqlite',events:catalog.search({}).total});
    if(req.method==='GET'&&url.pathname==='/api/orbit/status')return json(res,200,await lm.status());
    if(req.method==='POST'&&url.pathname==='/api/orbit/chat'){
      const input=chatSchema.parse(await body(req)),controller=new AbortController();
      // Stop the model call when the browser cancels or disconnects, so the session is free again.
      res.on('close',()=>{if(!res.writableFinished)controller.abort();});
      return json(res,200,await orbit.chat(input,controller.signal));
    }
    if(url.pathname.startsWith('/api/'))throw new ServiceError(404,'NOT_FOUND','Endpoint not found');
    if(req.method!=='GET'&&req.method!=='HEAD')throw new ServiceError(405,'METHOD','Method not allowed');
    const dist=resolve(root,'dist');let file=resolve(dist,'.'+decode(url.pathname));
    if(!file.startsWith(dist+sep))file=resolve(dist,'index.html');
    try {if(!(await stat(file)).isFile())file=resolve(dist,'index.html');}catch{file=resolve(dist,'index.html');}
    let content:Buffer;try{content=await readFile(file);}catch{throw new ServiceError(404,'BUILD_MISSING','Run npm run build, or npm run dev for development.');}
    const mime:Record<string,string>={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.geojson':'application/geo+json','.json':'application/json','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.ttf':'font/ttf'};
    res.writeHead(200,{'Content-Type':mime[extname(file)]??'application/octet-stream','X-Content-Type-Options':'nosniff'});res.end(req.method==='HEAD'?undefined:content);
  }catch(e){
    if(e instanceof ZodError)return json(res,400,{error:{code:'VALIDATION',message:'Invalid request parameters',details:e.issues.map(i=>({path:i.path,message:i.message}))}});
    if(e instanceof ServiceError)return json(res,e.status,{error:{code:e.code,message:e.message}});
    console.error('API error:',e instanceof Error?e.message:'Unknown error');json(res,500,{error:{code:'INTERNAL',message:'Local API error. Check the terminal.'}});
  }
  };
}
