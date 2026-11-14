import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {inBounds,filterEvents,lonSpan,type EventRecord} from './domain.ts';
const events:EventRecord[]=JSON.parse(readFileSync(new URL('../data/events.seed.json',import.meta.url),'utf8'));
test('viewport handles antimeridian and repeated worlds',()=>{assert.ok(inBounds([179,0],[170,-10,190,10]));assert.ok(inBounds([-179,0],[170,-10,190,10]));assert.ok(!inBounds([0,0],[170,-10,190,10]));assert.ok(inBounds([0,0],[-200,-10,200,10]));});
test('filter does not imply analysis availability',()=>{const found=filterEvents(events,'Spain',['wildfire'],'2025-01-01','2026-12-31',false,null);assert.equal(found.length,1);assert.equal(found[0].analysisAvailable,false);assert.equal(filterEvents(events,'Spain',['wildfire'],'2025-01-01','2026-12-31',true,null).length,0);});
test('search matches descriptions and multiple words in any order',()=>{
  const ids=(q:string)=>filterEvents(events,q,['flood','wildfire','volcano','earthquake','ice'],'2025-01-01','2026-12-31',false,null).map(e=>e.id);
  assert.deepEqual(ids('fire spain'),['spain']);assert.deepEqual(ids('spain fire'),['spain']);
  assert.ok(ids('radar').includes('etna'));assert.deepEqual(ids('hiszpania  mozambik'),[]);assert.equal(ids('   ').length,events.length);
});
test('longitude span takes the shorter way across the antimeridian',()=>{
  assert.deepEqual(lonSpan([170,-170]),[170,190]);assert.deepEqual(lonSpan([-10,20,5]),[-10,20]);assert.deepEqual(lonSpan([30]),[30,30]);assert.equal(lonSpan([]),null);
  const [w,e]=lonSpan(events.map(x=>x.coordinates[0]))!;assert.ok(e-w<300&&e-w>0);for(const x of events){const l=x.coordinates[0];assert.ok((l>=w&&l<=e)||(l+360>=w&&l+360<=e));}
});
