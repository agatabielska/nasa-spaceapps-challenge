import {test} from 'node:test';import assert from 'node:assert/strict';
import {holdProgress,journeyStops,layoutJourney,makeCamera,nextStop,prevStop,project,sceneAtScroll,shotAt,sub,type Layout} from './journey/path.ts';

const sizes=[{id:'home',height:900,hold:270},{id:'about',height:1500,hold:270},{id:'flight',height:900,hold:3240},{id:'end',height:1100,hold:270}];
const layout=layoutJourney(sizes,1440,900);
const view=(l:Layout,s:number)=>{const shot=shotAt(l,s);return makeCamera(shot.pos,shot.fwd,shot.roll,l.focal,l.w,l.h);};

test('a scene at rest is drawn at scale 1 with its top at the top of the viewport',()=>{
  for(const sc of layout.scenes){
    const p=project(view(layout,sc.start),sc.anchor)!;
    assert.ok(Math.abs(p.s-1)<1e-9);assert.ok(Math.abs(p.x-720)<1e-6);assert.ok(Math.abs(p.y)<1e-6);
  }
});
test('holding on a tall scene pans down like ordinary scrolling',()=>{
  const about=layout.scenes[1];assert.equal(about.pan,600);
  const p=project(view(layout,about.start+250),about.anchor)!;
  assert.ok(Math.abs(p.y+250)<1e-6);assert.ok(Math.abs(p.s-1)<1e-9);
});
test('the camera path is continuous and the scroll length adds up',()=>{
  assert.equal(layout.total,layout.scenes.at(-1)!.end);
  for(let s=0;s<layout.total;s+=7){
    const a=shotAt(layout,s).pos,b=shotAt(layout,s+1).pos,step=Math.hypot(...sub(b,a));
    assert.ok(step<layout.gap/layout.travel*3,`jump at ${s}: ${step}`);
  }
});
test('scenes ahead start small and grow, scenes passed fall behind the camera',()=>{
  const next=layout.scenes[1],from=layout.scenes[0].end;
  const far=project(view(layout,from+layout.travel*.3),next.anchor),near=project(view(layout,from+layout.travel*.8),next.anchor);
  assert.ok(far&&near&&far.s<near.s&&near.s<1);
  assert.equal(project(view(layout,next.start),layout.scenes[0].anchor),null);
});
test('chapter switches halfway through a flight and hold progress drives the flight scene',()=>{
  const flight=layout.scenes[2];
  assert.equal(shotAt(layout,flight.start-layout.travel*.6).chapter,1);
  assert.equal(shotAt(layout,flight.start-layout.travel*.4).chapter,2);
  assert.equal(holdProgress(flight,flight.start-1),0);assert.equal(holdProgress(flight,flight.start+flight.hold/2),.5);assert.equal(holdProgress(flight,flight.end+5),1);
});
test('stops cover scene starts, pan steps and the playing scene, and step both ways',()=>{
  const stops=journeyStops(layout,[undefined,undefined,[1/3,2/3,1],undefined]),[home,about,flight,end]=layout.scenes;
  assert.deepEqual(stops,[home.start,about.start,about.start+600,flight.start,flight.start+flight.hold/3,flight.start+flight.hold*2/3,flight.end,end.start,end.start+200,end.end]);
  assert.equal(stops.at(-1),layout.total);
  assert.equal(nextStop(stops,home.start),about.start);
  assert.equal(nextStop(stops,about.start+100),about.start+600);
  assert.equal(nextStop(stops,end.start+200),end.end);assert.equal(nextStop(stops,end.end),end.end);
  assert.equal(prevStop(stops,flight.start+10),flight.start);
  assert.equal(prevStop(stops,flight.start-300),about.start+600);
  assert.equal(prevStop(stops,0),0);
  assert.equal(sceneAtScroll(layout,flight.start-300),1);assert.equal(sceneAtScroll(layout,flight.start),2);
});
