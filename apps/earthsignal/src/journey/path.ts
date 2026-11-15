// Camera maths for the landing journey. World units are CSS pixels: x right, y down, z towards the viewer.
// A scene seen from exactly one focal length away is drawn at scale 1, so text at rest is never resampled.
export type Vec=[number,number,number];
export const add=(a:Vec,b:Vec):Vec=>[a[0]+b[0],a[1]+b[1],a[2]+b[2]];
export const sub=(a:Vec,b:Vec):Vec=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
export const scale=(a:Vec,k:number):Vec=>[a[0]*k,a[1]*k,a[2]*k];
export const dot=(a:Vec,b:Vec)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
export const cross=(a:Vec,b:Vec):Vec=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
export const norm=(a:Vec):Vec=>{const d=Math.hypot(a[0],a[1],a[2])||1;return [a[0]/d,a[1]/d,a[2]/d];};
export const clamp=(v:number,min=0,max=1)=>Math.max(min,Math.min(max,v));
export const smooth=(a:number,b:number,x:number)=>{const t=clamp((x-a)/(b-a));return t*t*(3-2*t);};

export type Camera={pos:Vec;fwd:Vec;right:Vec;down:Vec;focal:number;w:number;h:number};
export function makeCamera(pos:Vec,fwd:Vec,roll:number,focal:number,w:number,h:number):Camera{
  const f=norm(fwd),r0=norm(cross(f,[0,1,0])),d0=cross(r0,f),c=Math.cos(roll),s=Math.sin(roll);
  return {pos,fwd:f,right:add(scale(r0,c),scale(d0,s)),down:sub(scale(d0,c),scale(r0,s)),focal,w,h};
}
// Screen position of a world point, its distance along the view axis and its scale; null when behind the camera.
export function project(cam:Camera,q:Vec,near=1){
  const v=sub(q,cam.pos),d=dot(v,cam.fwd);if(d<near)return null;
  const s=cam.focal/d;
  return {x:cam.w/2+dot(v,cam.right)*s,y:cam.h/2+dot(v,cam.down)*s,d,s};
}
const bezier=(a:Vec,b:Vec,c:Vec,d:Vec,u:number):Vec=>{const v=1-u;return add(add(scale(a,v*v*v),scale(b,3*v*v*u)),add(scale(c,3*v*u*u),scale(d,u*u*u)));};
const bezierTangent=(a:Vec,b:Vec,c:Vec,d:Vec,u:number):Vec=>{const v=1-u;return add(add(scale(sub(b,a),3*v*v),scale(sub(c,b),6*v*u)),scale(sub(d,c),3*u*u));};

// close: the scene waits right behind the previous one, centred on it, and the camera flies straight through
// the previous scene to it (the hero title in front of the About globe).
export type SceneSize={id:string;height:number;hold:number;close?:boolean};
export type PlacedScene={id:string;anchor:Vec;start:number;end:number;pan:number;hold:number;close:boolean};
// How far behind the previous scene a close scene sits, as a fraction of the focal length.
export const CLOSE_DEPTH=.5;
export type Layout={w:number;h:number;focal:number;gap:number;travel:number;total:number;scenes:PlacedScene[]};
// Where each scene floats, relative to the previous one, in viewport widths and heights.
const DRIFT:[number,number][]=[[0,0],[.24,.1],[-.28,-.06],[.3,.12],[-.26,.04],[.2,-.08],[-.22,.08],[0,.1]];

