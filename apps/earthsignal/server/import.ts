import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {Catalog,readSeed} from './catalog.ts';
const file=process.argv[2];
const catalog=new Catalog(resolve(process.env.EARTHSIGNAL_DB_PATH??'.local/earthsignal.sqlite'));
try {console.log(`Imported ${catalog.import(file?JSON.parse(readFileSync(file,'utf8')):readSeed())} events (upsert).`);}finally{catalog.close();}
