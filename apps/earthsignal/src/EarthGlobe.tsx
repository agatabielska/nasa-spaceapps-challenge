import {useEffect,useRef,useState,type MutableRefObject} from 'react';
import './earth-globe.css';

// NASA Blue Marble is a photographic background, not a NISAR data layer. The shader repaints it as an
// illustration in the landing page's deep blues and sea greens, with faint drifting clouds.
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
  uniform float u_tilt;
  uniform float u_time;
  // Dims the globe while it waits behind the hero title (1 = full colour).
  uniform float u_tone;
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
      float glow=exp(-(radius-1.0)*34.0)*0.5;
      float lit=mix(0.35,1.0,clamp(dot(normalize(vec3(p,0.12)),light)*0.5+0.5,0.0,1.0));
      // Premultiplied colour: where the halo fades out the pixel is truly empty. Safari shows the colour of
      // nearly transparent unpremultiplied pixels, which painted the canvas square solid cyan.
      float a=glow*lit;
      gl_FragColor=vec4(vec3(0.42,0.76,1.0)*mix(0.78,1.0,u_tone)*a,a);
      return;
    }
    vec3 normal=vec3(p,sqrt(max(0.0,1.0-dot(p,p))));
    float tilt=u_tilt;
    vec3 world=vec3(normal.x,normal.y*cos(tilt)+normal.z*sin(tilt),-normal.y*sin(tilt)+normal.z*cos(tilt));
    float longitude=atan(world.x,world.z)+u_rotation;
    float latitude=asin(clamp(world.y,-1.0,1.0));
    vec2 uv=vec2(fract(0.5+longitude/(2.0*PI)),0.5+latitude/PI);
    vec3 c=texture2D(u_earth,uv).rgb;
    float lum=dot(c,vec3(0.299,0.587,0.114));

    // Illustrated palette in the page's colours: deep teal-blue oceans (lighter near the coast), muted sea-green
    // land with sandy deserts and pale ice, and a darker outline along the coasts.
    float w=water(uv),near=around(uv,2.5),far=around(uv,8.0);
    vec3 ocean=world.y>0.0?mix(vec3(0.04,0.29,0.45),vec3(0.08,0.20,0.31),smoothstep(0.1,0.85,world.y))
                          :mix(vec3(0.04,0.29,0.45),vec3(0.024,0.12,0.24),smoothstep(0.1,0.85,-world.y));
    ocean=mix(ocean,vec3(0.10,0.42,0.58),w*(1.0-far)*0.7);
    float desert=smoothstep(0.06,0.2,c.r-c.b)*smoothstep(0.22,0.4,lum);
    vec3 land=mix(vec3(0.13,0.34,0.30),vec3(0.22,0.48,0.42),smoothstep(0.02,0.13,lum));
    land=mix(land,vec3(0.55,0.58,0.44),desert*0.8);
    land=mix(land,vec3(0.74,0.85,0.90),smoothstep(0.55,0.78,lum));
    vec3 base=mix(land,ocean,w);
    float coast=(1.0-w)*smoothstep(0.12,0.55,near);
    base=mix(base,vec3(0.10,0.27,0.27),coast*0.75);

    // Faint clouds drifting a little faster than the ground.
    float drift=longitude+u_time*0.02;
    vec3 q=vec3(sin(drift)*cos(latitude),sin(latitude),cos(drift)*cos(latitude));
    float cloud=smoothstep(0.62,0.82,fbm(q*3.2+vec3(0.0,0.0,u_time*0.01)));

    // Lighting as in an illustration: a cool highlight on the lit side, a deep blue shadow on the far side.
    float facing=dot(normal,light);
    float shade=0.16+0.8*smoothstep(-0.25,0.75,facing);
    vec3 surface=base*shade+vec3(0.52,0.86,0.95)*0.10*smoothstep(0.55,1.0,facing);
    surface=mix(surface,vec3(0.88,0.96,1.0)*shade,cloud*0.22);
    surface=mix(surface,vec3(0.0,0.03,0.1),smoothstep(0.15,-0.45,facing)*0.55);
    float rim=pow(1.0-normal.z,3.0);
    surface+=vec3(0.33,0.70,1.0)*rim*(0.25+max(0.0,facing))*0.5;
    float edge=1.0-smoothstep(0.996,1.0,radius);
    surface*=mix(0.78,1.0,u_tone);
    surface=mix(vec3(dot(surface,vec3(0.299,0.587,0.114))),surface,mix(0.85,1.0,u_tone));
    gl_FragColor=vec4(surface*edge,edge);
  }
`;

// The longitude and latitude (radians) at the centre of the disc. Pass a view to steer the globe from outside
// (the camera then decides where it looks); without one it turns slowly on its own, tilted 0.29 rad.
export type GlobeView={lon:number;lat:number};
export default function EarthGlobe({paused=false,view}:{paused?:boolean;view?:MutableRefObject<GlobeView>}){
  const canvas=useRef<HTMLCanvasElement>(null);
  const pausedRef=useRef(paused);
  const refresh=useRef<()=>void>(()=>{});
  const [ready,setReady]=useState(false);
  useEffect(()=>{pausedRef.current=paused;refresh.current();},[paused]);
  useEffect(()=>{
    const element=canvas.current;if(!element)return;
    const gl=element.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:true,powerPreference:'low-power'});
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
    const rotationUniform=gl.getUniformLocation(program,'u_rotation'),tiltUniform=gl.getUniformLocation(program,'u_tilt'),timeUniform=gl.getUniformLocation(program,'u_time'),toneUniform=gl.getUniformLocation(program,'u_tone');
    // The landing page's About scene sets --arrive on its layer: the globe is dimmer until the camera arrives.
    const scene=element.closest<HTMLElement>('[data-scene]');
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
      const arrive=parseFloat(scene?.style.getPropertyValue('--arrive')||'1');gl.uniform1f(toneUniform,Number.isFinite(arrive)?arrive:1);
      gl.uniform1f(rotationUniform,view?view.current.lon:rotation);gl.uniform1f(tiltUniform,view?view.current.lat:0.29);gl.drawArrays(gl.TRIANGLES,0,6);
      // A steered globe keeps drawing while visible, because the camera can move even when motion is paused.
      if(view||(!pausedRef.current&&!reduced.matches))frame=requestAnimationFrame(draw);
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
