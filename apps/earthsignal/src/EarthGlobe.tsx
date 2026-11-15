import {useEffect,useRef,useState} from 'react';
import './earth-globe.css';

// NASA Blue Marble is a photographic background, not a NISAR data layer. It is redrawn in a flat, cartoon-like
// palette (bright water, flat land, outlined coasts, drifting clouds) to match the illustrated landing page.
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
  uniform float u_time;
  const float PI=3.14159265359;
  const vec2 TEXEL=vec2(1.0/2048.0,1.0/1024.0);
  // Blue Marble oceans are near-black navy: water = blue clearly above red and green, and dark.
  float water(vec2 uv){
    vec3 c=texture2D(u_earth,uv).rgb;
    float lum=dot(c,vec3(0.299,0.587,0.114));
    return smoothstep(0.012,0.04,c.b-max(c.r,c.g))*(1.0-smoothstep(0.1,0.2,lum));
  }
  float around(vec2 uv,float r){
    float s=0.0;
    for(int k=0;k<8;k++){float a=float(k)*0.785398;s+=water(uv+vec2(cos(a),sin(a))*TEXEL*r);}
    return s/8.0;
  }
  float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
  float noise(vec3 p){
    vec3 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
    return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
               mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);
  }
  float fbm(vec3 p){float v=0.0,a=0.5;for(int k=0;k<4;k++){v+=a*noise(p);p*=2.07;a*=0.5;}return v;}
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
    float latitude=asin(clamp(world.y,-1.0,1.0));
    vec2 uv=vec2(fract(0.5+longitude/(2.0*PI)),0.5+latitude/PI);
    vec3 c=texture2D(u_earth,uv).rgb;
    float lum=dot(c,vec3(0.299,0.587,0.114));

    // Cartoon palette: flat bright oceans with lighter shallows, flat greens and sand, white ice,
    // and a dark outline along the coasts.
    float w=water(uv),near=around(uv,2.5),far=around(uv,9.0);
    float lat=abs(world.y);
    vec3 ocean=mix(vec3(0.11,0.55,0.80),vec3(0.07,0.38,0.62),smoothstep(0.25,0.9,lat));
    ocean=mix(ocean,vec3(0.38,0.80,0.93),w*(1.0-far)*0.8);
    // Gentle animated ripples on the water (periodic in longitude, so there is no seam).
    float ripple=sin(uv.x*2.0*PI*48.0+uv.y*90.0+u_time*1.4)*sin(uv.y*170.0-u_time*0.9);
    ocean+=vec3(0.07,0.12,0.14)*smoothstep(0.82,0.97,ripple)*(1.0-lat);
    float desert=smoothstep(0.06,0.2,c.r-c.b)*smoothstep(0.22,0.4,lum);
    vec3 land=mix(vec3(0.17,0.45,0.37),vec3(0.30,0.66,0.44),smoothstep(0.02,0.14,lum));
    land=mix(land,vec3(0.86,0.74,0.48),desert);
    land=mix(land,vec3(0.93,0.97,1.0),smoothstep(0.55,0.75,lum));
    vec3 base=mix(land,ocean,w);
    float coast=(1.0-w)*smoothstep(0.12,0.55,near);
    base=mix(base,vec3(0.05,0.18,0.24),coast*0.7);

    // Soft clouds drifting a little faster than the ground.
    float drift=longitude+u_time*0.02;
    vec3 q=vec3(sin(drift)*cos(latitude),sin(latitude),cos(drift)*cos(latitude));
    float cloud=smoothstep(0.6,0.8,fbm(q*3.2+vec3(0.0,0.0,u_time*0.01)));

    // Toon lighting: bright day side, a soft stepped terminator, a lifted night side.
    float diffuse=max(0.0,dot(normal,light));
    float toon=0.5+0.4*smoothstep(0.0,0.3,diffuse)+0.12*smoothstep(0.55,0.7,diffuse);
    vec3 surface=base*toon;
    surface=mix(surface,vec3(0.96,0.98,1.0)*(0.65+0.35*toon),cloud*0.6);
    float rim=pow(1.0-normal.z,3.0);
    surface+=vec3(0.33,0.72,1.0)*rim*(0.3+diffuse)*0.6;
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
    const rotationUniform=gl.getUniformLocation(program,'u_rotation'),timeUniform=gl.getUniformLocation(program,'u_time');
    let clock=0;
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    const draw=(time:number)=>{
      frame=0;if(disposed||!loaded||!visible||document.hidden)return;
      const moving=!pausedRef.current&&!reduced.matches;
      // About one turn a minute: alive, but calm enough to read the chips around it.
      if(lastTime&&moving){rotation+=Math.min(time-lastTime,50)*0.00011;clock+=Math.min(time-lastTime,50)/1000;}
      lastTime=time;
      gl.viewport(0,0,element.width,element.height);
      gl.uniform1f(timeUniform,clock);
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
