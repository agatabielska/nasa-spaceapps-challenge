import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer,request,type Server} from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Catalog,readSeed} from './catalog.ts';
import {LMStudio} from './lmstudio.ts';
import {Orbit} from './orbit.ts';
import {BODY_LIMIT,createHandler} from './http.ts';

// The real handler on a free port, with a throwaway database; LM Studio is never reached by these requests.
async function start(options:{publicUrl?:string;orbitEnabled?:boolean}={}){
  const dir=mkdtempSync(join(tmpdir(),'earthsignal-http-')),catalog=new Catalog(join(dir,'events.sqlite'),readSeed());
  const lm=new LMStudio({}),orbit=new Orbit(catalog,lm),root=resolve(fileURLToPath(new URL('..',import.meta.url)));
  let port=0;
  const server:Server=createServer(createHandler({catalog,lm,orbit,root,port:()=>port,...options}));
  await new Promise<void>(done=>server.listen(0,'127.0.0.1',done));
  port=(server.address() as {port:number}).port;
  return {port,close:()=>new Promise<void>(done=>server.close(()=>{catalog.close();rmSync(dir,{recursive:true,force:true});done();}))};
}
// Raw requests, so tests control the exact path (no URL normalisation) and the Host/Origin headers.
function call(port:number,path:string,{method='GET',headers={},body}:{method?:string;headers?:Record<string,string>;body?:string}={}){
  return new Promise<{status:number;text:string}>((ok,fail)=>{
    const req=request({host:'127.0.0.1',port,path,method,headers:{host:`127.0.0.1:${port}`,...headers}},res=>{let text='';res.setEncoding('utf8');res.on('data',c=>text+=c);res.on('end',()=>ok({status:res.statusCode??0,text}));});
    req.on('error',fail);if(body!==undefined)req.write(body);req.end();
  });
}
const code=(text:string)=>JSON.parse(text).error?.code;

test('health and catalog answer; unknown API paths and methods are refused',async()=>{
  const s=await start();
  try{
    const health=await call(s.port,'/api/health');assert.equal(health.status,200);assert.equal(JSON.parse(health.text).events,15);
    assert.equal((await call(s.port,'/api/events/etna')).status,200);
    assert.equal(code((await call(s.port,'/api/events/nope')).text),'NOT_FOUND');
    assert.equal(code((await call(s.port,'/api/nope')).text),'NOT_FOUND');
    assert.equal((await call(s.port,'/',{method:'PUT'})).status,405);
  }finally{await s.close();}
});
test('foreign origins and hosts are refused',async()=>{
  const s=await start();
  try{
    const origin=await call(s.port,'/api/events',{headers:{origin:'https://evil.example'}});assert.equal(origin.status,403);assert.equal(code(origin.text),'ORIGIN');
    assert.equal((await call(s.port,'/api/events',{headers:{origin:'http://localhost:5173'}})).status,200);
    const host=await call(s.port,'/api/health',{headers:{host:'evil.example'}});assert.equal(host.status,403);assert.equal(code(host.text),'HOST');
  }finally{await s.close();}
});
test('configured public deployment serves its own origin without trusting other domains or forwarded headers',async()=>{
  const s=await start({publicUrl:'https://earthsignal-test.onrender.com'});
  try{
    const headers={host:'earthsignal-test.onrender.com',origin:'https://earthsignal-test.onrender.com'};
    const catalog=await call(s.port,'/api/events',{headers});assert.equal(catalog.status,200);assert.equal(JSON.parse(catalog.text).total,15);
    const search=await call(s.port,'/api/events/search',{method:'POST',headers:{...headers,'content-type':'application/json'},body:JSON.stringify({countries:['IT']})});
    assert.equal(search.status,200);assert.equal(JSON.parse(search.text).events[0].id,'etna');
    assert.equal((await call(s.port,'/api/health',{headers:{host:headers.host}})).status,200);
    assert.equal((await call(s.port,'/api/events',{headers:{...headers,origin:'https://other.onrender.com'}})).status,403);
    assert.equal((await call(s.port,'/api/events',{headers:{host:'evil.example','x-forwarded-host':headers.host}})).status,403);
  }finally{await s.close();}
});
test('disabled Orbit reports unavailable and rejects chat before any model request',async()=>{
  const s=await start({orbitEnabled:false});
  try{
    const status=await call(s.port,'/api/orbit/status');assert.equal(status.status,200);assert.equal(JSON.parse(status.text).available,false);
    const chat=await call(s.port,'/api/orbit/chat',{method:'POST',body:'{}'});assert.equal(chat.status,503);assert.equal(code(chat.text),'ORBIT_DISABLED');
    assert.equal((await call(s.port,'/api/events')).status,200);
  }finally{await s.close();}
});
test('malformed URL encoding is a 400, and paths cannot leave the build folder',async()=>{
  const s=await start();
  try{
    for(const path of ['/api/events/%E0%A4','/%E0%A4']){const r=await call(s.port,path);assert.equal(r.status,400);assert.equal(code(r.text),'BAD_PATH');}
    for(const path of ['/../package.json','/%2e%2e/package.json','/..%2fpackage.json','/../../server/http.ts']){
      const r=await call(s.port,path);
      assert.ok(!r.text.includes('"name": "earthsignal"')&&!r.text.includes('createHandler'),`${path} leaked a file outside dist`);
    }
  }finally{await s.close();}
});
test('request bodies are validated and size-limited',async()=>{
  const s=await start();
  try{
    const json={'content-type':'application/json'};
    assert.equal(code((await call(s.port,'/api/events/search',{method:'POST',headers:json,body:'{bad'})).text),'INVALID_JSON');
    assert.equal(code((await call(s.port,'/api/events/search',{method:'POST',headers:json,body:'{"foo":1}'})).text),'VALIDATION');
    assert.equal(code((await call(s.port,'/api/events/search',{method:'POST',headers:json,body:'{"from":"2026-13-40"}'})).text),'VALIDATION');
    const big=await call(s.port,'/api/events/search',{method:'POST',headers:json,body:JSON.stringify({search:'a'.repeat(BODY_LIMIT)})});
    assert.equal(big.status,413);
    // The longest allowed chat message in 3-byte characters fits the body limit (it fails validation on the
    // session id instead, before any model call).
    const long=await call(s.port,'/api/orbit/chat',{method:'POST',headers:json,body:JSON.stringify({message:'€'.repeat(4000),sessionId:'not-a-uuid'})});
    assert.equal(long.status,400);assert.equal(code(long.text),'VALIDATION');
  }finally{await s.close();}
});
