import { createServer } from 'node:http';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Catalog,readSeed } from './catalog.ts';
import { LMStudio } from './lmstudio.ts';
import { Orbit } from './orbit.ts';
import { createHandler } from './http.ts';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const catalog=new Catalog(resolve(root,process.env.EARTHSIGNAL_DB_PATH??'.local/earthsignal.sqlite'),readSeed());
const lm=new LMStudio(),orbit=new Orbit(catalog,lm);
const port=Number(process.env.API_PORT??8787);
const server=createServer(createHandler({catalog,lm,orbit,root,port:()=>port}));
server.listen(port,'127.0.0.1',()=>console.log(`EarthSignal API: http://127.0.0.1:${port} · SQLite · LM Studio ${lm.base}`));
for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>server.close(()=>{catalog.close();process.exit(0);}));