// Scroll distance is split into holds (the camera rests on a scene, panning down if it is taller than
// the viewport) and travels (the camera flies a curved path to the next scene).
export function layoutJourney(sizes:SceneSize[],w:number,h:number):Layout{
  const focal=Math.max(700,h*1.1),gap=focal*3,travel=h*1.2;
  let s=0,y=0,x=0,z=0;
  const scenes=sizes.map((size,i)=>{
    if(i>0)s+=travel;
    const close=i>0&&!!size.close,pan=Math.max(0,size.height-h),hold=Math.max(pan,size.hold),[dx,dy]=close?[0,0]:DRIFT[i%DRIFT.length];
    if(i>0)z-=close?focal*CLOSE_DEPTH:gap;
    if(!close)x=dx*w;
    const anchor:Vec=[x,y+dy*h,z];
    y=anchor[1]+pan;
    const placed={id:size.id,anchor,start:s,end:s+hold,pan,hold,close};
    s+=hold;return placed;
  });
  return {w,h,focal,gap,travel,total:s,scenes};
}
// Camera position resting on scene i, scrolled `offset` pixels into it.
function rest(l:Layout,i:number,offset:number):Vec{
  const sc=l.scenes[i];
  return [sc.anchor[0],sc.anchor[1]+l.h/2+clamp(offset,0,sc.pan),sc.anchor[2]+l.focal];
}
export type Shot={pos:Vec;fwd:Vec;roll:number;chapter:number};
export function shotAt(l:Layout,s:number):Shot{
  s=clamp(s,0,l.total);
  for(let i=0;i<l.scenes.length;i++){
    const sc=l.scenes[i];
    if(s>sc.end&&i<l.scenes.length-1)continue;
    if(s>=sc.start||i===0)return {pos:rest(l,i,s-sc.start),fwd:[0,0,-1],roll:0,chapter:i};
    // Curved flight from scene i-1 to scene i: a cubic that swings out to one side and climbs a little.
    const t=clamp((s-(sc.start-l.travel))/l.travel),u=t*t*(3-2*t),side=i%2?1:-1;
    const a=rest(l,i-1,Infinity),d=rest(l,i,0);
    // A close scene is reached in a straight push forward, looking ahead the whole way.
    if(sc.close)return {pos:add(scale(a,1-u),scale(d,u)),fwd:[0,0,-1],roll:0,chapter:t<.5?i-1:i};
    const b=add(a,[side*.34*l.w,-.22*l.h,-l.gap*.42]),c=add(d,[side*.16*l.w,-.1*l.h,l.gap*.42]);
    const tangent=norm(bezierTangent(a,b,c,d,u)),bend=Math.sin(Math.PI*t);
    const fwd=norm(add(scale([0,0,-1],1-bend*.45),scale(tangent,bend*.45)));
    return {pos:bezier(a,b,c,d,u),fwd,roll:-tangent[0]*.32*bend,chapter:t<.5?i-1:i};
  }
  return {pos:rest(l,0,0),fwd:[0,0,-1],roll:0,chapter:0};
}
// How far through its hold a scene is (0 before it, 1 after it).
export function holdProgress(sc:PlacedScene,s:number){return sc.hold>0?clamp((s-sc.start)/sc.hold):s>=sc.start?1:0;}

// Places the presenter can step to with the keyboard or the bar: every scene start, plus evenly spaced points
// through a scene that pans (taller than the screen) or plays something during its hold (the drone flight).
// `steps` gives, per scene, explicit stops as fractions of its hold; the journey always ends on the very last pixel.
export function journeyStops(l:Layout,steps:(number[]|undefined)[]):number[]{
  const stops:number[]=[];
  l.scenes.forEach((sc,i)=>{
    stops.push(sc.start);
    const given=steps[i];
    if(given){for(const f of given){const y=sc.start+sc.hold*f;if(y>stops[stops.length-1]+1)stops.push(y);}return;}
    const n=sc.pan>0?Math.ceil(sc.pan/(l.h*.75)):0;
    for(let k=1;k<=n;k++)stops.push(sc.start+sc.pan*k/n);
  });
  if(stops[stops.length-1]<l.total-.5)stops.push(l.total);
  return stops;
}
export const nextStop=(stops:number[],y:number)=>stops.find(s=>s>y+1)??stops[stops.length-1];
export const prevStop=(stops:number[],y:number)=>[...stops].reverse().find(s=>s<y-1)??0;
// The scene whose hold, or the flight after it, contains scroll position y.
export function sceneAtScroll(l:Layout,y:number){let i=0;l.scenes.forEach((sc,k)=>{if(y>=sc.start-.5)i=k;});return i;}

// Where the camera stops inside a scene, as pan offsets: at the top of each content block (leaving `top` px for
// the top bar) and, only if a block is too tall to show above the bottom bar (`bottom` px), at evenly spaced
// points until its last line is visible. Blocks are {top,bottom} in scene pixels.
export function blockStops(blocks:{top:number;bottom:number}[],h:number,pan:number,top:number,bottom:number):number[]{
  const stops:number[]=[],room=h-top-bottom;
  blocks.forEach((block,i)=>{
    const first=i===0?0:clamp(block.top-top,0,pan),end=clamp(block.bottom-(h-bottom),0,pan);
    stops.push(first);
    if(end>first+40){const n=Math.ceil((end-first)/(room*.85));for(let k=1;k<=n;k++)stops.push(first+(end-first)*k/n);}
  });
  return stops.filter((s,i)=>i===0||s>stops[i-1]+1);
}
