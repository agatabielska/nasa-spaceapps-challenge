import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('..',import.meta.url)));
const children=[spawn(process.execPath,['--env-file-if-exists=.env.local','--watch','--watch-preserve-output','--experimental-strip-types','server/index.ts'],{stdio:'inherit'}),
  spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort'],{stdio:'inherit'})];
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const child of children)child.kill('SIGTERM');setTimeout(()=>process.exit(code),400).unref();}
for(const child of children){child.on('error',e=>{console.error(e.message);stop(1);});child.on('exit',code=>stop(code??0));}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
