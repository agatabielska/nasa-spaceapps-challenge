import {createContext} from 'react';
import {stableHeight,blockStops,clamp,CLOSE_DEPTH,holdProgress,journeyStops,layoutJourney,makeCamera,nextStop,prevStop,project,sceneAtScroll,shotAt,smooth,type Camera,type Layout} from './path';

export type JourneyFrame={camera:Camera;speed:number;moved:boolean;time:number;hold:Record<string,number>;progress:number;chapter:number;marks:number[]};
// data-hold: minimum screens to rest on a scene · data-steps: stops while it plays, as fractions of its hold ·
// data-dwell: autopilot pause on each content block
// in seconds · data-pace: autopilot speed through the scene, in screens per second.
type Scene={el:HTMLElement;id:string;close:boolean;minHold:number;steps?:number[];dwell:number;pace:number};
type Autopilot={phase:'arrive'|'rest'|'move';wait:number;y:number;from:number;to:number;time:number;duration:number};
// A scene that shows several things in turn while the camera rests on it (About tours the event types).
// next/prev step inside it and return false once there is nothing left to show that way; busy holds the
// autopilot on the scene until its tour is done.
export type SceneStepper={next():boolean;prev():boolean;busy():boolean};
export type JourneyEvents={onChapter:(id:string,index:number)=>void;onAutopilot:(on:boolean)=>void};
// Room left above a content block when the camera stops on it (top bar), and below it (presenter bar).
const STOP_GAP=76,BAR_ROOM=96;
// Vertical position of an element inside its scene, unaffected by the scene's 3D transform.
function offsetIn(el:HTMLElement,scene:HTMLElement){
  let y=0,node:HTMLElement|null=el;
  while(node&&node!==scene){y+=node.offsetTop;node=node.offsetParent as HTMLElement|null;}
  return node===scene?y:0;
}
// The scene's content split at [data-stop] markers, without the empty padding at the bottom of the scene.
function contentBlocks(scene:HTMLElement){
  const end=Math.max(0,...[...scene.children].map(child=>{const el=child as HTMLElement;return el.offsetTop+el.offsetHeight-parseFloat(getComputedStyle(el).paddingBottom||'0');}));
  const tops=[...scene.querySelectorAll<HTMLElement>('[data-stop]')].map(el=>({top:offsetIn(el,scene),margin:parseFloat(getComputedStyle(el).marginTop||'0')}));
  const blocks:{top:number;bottom:number}[]=[];
  let top=0;
  for(const mark of tops){blocks.push({top,bottom:mark.top-mark.margin});top=mark.top;}
  blocks.push({top,bottom:end});
  return blocks;
}
// Seconds an autopilot move takes to reach full speed, and to stop again.
const RAMP=.8;
// Position along a move at time t (0..1): accelerate for the first r, glide, decelerate for the last r.
export function easeMove(t:number,r:number){
  if(r<=0)return t;
  const v=1/(1-r);
  if(t<r)return v*t*t/(2*r);
  if(t>1-r)return 1-v*(1-t)*(1-t)/(2*r);
  return v*(t-r/2);
}
const editable='input,textarea,select,[contenteditable=""],[contenteditable=true],[role=slider]';

// Drives the landing page as one continuous camera flight. The page still scrolls natively (scrollbar,
// keyboard, touch and links keep working); a tall spacer provides the scroll length, and the camera eases
// towards the scroll position with some inertia. Scenes ([data-scene]) are fixed layers projected in 3D.
// Jump to y at once. The page scrolls smoothly by CSS (for anchor links), and behavior:'instant' is not
// understood by every Safari (older ones reject the call), so smooth scrolling is switched off just for this.
export function instantly(scroll:()=>void){
  const root=document.documentElement,before=root.style.scrollBehavior;
  root.style.scrollBehavior='auto';scroll();root.style.scrollBehavior=before;
}
export const jumpTo=(y:number)=>instantly(()=>window.scrollTo(0,y));
export class Journey{
  private scenes:Scene[];
  private layout!:Layout;
  private cam=Number.NaN;
  private speed=0;
  private lastTime=0;
  private frame=0;
  private dirty=true;
  private chapter=-1;
  private listeners=new Set<(frame:JourneyFrame)=>void>();
  private resize:ResizeObserver;
  private restoration=history.scrollRestoration;
  private stops:number[]=[];
  private marks:number[]=[];
  private auto:Autopilot|null=null;
  private steppers=new Map<string,SceneStepper>();
  latest:JourneyFrame|null=null;

