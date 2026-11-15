import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'');
  return {
    plugins:[react()],
    resolve: {
      dedupe: ['react', 'react-dom', 'react-dom/client']
    },
    optimizeDeps: {
      include: ['react', 'react-dom', 'react-dom/client']
    },
    server:{
      proxy:{
        '/api':{
          target:'http://127.0.0.1:'+(env.API_PORT||'8787'),
          changeOrigin:true,
          timeout:240000,
          proxyTimeout:240000,
          configure:proxy=>proxy.on('proxyReq',(proxyReq,_req,res)=>{
            res.on('close',()=>{if(!res.writableFinished)proxyReq.destroy();});
          })
        }
      }
    }
  };
});

