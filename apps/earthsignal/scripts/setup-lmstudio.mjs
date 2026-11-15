import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';

// A model.yaml profile reuses the downloaded weights. No weight or global setting is changed.
const target=join(homedir(),'.lmstudio/hub/models/earthsignal/orbit-qwen3.6/model.yaml');
const content=`# EarthSignal Orbit: local, low-latency Qwen profile. Uses existing downloaded weights.
model: earthsignal/orbit-qwen3.6
base:
  - key: mlx-community/qwen3.6-35b-a3b-4bit
    sources:
      - type: huggingface
        user: mlx-community
        repo: Qwen3.6-35B-A3B-4bit
config:
  operation:
    fields:
      - key: llm.prediction.reasoning.parsing
        value:
          enabled: true
          startString: "<think>"
          endString: "</think>"
customFields:
  - key: enableThinking
    displayName: Enable Thinking
    description: Orbit uses direct tool calls for responsive navigation.
    type: boolean
    defaultValue: false
    effects:
      - type: setJinjaVariable
        variable: enable_thinking
metadataOverrides:
  domain: llm
  architectures:
    - qwen3_5_moe
  compatibilityTypes:
    - safetensors
  paramsStrings:
    - 35B-A3B
  vision: true
  reasoning: true
  trainedForToolUse: true
`;
let existing;try{existing=await readFile(target,'utf8');}catch(e){if(e.code!=='ENOENT')throw e;}
if(existing!==undefined&&existing!==content)throw new Error('An edited Orbit profile already exists. Review it before replacing: '+target);
await mkdir(join(target,'..'),{recursive:true});
await writeFile(target,content);
console.log('Orbit model profile ready: '+target);
console.log('Load earthsignal/orbit-qwen3.6 in LM Studio (context 8192, parallel 1). No weights are downloaded by this script.');