  constructor(private root:HTMLElement,world:HTMLElement,private spacer:HTMLElement,private events:JourneyEvents){
    this.scenes=[...world.querySelectorAll<HTMLElement>('[data-scene]')].map(el=>({el,id:el.id,close:el.dataset.close!==undefined,minHold:Number(el.dataset.hold??.3),
      steps:el.dataset.steps?el.dataset.steps.split(',').map(Number):undefined,dwell:Number(el.dataset.dwell??6),pace:Number(el.dataset.pace??.75)}));
    history.scrollRestoration='manual';
    this.measure();
    // Open a deep link (/#etna) on its scene, without flying through everything before it.
    const hash=location.hash.slice(1),found=this.index(hash);
    // An unknown anchor (/#xyz) opens the start screen and is dropped from the address.
    if(hash&&found<0)history.replaceState(null,'',location.pathname+location.search);
    const start=this.layout.scenes[Math.max(0,found)].start;
    jumpTo(start);this.cam=start;
    this.resize=new ResizeObserver(()=>this.relayout());
    this.scenes.forEach(sc=>this.resize.observe(sc.el));
    window.addEventListener('resize',this.relayout);
    document.addEventListener('click',this.onClick);
    root.addEventListener('focusin',this.onFocus);
    document.addEventListener('visibilitychange',this.wake);
    window.addEventListener('keydown',this.onKey);
    for(const type of ['wheel','touchstart','pointerdown'] as const)window.addEventListener(type,this.interrupt,{passive:true,capture:true});
    this.wake();
  }
  subscribe(fn:(frame:JourneyFrame)=>void){this.listeners.add(fn);if(this.latest)fn({...this.latest,moved:true});return()=>{this.listeners.delete(fn);};}
  index(id:string){return this.scenes.findIndex(sc=>sc.id===id);}
  goTo(id:string){
    const i=this.index(id);if(i<0)return;
    this.scrollTo(this.layout.scenes[i].start);
    history.replaceState(null,'',`#${id}`);
  }
  // Presenter controls: step to the next or previous stop, jump to an end, or seek along the whole journey.
  next(){
    this.setAutopilot(false);
    const y=window.scrollY,to=nextStop(this.stops,y),sc=this.restingIn(y);
    if(sc&&to>sc.end+.5&&this.steppers.get(sc.id)?.next())return;
    this.scrollTo(to);
  }
  prev(){
    this.setAutopilot(false);
    const y=window.scrollY,to=prevStop(this.stops,y),sc=this.restingIn(y);
    if(sc&&to<sc.start-.5&&this.steppers.get(sc.id)?.prev())return;
    this.scrollTo(to);
  }
  // A scene registers itself to take the arrows while the camera rests on it; returns the unregister call.
  step(id:string,stepper:SceneStepper){this.steppers.set(id,stepper);return()=>{if(this.steppers.get(id)===stepper)this.steppers.delete(id);};}
  first(){this.setAutopilot(false);this.scrollTo(0);}
  last(){this.setAutopilot(false);this.scrollTo(this.layout.total);}
  seek(fraction:number){this.setAutopilot(false);this.scrollTo(clamp(fraction)*this.layout.total);}
  get autopilot(){return this.auto!==null;}
  // Guided flight: rest on each scene, move through what it pans or plays, then fly on to the next one.
  setAutopilot(on:boolean){
    if(on===this.autopilot)return;
    if(on){
      const l=this.layout;let y=window.scrollY;
      if(y>=l.total-1)y=0;
      const sc=l.scenes[sceneAtScroll(l,y)];
      if(y<sc.start||y>sc.end)y=y>sc.end?l.scenes[Math.min(l.scenes.indexOf(sc)+1,l.scenes.length-1)].start:sc.start;
      this.scrollTo(y);this.auto={phase:'arrive',wait:0,y,from:y,to:y,time:0,duration:0};
    }else this.auto=null;
    this.events.onAutopilot(on);
  }
  destroy(){
    cancelAnimationFrame(this.frame);this.resize.disconnect();
    window.removeEventListener('resize',this.relayout);document.removeEventListener('click',this.onClick);
    this.root.removeEventListener('focusin',this.onFocus);document.removeEventListener('visibilitychange',this.wake);
    window.removeEventListener('keydown',this.onKey);
    for(const type of ['wheel','touchstart','pointerdown'] as const)window.removeEventListener(type,this.interrupt,{capture:true});
    for(const sc of this.scenes){sc.el.style.cssText='';delete sc.el.dataset.shown;}
    this.spacer.style.height='';history.scrollRestoration=this.restoration;
  }

