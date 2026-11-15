import { Gemini } from './gemini.ts';
import { LMStudio } from './lmstudio.ts';
import type { OrbitModel } from './model.ts';

export function createModel(env:NodeJS.ProcessEnv=process.env):OrbitModel{
  switch(env.ORBIT_PROVIDER??'lmstudio'){
    case 'lmstudio':return new LMStudio(env);
    case 'gemini':return new Gemini(env);
    default:throw new Error('ORBIT_PROVIDER must be lmstudio or gemini');
  }
}
