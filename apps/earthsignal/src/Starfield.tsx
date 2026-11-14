import {useEffect,useRef} from 'react';

type Star={x:number;y:number;z:number;r:number;phase:number;tint:string;ox:number;oy:number};
const tints=['#ffffff','#ffffff','#d6e9ff','#a9d4ff','#ffe8c7'];
const REPEL_RADIUS=150;

// Deep-space backdrop for the whole landing journey. Stars sit on depth layers: nearer ones drift further
// with the pointer and with scrolling, are pushed aside by the cursor and stretch a little while scrolling.
export default function Starfield({paused}:{paused:boolean}){
  const ref=useRef<HTMLCanvasElement>(null);
  const pausedRef=useRef(paused);
  const refresh=useRef<()=>void>(()=>{});
  useEffect(()=>{pausedRef.current=paused;refresh.current();},[paused]);
  useEffect(()=>{
    const canvas=ref.current,ctx=canvas?.getContext('2d');
    if(!canvas||!ctx)return;
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    let w=0,h=0,stars:Star[]=[],frame=0;
    const pointer={x:.5,y:.5,tx:.5,ty:.5,px:-9999,py:-9999};
    let smoothScroll=window.scrollY;
    const animated=()=>!pausedRef.current&&!reduced.matches&&!document.hidden;
    function build(){
      const dpr=Math.min(window.devicePixelRatio||1,2);
      w=window.innerWidth;h=window.innerHeight;
      canvas!.width=Math.round(w*dpr);canvas!.height=Math.round(h*dpr);
      ctx!.setTransform(dpr,0,0,dpr,0,0);
      const count=Math.round(Math.min(1000,Math.max(240,w*h/1700)));
      stars=Array.from({length:count},()=>{
        const z=Math.random()**1.7*.9+.1;
        return {x:Math.random(),y:Math.random(),z,r:.45+z*1.25*Math.random()+(Math.random()<.025?1.1:0),phase:Math.random()*6.283,tint:tints[Math.floor(Math.random()*tints.length)],ox:0,oy:0};
      });
    }
    function draw(time:number){
      frame=0;
      const live=animated();
      if(live){
        pointer.x+=(pointer.tx-pointer.x)*.05;pointer.y+=(pointer.ty-pointer.y)*.05;
        smoothScroll+=(window.scrollY-smoothScroll)*.14;
      }else smoothScroll=window.scrollY;
      const lag=live?window.scrollY-smoothScroll:0,span=h+40;
      ctx!.clearRect(0,0,w,h);
      for(const s of stars){
        let x=s.x*w+(.5-pointer.x)*70*s.z;
        let y=((s.y*span-smoothScroll*s.z*.32)%span+span)%span-20+(.5-pointer.y)*70*s.z;
        if(live){
          const dx=x-pointer.px,dy=y-pointer.py,d=Math.hypot(dx,dy);
          let tx=0,ty=0;
          if(d<REPEL_RADIUS&&d>.01){const push=(1-d/REPEL_RADIUS)**2*52*s.z;tx=dx/d*push;ty=dy/d*push;}
          s.ox+=(tx-s.ox)*.12;s.oy+=(ty-s.oy)*.12;
          x+=s.ox;y+=s.oy;
        }
        const twinkle=live?.78+.22*Math.sin(time*.0011*(.6+s.z)+s.phase):.9;
        ctx!.globalAlpha=(.3+.7*s.z)*twinkle;
        ctx!.fillStyle=ctx!.strokeStyle=s.tint;
        const streak=Math.max(-70,Math.min(70,lag*s.z*.22));
        if(Math.abs(streak)>1.5){ctx!.lineWidth=s.r;ctx!.beginPath();ctx!.moveTo(x,y);ctx!.lineTo(x,y+streak);ctx!.stroke();}
        else if(s.r<1.2)ctx!.fillRect(x,y,s.r*1.35,s.r*1.35);
        else{
          ctx!.beginPath();ctx!.arc(x,y,s.r*.8,0,6.283);ctx!.fill();
          if(s.r>2){ctx!.globalAlpha*=.22;ctx!.beginPath();ctx!.arc(x,y,s.r*2.6,0,6.283);ctx!.fill();}
        }
      }
      ctx!.globalAlpha=1;
      if(live)frame=requestAnimationFrame(draw);
    }
    const schedule=()=>{if(!frame)frame=requestAnimationFrame(draw);};
    const onResize=()=>{build();schedule();};
    const onPointer=(e:PointerEvent)=>{
      if(e.pointerType==='touch')return;
      pointer.tx=e.clientX/w;pointer.ty=e.clientY/h;pointer.px=e.clientX;pointer.py=e.clientY;
    };
    const onLeave=()=>{pointer.px=pointer.py=-9999;pointer.tx=pointer.ty=.5;};
    refresh.current=schedule;
    build();schedule();
    window.addEventListener('resize',onResize);
    window.addEventListener('pointermove',onPointer,{passive:true});
    window.addEventListener('scroll',schedule,{passive:true});
    document.documentElement.addEventListener('pointerleave',onLeave);
    document.addEventListener('visibilitychange',schedule);
    reduced.addEventListener('change',schedule);
    return()=>{
      cancelAnimationFrame(frame);
      window.removeEventListener('resize',onResize);window.removeEventListener('pointermove',onPointer);window.removeEventListener('scroll',schedule);
      document.documentElement.removeEventListener('pointerleave',onLeave);document.removeEventListener('visibilitychange',schedule);reduced.removeEventListener('change',schedule);
    };
  },[]);
  return <canvas ref={ref} className="sp-starfield" aria-hidden="true"/>;
}