  private screen={w:0,h:0};
  private measure(){
    const w=window.innerWidth,h=stableHeight(this.screen,w,window.innerHeight);this.screen={w,h};
    this.layout=layoutJourney(this.scenes.map(sc=>({id:sc.id,height:sc.el.offsetHeight,hold:sc.minHold*h,close:sc.close})),w,h);
    this.spacer.style.height=`${Math.ceil(this.layout.total+h)}px`;
    // A scene plays through data-steps, or stops at each content block (split at elements marked data-stop),
    // with extra stops only where a block is too tall for the screen.
    this.stops=journeyStops(this.layout,this.scenes.map((sc,i)=>{
      if(sc.steps)return sc.steps;
      const placed=this.layout.scenes[i];if(!placed.hold)return [];
      return blockStops(contentBlocks(sc.el),h,placed.pan,STOP_GAP,BAR_ROOM).map(y=>y/placed.hold).filter(f=>f>.001);
    }));
    this.marks=this.layout.scenes.map(sc=>this.layout.total?sc.start/this.layout.total:0);
    this.dirty=true;
  }
  // The scene whose hold contains scroll position y (not the flight after it).
  private restingIn(y:number){const sc=this.layout.scenes[sceneAtScroll(this.layout,y)];return y<=sc.end+.5?sc:null;}
  private scrollTo(y:number){jumpTo(y);}
  // Keep the camera on the same scene, at the same relative point, when sizes change.
  private relayout=()=>{
    const old=this.layout,s=Number.isNaN(this.cam)?0:this.cam;
    let i=old.scenes.findIndex(sc=>s<=sc.end);if(i<0)i=old.scenes.length-1;
    const sc=old.scenes[i],travelling=s<sc.start,fraction=travelling?(sc.start-s)/old.travel:0,offset=s-sc.start;
    this.measure();
    const next=this.layout.scenes[i],to=travelling?next.start-fraction*this.layout.travel:next.start+Math.min(offset,next.hold);
    if(Math.abs(to-s)>.5){this.scrollTo(to);this.cam=to;}
    if(this.auto)this.auto.y=window.scrollY;
  };
  // Any manual scrolling, touch or click takes the controls back from the autopilot.
  private interrupt=(e:Event)=>{
    if(!this.auto||(e.target as Element|null)?.closest?.('[data-autopilot]'))return;
    this.setAutopilot(false);
  };
  // Presentation keys, so a clicker or the arrows step from stop to stop instead of scrolling a few pixels.
  private onKey=(e:KeyboardEvent)=>{
    if(e.defaultPrevented||e.altKey||e.ctrlKey||e.metaKey)return;
    const target=e.target as Element|null;
    if(target?.closest?.(editable))return;
    const key=e.key;
    if(key==='p'||key==='P'){e.preventDefault();this.setAutopilot(!this.autopilot);return;}
    if(key===' '&&target?.closest?.('button,a,summary'))return;
    const forward=['ArrowDown','ArrowRight','PageDown'].includes(key)||(key===' '&&!e.shiftKey);
    const back=['ArrowUp','ArrowLeft','PageUp'].includes(key)||(key===' '&&e.shiftKey);
    if(!forward&&!back&&key!=='Home'&&key!=='End'){if(key!=='Shift'&&key!=='Tab')this.setAutopilot(false);return;}
    e.preventDefault();
    if(forward)this.next();else if(back)this.prev();else if(key==='Home')this.first();else this.last();
  };
  private drive(dt:number){
    const a=this.auto!,l=this.layout;
    // Someone dragged the scrollbar or the page jumped: hand control back.
    if(Math.abs(window.scrollY-a.y)>3){this.setAutopilot(false);return;}
    const i=sceneAtScroll(l,a.y),sc=l.scenes[i],info=this.scenes[i];
    if(a.phase==='arrive'){if(Math.abs(this.cam-a.y)<l.h*.01){a.phase='rest';a.wait=info.dwell;}return;}
    if(a.phase==='rest'){
      a.wait-=dt;if(a.wait>0)return;
      // A scene with a tour keeps the camera until the tour is done (with a safety limit, if it never says so).
      if(a.wait>-90&&this.steppers.get(info.id)?.busy())return;
      // Next move inside the scene: right through a scene that plays (the flight), otherwise on to the next
      // content block, resting on each one. With nothing left, fly on to the next scene.
      const last=i===l.scenes.length-1,limit=info.steps||last?sc.end:sc.start+sc.pan;
      const to=info.steps?limit:this.stops.find(stop=>stop>a.y+1&&stop<=limit+.5);
      if(to===undefined||to<=a.y+.5){
        if(last){this.setAutopilot(false);return;}
        a.y=l.scenes[i+1].start;this.scrollTo(a.y);a.y=window.scrollY;a.phase='arrive';return;
      }
      // The move ramps up and down gently, with a steady speed in between; a scene that plays (the flight)
      // runs at its own steady pace from start to end.
      a.from=a.y;a.to=to;a.time=0;a.duration=(a.to-a.from)/(info.pace*l.h)+(info.steps?0:RAMP);a.phase='move';
    }
    a.time+=dt;
    const t=a.duration>0?clamp(a.time/a.duration):1;
    a.y=a.from+(a.to-a.from)*easeMove(t,a.duration>0&&!info.steps?Math.min(.3,RAMP/a.duration):0);this.scrollTo(a.y);
    if(t>=1){a.phase='rest';a.wait=info.steps?2.5:info.dwell;}
  }
  private onClick=(e:MouseEvent)=>{
    const link=(e.target as Element|null)?.closest?.('a[href^="#"]');
    if(!link||!this.root.contains(link)||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey)return;
    const id=link.getAttribute('href')!.slice(1);
    if(this.index(id)<0)return;
    e.preventDefault();this.goTo(id);
  };
  // Tabbing into a scene that is not on screen flies the camera to it.
  private onFocus=(e:FocusEvent)=>{
    const target=e.target as HTMLElement,host=target.closest<HTMLElement>('[data-scene]');if(!host)return;
    const sc=this.layout.scenes[this.index(host.id)];if(!sc)return;
    const y=offsetIn(target,host);
    const h=this.layout.h,inView=window.scrollY>=sc.start&&window.scrollY<=sc.end&&y>=window.scrollY-sc.start&&y<window.scrollY-sc.start+h-80;
    if(!inView)this.scrollTo(sc.start+clamp(y-h*.35,0,sc.pan));
  };
  private wake=()=>{cancelAnimationFrame(this.frame);if(!document.hidden){this.lastTime=0;this.frame=requestAnimationFrame(this.tick);}};
  private tick=(time:number)=>{
    const dt=this.lastTime?Math.min(.05,(time-this.lastTime)/1000):0;this.lastTime=time;
    if(this.auto&&dt>0)this.drive(dt);
    const l=this.layout,target=clamp(window.scrollY,0,l.total),prev=this.cam;
    // Inertia: ease towards the scroll position, with a speed limit so long jumps become a visible flight.
    let next=Number.isNaN(prev)?target:prev+clamp((target-prev)*(1-Math.exp(-dt*4.2)),-dt*l.h*7,dt*l.h*7);
    if(Math.abs(target-next)<.25)next=target;
    this.cam=next;
    this.speed+=((dt>0?Math.abs(next-prev)/dt/l.h:0)-this.speed)*.2;
    const moved=this.dirty||next!==prev;
    if(moved||!this.latest)this.place(time);
    else this.latest={...this.latest,speed:this.speed,moved:false,time};
    this.dirty=false;
    for(const fn of this.listeners)fn(this.latest!);
    this.frame=requestAnimationFrame(this.tick);
  };
  private place(time:number){
    const l=this.layout,s=this.cam,shot=shotAt(l,s),camera=makeCamera(shot.pos,shot.fwd,shot.roll,l.focal,l.w,l.h);
    const hold:Record<string,number>={};
    this.scenes.forEach((sc,i)=>{
      const placed=l.scenes[i],el=sc.el,p=project(camera,placed.anchor);
      hold[sc.id]=holdProgress(placed,s);
      // Fade in from the distance, stay solid around the resting distance, fade out while passing through.
      // A scene with a close scene right behind it fades out in the first part of the push (the camera flies
      // through it), before the close scene fills in its details.
      const f=l.focal,nearFade=this.scenes[i+1]?.close?[f*(1-CLOSE_DEPTH*.6),f*(1-CLOSE_DEPTH*.3)]:[f*.36,f*.86];
      const opacity=p?smooth(nearFade[0],nearFade[1],p.d)*(1-smooth(f*2.6,f*3.9,p.d)):0;
      if(!p||opacity<.004){
        if(el.dataset.shown!=='0'){el.dataset.shown='0';el.style.opacity='0';el.style.transform='translate3d(-400vw,0,0)';el.style.pointerEvents='none';}
        return;
      }
      el.dataset.shown='1';
      const resting=Math.abs(p.s-1)<.002,x=resting?Math.round(p.x):p.x,y=resting?Math.round(p.y):p.y;
      el.style.transform=`translate3d(${x.toFixed(2)}px,${y.toFixed(2)}px,0) scale(${resting?1:p.s.toFixed(4)}) translateX(-50%)`;
      el.style.opacity=opacity>.995?'1':opacity.toFixed(3);
      el.style.zIndex=String(Math.round(1e5-p.d));
      // --arrive: 0 while the scene waits in the distance, 1 once the camera has arrived (scenes fill in their
      // details with it, e.g. About shows only the globe behind the hero title).
      // --approach: 0 while a close scene waits behind the previous one, rising evenly to 1 as the camera reaches it.
      el.style.setProperty('--approach',clamp((f*(1+CLOSE_DEPTH)-p.d)/(f*CLOSE_DEPTH)).toFixed(3));
      el.style.setProperty('--arrive',p.d<=f*1.03?'1':(1-smooth(f*1.03,f*(1+CLOSE_DEPTH*.3),p.d)).toFixed(3));
      el.style.pointerEvents=opacity>.9&&Math.abs(p.s-1)<.1?'auto':'none';
    });
    if(shot.chapter!==this.chapter){
      const first=this.chapter<0;this.chapter=shot.chapter;const id=this.scenes[shot.chapter].id;
      if(!first)history.replaceState(null,'',`#${id}`);
      this.events.onChapter(id,shot.chapter);
    }
    this.latest={camera,speed:this.speed,moved:true,time,hold,progress:l.total?s/l.total:0,chapter:shot.chapter,marks:this.marks};
  }
}

export const JourneyContext=createContext<Journey|null>(null);
// True while the autopilot runs, so scenes can demonstrate themselves (e.g. sweep the before/after dividers).
export const AutopilotContext=createContext(false);
