import { createServer } from 'node:http';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Catalog,readSeed } from './catalog.ts';
import { createModel } from './model-provider.ts';
import { Orbit } from './orbit.ts';
import { createHandler } from './http.ts';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const catalog=new Catalog(resolve(root,process.env.EARTHSIGNAL_DB_PATH??'.local/earthsignal.sqlite'),readSeed());
const orbitEnabled=process.env.ORBIT_ENABLED!=='false';
// A disabled assistant must not depend on model credentials or a model service.
const lm=createModel(orbitEnabled?process.env:{}),orbit=new Orbit(catalog,lm);
// Render supplies PORT and RENDER_EXTERNAL_URL. Keep the local-only defaults for development.
const port=Number(process.env.PORT??process.env.API_PORT??8787);
if(!Number.isInteger(port)||port<1||port>65535)throw new Error('PORT/API_PORT must be an integer between 1 and 65535');
const host=process.env.HOST??(process.env.RENDER==='true'?'0.0.0.0':'127.0.0.1');
const server=createServer(createHandler({catalog,lm,orbit,root,port:()=>port,
  publicUrl:process.env.PUBLIC_URL??process.env.RENDER_EXTERNAL_URL,orbitEnabled}));
server.listen(port,host,()=>console.log(`EarthSignal API: http://${host}:${port} · SQLite · Orbit ${orbitEnabled?'enabled':'disabled'}`));
for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>server.close(()=>{catalog.close();process.exit(0);}));
