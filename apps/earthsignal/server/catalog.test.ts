import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Catalog,readSeed} from './catalog.ts';
import {eventSchema,searchSchema} from './contracts.ts';

test('persistent database seeds once and preserves edits across restart',()=>{
  const dir=mkdtempSync(join(tmpdir(),'earthsignal-test-')),path=join(dir,'events.sqlite');
  let c=new Catalog(path,readSeed());
  try{assert.equal(c.search().total,15);const event=c.get('spain')!;event.title='Updated local record';c.import([event]);c.close();c=new Catalog(path,readSeed());assert.equal(c.get('spain')?.title,'Updated local record');assert.equal(c.search().total,15);}finally{c.close();rmSync(dir,{recursive:true});}
});
test('SQL filters, full text, missing results and analysis availability',()=>{
  const c=new Catalog(':memory:',readSeed());try{
    assert.deepEqual(c.search({kinds:['wildfire'],countries:['ES']}).events.map(e=>e.id),['spain']);
    assert.equal(c.search({region:'Africa',kinds:['flood']}).events[0].id,'mozambique');
    assert.equal(c.search({countries:['FR']}).total,0);
    assert.equal(c.search({analysisAvailable:true}).total,4);
    assert.equal(c.search({q:'Limpopo'}).events[0].id,'mozambique');
    assert.equal(c.search({q:'" OR 1=1; DROP TABLE events; --'}).total,0);
    assert.equal(c.search().total,15);
    assert.equal(c.search({from:'2026-08-01',to:'2026-08-31'}).total,3);
    assert.equal(c.search({kinds:[]}).total,0);
  }finally{c.close();}
});
test('invalid import is atomic and duplicate IDs fail',()=>{
  const c=new Catalog(':memory:',readSeed());try{const event=c.get('spain')!;assert.throws(()=>c.import([event,{...event,id:'new',coordinates:[900,10]}]));assert.equal(c.search().total,15);assert.throws(()=>c.import([event,event]));}finally{c.close();}
});
test('event and query validation rejects invalid dates and unsupported fields',()=>{
  assert.equal(searchSchema.safeParse({from:'2026-02-30'}).success,false);
  assert.equal(searchSchema.safeParse({from:'2026-10-01',to:'2026-01-01'}).success,false);
  assert.equal(searchSchema.safeParse({sql:'DELETE FROM events'}).success,false);
  assert.equal(eventSchema.safeParse({...readSeed()[0],source:'javascript:alert(1)'}).success,false);
});
