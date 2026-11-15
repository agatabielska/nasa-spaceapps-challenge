import {createContext} from 'react';
import {clamp,holdProgress,layoutJourney,makeCamera,project,shotAt,smooth,type Camera,type Layout} from './path';

export type JourneyFrame={camera:Camera;speed:number;moved:boolean;time:number;hold:Record<string,number>};
type Scene={el:HTMLElement;id:string;minHold:number};

// Drives the landing page as one continuous camera flight. The page still scrolls natively (scrollbar,
// keyboard, touch and links keep working); a tall spacer provides the scroll length, and the camera eases
// towards the scroll position with some inertia. Scenes ([data-scene]) are fixed layers projected in 3D.
export class Journey{
  private scenes:Scene[];
  private layout!:Layout;
  private cam=Number.NaN;
  private speed=0;
  private last=0;
  private frame=0;
  private dirty=true;
  private chapter=-1;
  private listeners=new Set<(frame:JourneyFrame)=>void>();
  private resize:ResizeObserver;
  private restoration=history.scrollRestoration;
  latest:JourneyFrame|null=null;

  constructor(private root:HTMLElement,world:HTMLElement,private spacer:HTMLElement,private onChapter:(id:string,index:number)=>void){
    this.scenes=[...world.querySelectorAll<HTMLElement>('[data-scene]')].map(el=>({el,id:el.id,minHold:Number(el.dataset.hold??.3)}));
    history.scrollRestoration='manual';
    this.measure();
    // Open a deep link (/#etna) on its scene, without flying through everything before it.
    const start=this.layout.scenes[Math.max(0,this.index(location.hash.slice(1)))].start;
    window.scrollTo({top:start,behavior:'instant'});this.cam=start;
    this.resize=new ResizeObserver(()=>this.relayout());
    this.scenes.forEach(sc=>this.resize.observe(sc.el));
    window.addEventListener('resize',this.relayout);
    document.addEventListener('click',this.onClick);
    root.addEventListener('focusin',this.onFocus);
    document.addEventListener('visibilitychange',this.wake);
    this.wake();
  }
  subscribe(fn:(frame:JourneyFrame)=>void){this.listeners.add(fn);if(this.latest)fn({...this.latest,moved:true});return()=>{this.listeners.delete(fn);};}
  index(id:string){return this.scenes.findIndex(sc=>sc.id===id);}
  goTo(id:string){
    const i=this.index(id);if(i<0)return;
    window.scrollTo({top:this.layout.scenes[i].start,behavior:'instant'});
    history.replaceState(null,'',`#${id}`);
  }
  destroy(){
    cancelAnimationFrame(this.frame);this.resize.disconnect();
    window.removeEventListener('resize',this.relayout);document.removeEventListener('click',this.onClick);
    this.root.removeEventListener('focusin',this.onFocus);document.removeEventListener('visibilitychange',this.wake);
    for(const sc of this.scenes){sc.el.style.cssText='';delete sc.el.dataset.shown;}
    this.spacer.style.height='';history.scrollRestoration=this.restoration;
  }

  private measure(){
    const w=window.innerWidth,h=window.innerHeight;
    this.layout=layoutJourney(this.scenes.map(sc=>({id:sc.id,height:sc.el.offsetHeight,hold:sc.minHold*h})),w,h);
    this.spacer.style.height=`${Math.ceil(this.layout.total+h)}px`;
    this.dirty=true;
  }
  // Keep the camera on the same scene, at the same relative point, when sizes change.
  private relayout=()=>{
    const old=this.layout,s=Number.isNaN(this.cam)?0:this.cam;
    let i=old.scenes.findIndex(sc=>s<=sc.end);if(i<0)i=old.scenes.length-1;
    const sc=old.scenes[i],travelling=s<sc.start,fraction=travelling?(sc.start-s)/old.travel:0,offset=s-sc.start;
    this.measure();
    const next=this.layout.scenes[i],to=travelling?next.start-fraction*this.layout.travel:next.start+Math.min(offset,next.hold);
    if(Math.abs(to-s)>.5){window.scrollTo({top:to,behavior:'instant'});this.cam=to;}
  };
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
    let y=0,node:HTMLElement|null=target;
    while(node&&node!==host){y+=node.offsetTop;node=node.offsetParent as HTMLElement|null;}
    if(node!==host)y=0;
    const h=this.layout.h,inView=window.scrollY>=sc.start&&window.scrollY<=sc.end&&y>=window.scrollY-sc.start&&y<window.scrollY-sc.start+h-80;
    if(!inView)window.scrollTo({top:sc.start+clamp(y-h*.35,0,sc.pan),behavior:'instant'});
  };
  private wake=()=>{cancelAnimationFrame(this.frame);if(!document.hidden){this.last=0;this.frame=requestAnimationFrame(this.tick);}};
  private tick=(time:number)=>{
    const dt=this.last?Math.min(.05,(time-this.last)/1000):0;this.last=time;
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
      const opacity=p?smooth(l.focal*.36,l.focal*.86,p.d)*(1-smooth(l.focal*2.6,l.focal*3.9,p.d)):0;
      if(!p||opacity<.004){
        if(el.dataset.shown!=='0'){el.dataset.shown='0';el.style.opacity='0';el.style.transform='translate3d(-400vw,0,0)';el.style.pointerEvents='none';}
        return;
      }
      el.dataset.shown='1';
      const resting=Math.abs(p.s-1)<.002,x=resting?Math.round(p.x):p.x,y=resting?Math.round(p.y):p.y;
      el.style.transform=`translate3d(${x.toFixed(2)}px,${y.toFixed(2)}px,0) scale(${resting?1:p.s.toFixed(4)}) translateX(-50%)`;
      el.style.opacity=opacity>.995?'1':opacity.toFixed(3);
      el.style.zIndex=String(Math.round(1e5-p.d));
      el.style.pointerEvents=opacity>.9&&Math.abs(p.s-1)<.1?'auto':'none';
    });
    if(shot.chapter!==this.chapter){
      const first=this.chapter<0;this.chapter=shot.chapter;const id=this.scenes[shot.chapter].id;
      if(!first)history.replaceState(null,'',`#${id}`);
      this.onChapter(id,shot.chapter);
    }
    this.latest={camera,speed:this.speed,moved:true,time,hold};
  }
}

export const JourneyContext=createContext<Journey|null>(null);
