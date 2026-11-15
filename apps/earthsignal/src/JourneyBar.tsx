import {useContext,useEffect,useRef,useState,type KeyboardEvent as ReactKeyboardEvent,type PointerEvent as ReactPointerEvent} from 'react';
import {ArrowDown,ArrowUp,CircleDashed,Pause,Play} from 'lucide-react';
import {JourneyContext,jumpTo} from './journey/engine';

type Chapter={id:string;label:string};
const clamp=(v:number)=>Math.max(0,Math.min(1,v));

// Presenter HUD along the bottom, as in the prototype: the project line on the left, the chapter counter, a thin
// camera-position track with a tick per scene and the percentage in the middle, and square controls in the
// bottom-right corner (autopilot, background motion, previous and next stop). With reduced motion it drives an
// ordinary scrolling page and the autopilot and motion controls are left out.
export default function JourneyBar({chapters,chapter,autopilot,paused,onPause}:{chapters:Chapter[];chapter:string;autopilot:boolean;paused:boolean;onPause?:()=>void}){
  const journey=useContext(JourneyContext);
  const track=useRef<HTMLDivElement>(null),fill=useRef<HTMLSpanElement>(null),knob=useRef<HTMLSpanElement>(null),percent=useRef<HTMLSpanElement>(null);
  const progress=useRef(0);
  const [marks,setMarks]=useState<number[]>([]);
  const index=Math.max(0,chapters.findIndex(item=>item.id===chapter));
  useEffect(()=>{
    let shown=-1,lastMarks:number[]|null=null;
    const show=(p:number)=>{
      progress.current=p;if(Math.abs(p-shown)<.0005)return;shown=p;
      fill.current!.style.transform=`scaleX(${p.toFixed(4)})`;knob.current!.style.left=`${(p*100).toFixed(2)}%`;
      const value=Math.round(p*100);percent.current!.textContent=`${value}%`;track.current!.setAttribute('aria-valuenow',String(value));
    };
    if(journey)return journey.subscribe(frame=>{show(frame.progress);if(frame.marks!==lastMarks){lastMarks=frame.marks;setMarks(frame.marks);}});
    const update=()=>{
      const max=document.documentElement.scrollHeight-window.innerHeight;
      show(max>0?window.scrollY/max:0);
      setMarks(chapters.map(item=>{const el=document.getElementById(item.id);return el&&max>0?clamp((el.getBoundingClientRect().top+window.scrollY)/max):0;}));
    };
    update();
    window.addEventListener('scroll',update,{passive:true});window.addEventListener('resize',update);
    return()=>{window.removeEventListener('scroll',update);window.removeEventListener('resize',update);};
  },[journey,chapters]);
  const flowTo=(i:number)=>document.getElementById(chapters[Math.max(0,Math.min(chapters.length-1,i))].id)?.scrollIntoView({block:'start'});
  const step=(dir:1|-1)=>{if(journey){if(dir>0)journey.next();else journey.prev();}else flowTo(index+dir);};
  const seek=(fraction:number)=>{
    if(journey)journey.seek(fraction);
    else jumpTo(clamp(fraction)*(document.documentElement.scrollHeight-window.innerHeight));
  };
  const fromPointer=(e:ReactPointerEvent<HTMLDivElement>)=>{const r=e.currentTarget.getBoundingClientRect();seek((e.clientX-r.left)/r.width);};
  const onKey=(e:ReactKeyboardEvent<HTMLDivElement>)=>{
    const keys:Record<string,()=>void>={ArrowRight:()=>seek(progress.current+.02),ArrowUp:()=>seek(progress.current+.02),ArrowLeft:()=>seek(progress.current-.02),ArrowDown:()=>seek(progress.current-.02),
      PageDown:()=>step(1),PageUp:()=>step(-1),Home:()=>seek(0),End:()=>seek(1)};
    const action=keys[e.key];if(!action)return;
    e.preventDefault();action();
  };
  const count=`${String(index+1).padStart(2,'0')} / ${String(chapters.length).padStart(2,'0')}`;
  return <div className="sp-bar" role="group" aria-label="Journey controls">
    <p className="sp-bar-id" aria-hidden="true">NASA Space Apps Challenge</p>
    <div className="sp-bar-center">
      <div className="sp-bar-row">
        <b className="sp-bar-count">{count}</b>
        <div className="sp-bar-track" ref={track} role="slider" tabIndex={0} aria-label="Journey progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={0}
          aria-valuetext={chapters[index].label}
          onPointerDown={e=>{if(e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);fromPointer(e);}}
          onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))fromPointer(e);}}
          onKeyDown={onKey}>
          <span className="sp-bar-rail"/>
          {marks.map((mark,i)=><i key={chapters[i]?.id??i} style={{left:`${mark*100}%`}}/>)}
          <span className="sp-bar-fill" ref={fill}/>
          <span className="sp-bar-knob" ref={knob}/>
        </div>
        <span className="sp-bar-percent" ref={percent} aria-hidden="true">0%</span>
      </div>
      <p className="sp-bar-chapter" aria-live="polite">{chapters[index].label}</p>
    </div>
    <div className="sp-bar-controls">
      {journey&&<button type="button" data-autopilot aria-pressed={autopilot} aria-label="Autopilot" title="Autopilot: guided flight through every scene (P)"
        onClick={()=>journey.setAutopilot(!autopilot)}>{autopilot?<Pause size={18} aria-hidden="true"/>:<Play size={18} aria-hidden="true"/>}</button>}
      {onPause&&<button type="button" aria-pressed={paused} aria-label="Pause background motion" title="Pause background motion" onClick={onPause}><CircleDashed size={18} aria-hidden="true"/></button>}
      <button type="button" onClick={()=>step(-1)} aria-label="Previous stop" title="Previous stop (↑ or Page Up)"><ArrowUp size={18} aria-hidden="true"/></button>
      <button type="button" onClick={()=>step(1)} aria-label="Next stop" title="Next stop (↓, Space or Page Down)"><ArrowDown size={18} aria-hidden="true"/></button>
    </div>
  </div>;
}
