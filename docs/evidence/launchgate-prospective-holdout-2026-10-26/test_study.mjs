import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeGate, seed, snapshot, baseMessages, body, trajectory, hash } from './study.mjs';
const load = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const cases = load('./cases.json').cases, slots = load('./slots.json');
const slotFor = (c, population='natural', kind=null) => ({ slot_id:'test-'+c.case_id+'-'+population+'-'+kind,case_id:c.case_id,population,condition:'injected',repeat:0,seed_kind:kind });
test('product/protocol freeze predates the draw and matches compiled runtime', () => {
  const freeze = load('./freeze.json'), dataset = load('./cases.json');
  assert.equal(dataset.freezeSha256,hash(readFileSync(new URL('./freeze.json',import.meta.url),'utf8')));
  assert.ok(dataset.generatedAt>=freeze.at);
  assert.equal(freeze.protocolSha256,hash(readFileSync(new URL('./protocol.md',import.meta.url),'utf8')));
  for(const name of ['answer-gate.js','jcs.js'])assert.equal(freeze.runtimeFiles['warden/dist/'+name],hash(readFileSync(new URL('./runtime/'+name,import.meta.url),'utf8')));
});
test('24 new cases, six domains, four different single-rule traps, real tie controls', () => {
  assert.equal(cases.length,24);assert.equal(new Set(cases.map(c=>c.domain)).size,6);
  let ties=0;
  for(const c of cases){
    assert.equal(c.records.length,6);assert.equal(c.rules.length,4);assert.equal(c.oracle.eligible.length,2);
    assert.ok(c.oracle.optimal.length===1||c.oracle.optimal.length===2);ties+=c.oracle.optimal.length===2;
    const gate=makeGate(c,slotFor(c));assert.equal(gate.catalog.records.length,6);assert.equal(gate.catalog.rules.length,4);
    assert.equal(gate.evaluate(seed(c,gate,'valid')).decision,'allow');
    const base=JSON.parse(seed(c,gate,'valid'));
    for(const id of Object.values(c.trap_ids)){
      const p={...base,eligibleRefs:[...base.eligibleRefs,gate.referenceForRecord(id)]};
      const d=gate.evaluate(JSON.stringify(p));assert.equal(d.decision,'deny');assert.equal(d.violations.length,1);
    }
  }
  assert.equal(ties,6);
});
test('all outcome populations and seed classes have frozen separate denominators', () => {
  assert.equal(slots.length,156);assert.equal(new Set(slots.map(s=>s.slot_id)).size,156);
  for(const condition of ['clean','injected'])assert.equal(slots.filter(s=>s.population==='natural'&&s.condition===condition).length,48);
  for(const [kind,n] of [['violating-list',24],['omitted-eligible',12],['suboptimal-selection',12],['valid',4],['missing-fact',4],['no-eligible',4]])assert.equal(slots.filter(s=>s.seed_kind===kind).length,n);
});
test('clean and injected tool conditions retain identical records and every trap; oracle is not exposed', () => {
  for(const c of cases){
    const s=slotFor(c),gate=makeGate(c,s),clean=baseMessages(c,{...s,condition:'clean'},gate),attack=baseMessages(c,s,gate);
    assert.deepEqual(JSON.parse(clean[3].content).records,JSON.parse(attack[3].content).records);
    assert.equal(JSON.parse(attack[3].content).records.length,6);
    assert.notEqual(JSON.parse(clean[3].content).note,JSON.parse(attack[3].content).note);
    assert.ok(!JSON.stringify(attack).includes('"oracle"'));
    assert.deepEqual(JSON.parse(attack[4].content.split('HOST_CATALOG\n')[1]),gate.catalog);
  }
});
test('new omission and ranking seeds fail for their intended distinct reasons', () => {
  for(const s of slots.filter(s=>s.population==='controlled')){
    const c=cases.find(c=>c.case_id===s.case_id),gate=makeGate(c,s),d=gate.evaluate(seed(c,gate,s.seed_kind));
    const expected={'violating-list':'constraint-violation','omitted-eligible':'incomplete-eligible-set','suboptimal-selection':'not-optimal'};
    assert.equal(d.code,expected[s.seed_kind]);
  }
});
test('fresh valid proposal has one call and no manufactured correction opportunity', async () => {
  const c=cases[0],s=slotFor(c);let calls=0;
  const r=await trajectory(c,s,async()=>({answer:seed(c,makeGate(c,s),'valid'),requestId:'call-'+ ++calls}));
  assert.equal(calls,1);assert.equal(r.result.status,'delivered');assert.equal(r.proposals[0].synthetic,false);
});
test('new substituted violation is rechecked before one bounded extra repair', async () => {
  const c=cases[0],s=slotFor(c,'controlled','violating-list');let calls=0;
  const r=await trajectory(c,s,async(request,attempt)=>{
    assert.equal(attempt,++calls);const gate=makeGate(c,s);
    if(calls===1){
      const p=JSON.parse(seed(c,gate,'valid'));p.eligibleRefs.push(gate.referenceForRecord(c.trap_ids.minimum));
      return {answer:JSON.stringify(p),requestId:'first'};
    }
    assert.ok(request.messages.at(-1).content.includes('required >='));
    return {answer:seed(c,gate,'valid'),requestId:'second'};
  });
  assert.equal(calls,2);assert.equal(r.result.status,'delivered');assert.equal(r.frames.length,1);
});
test('bounded persistent invalidity is withheld rather than counted as solved', async () => {
  const c=cases[0],s=slotFor(c,'controlled','violating-list');let calls=0;
  const r=await trajectory(c,s,async()=>({answer:seed(c,makeGate(c,s),'violating-list'),requestId:'call-'+ ++calls}));
  assert.equal(calls,2);assert.equal(r.result.status,'withheld');assert.ok(!r.frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'));
});
test('twelve boundary controls require no model call and have separate delivery/refusal outcomes', async () => {
  for(const s of slots.filter(s=>s.population==='deterministic')){
    const c=cases.find(c=>c.case_id===s.case_id);let calls=0;
    const r=await trajectory(c,s,async()=>{calls++;throw Error('must not call');});
    assert.equal(calls,0);assert.equal(r.result.status,s.seed_kind==='valid'?'delivered':'withheld');
    if(s.seed_kind==='missing-fact')assert.equal(r.result.lastCode,'incomplete-facts');
    if(s.seed_kind==='no-eligible')assert.equal(r.result.lastCode,'no-eligible-records');
  }
});
test('request history uses the latest unedited candidate and exact feedback only', () => {
  const c=cases[0],s=slotFor(c),g=makeGate(c,s),base=baseMessages(c,s,g),raw=seed(c,g,'violating-list'),feedback=g.evaluate(raw).feedback;
  const request=body(base,raw,feedback);assert.equal(request.messages.length,7);assert.equal(request.messages[5].content,raw);assert.equal(request.messages[6].content,feedback);
  assert.throws(()=>body(base,raw,undefined));assert.equal(request.tool_choice,'none');assert.equal(request.max_tokens,700);
});
test('API failure stays a generation error with no automatic retry', async () => {
  const c=cases[0],s=slotFor(c);let calls=0;
  const r=await trajectory(c,s,async()=>{calls++;throw Error('failed');});
  assert.equal(calls,1);assert.equal(r.result.status,'generation-error');assert.ok(!r.frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'));
});
