import {useEffect,useRef,useState} from 'react';
import './earth-globe.css';

// NASA Blue Marble is a photographic background, not a NISAR data layer.
// A single screen-space sphere keeps this decorative scene independent of the map engine.
const vertexSource=`
  attribute vec2 a_position;
  varying vec2 v_position;
  void main(){v_position=a_position;gl_Position=vec4(a_position,0.0,1.0);}
`;
const fragmentSource=`
  precision highp float;
  varying vec2 v_position;
  uniform sampler2D u_earth;
  uniform float u_rotation;
  uniform float u_scan;
  const float PI=3.14159265359;
  void main(){
    vec2 p=v_position/0.91;
    float radius=length(p);
    vec3 light=normalize(vec3(-0.65,0.45,0.95));
    if(radius>1.0){
      // Atmosphere: a soft cyan halo, brightest on the sunlit side.
      float glow=exp(-(radius-1.0)*30.0)*0.6;
      float lit=mix(0.45,1.0,clamp(dot(normalize(vec3(p,0.12)),light)*0.5+0.5,0.0,1.0));
      gl_FragColor=vec4(vec3(0.42,0.78,1.0),glow*lit);
      return;
    }
    vec3 normal=vec3(p,sqrt(max(0.0,1.0-dot(p,p))));
    float tilt=0.29;
    vec3 world=vec3(normal.x,normal.y*cos(tilt)+normal.z*sin(tilt),-normal.y*sin(tilt)+normal.z*cos(tilt));
    float longitude=atan(world.x,world.z)+u_rotation;
    vec2 uv=vec2(fract(0.5+longitude/(2.0*PI)),0.5+asin(clamp(world.y,-1.0,1.0))/PI);
    vec3 photograph=texture2D(u_earth,uv).rgb;
    float diffuse=max(0.0,dot(normal,light));
    // Brighter than a photo-real night side, so the planet reads on a projector: a generous ambient term,
    // a little extra saturation and a strong cyan atmosphere rim.
    vec3 surface=photograph*(0.32+diffuse*1.0);
    surface=mix(vec3(dot(surface,vec3(0.299,0.587,0.114))),surface,1.18);
    float rim=pow(1.0-normal.z,3.0);
    surface+=vec3(0.33,0.72,1.0)*rim*(0.3+diffuse)*0.7;
    // Radar swath: a thin bright line sweeps across the disc, leaving a faint lit strip behind it.
    float d=p.x-u_scan;
    surface+=vec3(0.55,0.9,1.0)*(exp(-d*d/0.0005)*0.55+(d<0.0?exp(d/0.22)*0.07:0.0))*normal.z;
    float edge=1.0-smoothstep(0.996,1.0,radius);
    gl_FragColor=vec4(surface,edge);
  }
`;

export default function EarthGlobe({paused=false}:{paused?:boolean}){
  const canvas=useRef<HTMLCanvasElement>(null);
  const pausedRef=useRef(paused);
  const refresh=useRef<()=>void>(()=>{});
  const [ready,setReady]=useState(false);
  useEffect(()=>{pausedRef.current=paused;refresh.current();},[paused]);
  useEffect(()=>{
    const element=canvas.current;if(!element)return;
    const gl=element.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'});
    if(!gl)return;
    let disposed=false,frame=0,loaded=false,visible=true,lastTime=0,rotation=0.32;
    const shaders:WebGLShader[]=[];
    let program:WebGLProgram|null=null,buffer:WebGLBuffer|null=null,texture:WebGLTexture|null=null;
    const compile=(type:number,source:string)=>{
      const shader=gl.createShader(type);if(!shader)throw new Error('Shader unavailable');
      shaders.push(shader);gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error('Shader compilation unavailable');
      return shader;
    };
    const release=()=>{shaders.forEach(shader=>gl.deleteShader(shader));if(program)gl.deleteProgram(program);if(buffer)gl.deleteBuffer(buffer);if(texture)gl.deleteTexture(texture);};
    try{
      program=gl.createProgram();if(!program)throw new Error('Renderer unavailable');
      gl.attachShader(program,compile(gl.VERTEX_SHADER,vertexSource));
      gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragmentSource));gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Renderer unavailable');
      gl.useProgram(program);
      buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
      const position=gl.getAttribLocation(program,'a_position');
      gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
      texture=gl.createTexture();gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.uniform1i(gl.getUniformLocation(program,'u_earth'),0);
    }catch{release();return;}
    const rotationUniform=gl.getUniformLocation(program,'u_rotation'),scanUniform=gl.getUniformLocation(program,'u_scan');
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    const draw=(time:number)=>{
      frame=0;if(disposed||!loaded||!visible||document.hidden)return;
      const moving=!pausedRef.current&&!reduced.matches;
      // About one turn a minute: alive, but calm enough to read the chips around it.
      if(lastTime&&moving)rotation+=Math.min(time-lastTime,50)*0.00011;
      lastTime=time;
      gl.viewport(0,0,element.width,element.height);
      // The swath crosses the disc every 7 s and is hidden while motion is paused.
      gl.uniform1f(scanUniform,moving?((time/7000)%1)*2.6-1.3:-9.0);
      gl.uniform1f(rotationUniform,rotation);gl.drawArrays(gl.TRIANGLES,0,6);
      if(!pausedRef.current&&!reduced.matches)frame=requestAnimationFrame(draw);
    };
    const schedule=()=>{cancelAnimationFrame(frame);frame=0;lastTime=0;if(!disposed)draw(performance.now());};
    refresh.current=schedule;
    const resize=new ResizeObserver(()=>{
      const size=Math.max(1,Math.round(element.clientWidth*Math.min(window.devicePixelRatio||1,1.75)));
      if(element.width!==size||element.height!==size){element.width=size;element.height=size;schedule();}
    });resize.observe(element);
    const intersection=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;schedule();},{rootMargin:'40px'});
    intersection.observe(element);
    const img=new Image();
    img.onload=()=>{
      if(disposed)return;
      gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,img);
      loaded=true;setReady(true);schedule();
    };
    img.src='/media/earth-blue-marble.jpg';
    const lost=(event:Event)=>{event.preventDefault();loaded=false;setReady(false);cancelAnimationFrame(frame);};
    element.addEventListener('webglcontextlost',lost);
    reduced.addEventListener('change',schedule);document.addEventListener('visibilitychange',schedule);
    return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();intersection.disconnect();reduced.removeEventListener('change',schedule);document.removeEventListener('visibilitychange',schedule);element.removeEventListener('webglcontextlost',lost);img.onload=null;refresh.current=()=>{};release();};
  },[]);
  return <div className={'earth-globe'+(ready?' earth-globe-ready':'')} aria-hidden="true"><div className="earth-globe-fallback"/><canvas ref={canvas}/></div>;
}
