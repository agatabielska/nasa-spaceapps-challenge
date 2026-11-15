import {useEffect,useRef} from 'react';
import {add,makeCamera,scale,smooth,type Camera} from './journey/path';
import type {Journey} from './journey/engine';
import {sky} from './journey/sky';

type Star={x:number;y:number;z:number;r:number;phase:number;tint:string;ox:number;oy:number;sx:number;sy:number;seen:boolean};
const tints=['#ffffff','#ffffff','#d6e9ff','#a9d4ff','#ffe8c7'];
const REPEL_RADIUS=150;
const mod=(a:number,n:number)=>((a%n)+n)%n;

// Deep-space backdrop seen through the journey camera. Stars fill a volume that wraps around the camera, so
// flying forward streams them past the viewer (with streaks at speed) and panning gives depth parallax.
// The pointer nudges the camera a little and pushes nearby stars aside.
export default function Starfield({paused,journey}:{paused:boolean;journey:Journey|null}){
  const ref=useRef<HTMLCanvasElement>(null);
  const pausedRef=useRef(paused);
  const refresh=useRef<()=>void>(()=>{});
  useEffect(()=>{pausedRef.current=paused;refresh.current();},[paused]);
  useEffect(()=>{
    const canvas=ref.current,ctx=canvas?.getContext('2d');
    if(!canvas||!ctx)return;
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    let w=0,h=0,stars:Star[]=[],still:Camera|null=null,lastCamera:Camera|null=null,lastSpeed=0;
    const pointer={x:.5,y:.5,tx:.5,ty:.5,px:-9999,py:-9999};
    const animated=()=>!pausedRef.current&&!reduced.matches&&!document.hidden;
    function build(){
      const dpr=Math.min(window.devicePixelRatio||1,2);
      w=window.innerWidth;h=window.innerHeight;
      canvas!.width=Math.round(w*dpr);canvas!.height=Math.round(h*dpr);
      ctx!.setTransform(dpr,0,0,dpr,0,0);
      const count=Math.round(Math.min(1600,Math.max(500,w*h/1100)));
      stars=Array.from({length:count},()=>({x:Math.random(),y:Math.random(),z:Math.random(),r:.5+Math.random()*1.1+(Math.random()<.03?1.2:0),
        phase:Math.random()*6.283,tint:tints[Math.floor(Math.random()*tints.length)],ox:0,oy:0,sx:0,sy:0,seen:false}));
      still=makeCamera([0,0,0],[0,0,-1],0,Math.max(700,h*1.1),w,h);
    }
    function draw(camera:Camera,speed:number,time:number){
      const live=animated();
      if(live){pointer.x+=(pointer.tx-pointer.x)*.05;pointer.y+=(pointer.ty-pointer.y)*.05;}
      const f=camera.focal,boxX=w*4,boxY=h*4,boxZ=f*7;
      // Pointer parallax: shift the eye, not the scene, so near stars move more than far ones.
      const eye=live?add(camera.pos,add(scale(camera.right,(pointer.x-.5)*-f*.12),scale(camera.down,(pointer.y-.5)*-f*.12))):camera.pos;
      ctx!.clearRect(0,0,w,h);
      const streaks=live&&speed>.25;
      for(const s of stars){
        // Wrap each star into a box around the eye: an endless field without allocating new stars.
        const rx=mod(s.x*boxX-eye[0]+boxX/2,boxX)-boxX/2,ry=mod(s.y*boxY-eye[1]+boxY/2,boxY)-boxY/2,rz=mod(s.z*boxZ-eye[2],boxZ)-boxZ;
        const d=rx*camera.fwd[0]+ry*camera.fwd[1]+rz*camera.fwd[2];
        if(d<20){s.seen=false;continue;}
        const k=f/d;
        let x=w/2+(rx*camera.right[0]+ry*camera.right[1]+rz*camera.right[2])*k;
        let y=h/2+(rx*camera.down[0]+ry*camera.down[1]+rz*camera.down[2])*k;
        if(x<-80||x>w+80||y<-80||y>h+80){s.seen=false;continue;}
        // When the About camera turns around the globe, the sky sweeps the other way; nearer stars move further.
        // Visible stars wrap around the screen edges, so the density stays the same.
        const near=.35+.65*Math.min(1,k*2.2);
        x=((x+80-sky.lon*w*.16*near)%(w+160)+w+160)%(w+160)-80;y=((y+80+sky.lat*h*.12*near)%(h+160)+h+160)%(h+160)-80;
        if(live){
          const dx=x-pointer.px,dy=y-pointer.py,dist=Math.hypot(dx,dy),near=Math.min(1,k*2);
          let tx=0,ty=0;
          if(dist<REPEL_RADIUS&&dist>.01){const push=(1-dist/REPEL_RADIUS)**2*52*near;tx=dx/dist*push;ty=dy/dist*push;}
          s.ox+=(tx-s.ox)*.12;s.oy+=(ty-s.oy)*.12;x+=s.ox;y+=s.oy;
        }
        const size=Math.min(3.4,Math.max(.35,s.r*k*1.6));
        const fade=(1-smooth(boxZ*.55,boxZ*.98,d))*smooth(20,f*.25,d);
        const twinkle=live?.8+.2*Math.sin(time*.0011*(.6+k)+s.phase):.9;
        ctx!.globalAlpha=Math.min(1,(.35+.65*Math.min(1,k*2.2))*fade*twinkle);
        ctx!.fillStyle=ctx!.strokeStyle=s.tint;
        const mx=x-s.sx,my=y-s.sy,moved=Math.hypot(mx,my);
        if(streaks&&s.seen&&moved>1.2&&moved<220){
          // Streak back along the star's own screen motion: radial when flying forward, vertical when panning.
          const len=Math.min(2.2,.7+speed*.7);
          ctx!.lineWidth=size;ctx!.beginPath();ctx!.moveTo(x,y);ctx!.lineTo(x-mx*len,y-my*len);ctx!.stroke();
        }else if(size<1.2)ctx!.fillRect(x,y,size*1.35,size*1.35);
        else{
          ctx!.beginPath();ctx!.arc(x,y,size*.8,0,6.283);ctx!.fill();
          if(size>2.2){ctx!.globalAlpha*=.22;ctx!.beginPath();ctx!.arc(x,y,size*2.6,0,6.283);ctx!.fill();}
        }
        s.sx=x;s.sy=y;s.seen=true;
      }
      ctx!.globalAlpha=1;
    }
    let frame=0;
    // Without the journey engine (reduced motion) the field is a still picture.
    const drawStill=()=>{frame=0;if(still)draw(still,0,performance.now());if(!journey&&animated())frame=requestAnimationFrame(drawStill);};
    const onResize=()=>{build();if(journey&&lastCamera)draw(lastCamera,0,performance.now());else drawStill();};
    const onPointer=(e:PointerEvent)=>{if(e.pointerType==='touch')return;pointer.tx=e.clientX/w;pointer.ty=e.clientY/h;pointer.px=e.clientX;pointer.py=e.clientY;};
    const onLeave=()=>{pointer.px=pointer.py=-9999;pointer.tx=pointer.ty=.5;};
    build();
    const off=journey?.subscribe(next=>{
      // Redraw while moving or animating; a still camera with paused motion needs no new frame.
      if(!next.moved&&!animated()&&lastSpeed<.01)return;
      lastCamera=next.camera;lastSpeed=next.speed;draw(next.camera,next.speed,next.time);
    });
    refresh.current=()=>{if(journey&&lastCamera)draw(lastCamera,0,performance.now());else if(!frame)drawStill();};
    if(!journey)drawStill();
    window.addEventListener('resize',onResize);
    window.addEventListener('pointermove',onPointer,{passive:true});
    document.documentElement.addEventListener('pointerleave',onLeave);
    return()=>{
      off?.();cancelAnimationFrame(frame);refresh.current=()=>{};
      window.removeEventListener('resize',onResize);window.removeEventListener('pointermove',onPointer);
      document.documentElement.removeEventListener('pointerleave',onLeave);
    };
  },[journey]);
  return <canvas ref={ref} className="sp-starfield" aria-hidden="true"/>;
}
