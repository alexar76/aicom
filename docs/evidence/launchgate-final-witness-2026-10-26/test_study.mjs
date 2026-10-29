import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gates,inputAnswer,requestFor,trajectory,hash } from './study.mjs';
const load=n=>JSON.parse(readFileSync(new URL(n,import.meta.url),'utf8'));
const cohort=load('./cohort.json').contexts,slots=load('./slots.json');
test('all five held contexts and fixed distinct failure/control populations',()=>{
 assert.equal(cohort.length,5);assert.equal(cohort.filter(c=>c.origin==='natural').length,2);assert.equal(new Set(cohort.map(c=>c.case.case_id)).size,4);
 assert.equal(slots.length,120);assert.equal(new Set(slots.map(s=>s.slot_id)).size,120);
 for(const arm of ['old','witness']){
  assert.equal(slots.filter(s=>s.arm===arm&&s.population==='failure').length,40);
  assert.equal(slots.filter(s=>s.arm===arm&&s.population==='valid-control').length,20);
 }
});
test('both frozen runtimes reproduce catalog and prior verdict; witness carries numerical comparison',()=>{
 for(const c of cohort){
  const pair=gates(c);assert.deepEqual(pair.old.catalog,pair.witness.catalog);assert.deepEqual(pair.old.catalog,c.catalog);
  assert.equal(pair.old.evaluate(c.invalid_answer).feedback,c.old_invalid_feedback);
  assert.equal(pair.old.evaluate(c.invalid_answer).code,'not-optimal');assert.equal(pair.witness.evaluate(c.invalid_answer).code,'not-optimal');
  assert.match(pair.witness.evaluate(c.invalid_answer).feedback,/Ranking (min|max).*selected rec-.*optimal value is/);
 }
});
test('matched failure requests differ only in the final feedback message',()=>{
 for(const c of cohort){
  const s={context_id:c.context_id,population:'failure',arm:'old'},a=requestFor(c,s),b=requestFor(c,{...s,arm:'witness'});
  assert.equal(a.input,b.input);assert.notEqual(a.feedback,b.feedback);
  assert.deepEqual(a.body.messages.slice(0,-1),b.body.messages.slice(0,-1));
  assert.deepEqual(a.body.messages.slice(0,-2),c.prior_body.messages);
  assert.equal(a.body.messages.at(-2).content,c.invalid_answer);
 }
});
test('positive controls have identical requests and are explicitly constructed valid answers',()=>{
 for(const c of cohort){
  const s={population:'valid-control',arm:'old'},a=requestFor(c,s),b=requestFor(c,{...s,arm:'witness'});
  assert.deepEqual(a.body,b.body);assert.equal(gates(c).witness.evaluate(a.input).decision,'allow');
 }
});
test('one fresh research continuation emits valid result with notice',async()=>{
 const c=cohort[0],slot=slots.find(s=>s.context_id===c.context_id);let calls=0;
 const r=await trajectory(c,slot,async(_body,attempt,signal)=>{calls++;assert.equal(attempt,0);assert.equal(signal.aborted,false);return {answer:inputAnswer(c,{population:'valid-control'},gates(c).witness),requestId:'test'};});
 assert.equal(calls,1);assert.equal(r.result.status,'delivered');assert.equal(r.frames.length,1);assert.ok(r.frames[0].startsWith('WARDEN:'));
});
test('failed fresh continuation withholds without adding another production repair',async()=>{
 const c=cohort[0],slot=slots.find(s=>s.context_id===c.context_id);let calls=0;
 const r=await trajectory(c,slot,async()=>({answer:c.invalid_answer,requestId:'test-'+ ++calls}));
 assert.equal(calls,1);assert.equal(r.result.status,'withheld');assert.equal(r.result.attempts,1);assert.ok(!r.frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'));
});
test('transport failure is not retried',async()=>{
 const c=cohort[0],slot=slots[0];let calls=0;
 const r=await trajectory(c,slot,async()=>{calls++;throw Error('failed');});
 assert.equal(calls,1);assert.equal(r.result.status,'generation-error');
});
test('runtime and protocol/cohort/schedule identities match frozen files',()=>{
 const freeze=load('./freeze.json');
 for(const [name,h] of Object.entries(freeze.runtimeFiles))assert.equal(hash(readFileSync(new URL('./'+name,import.meta.url),'utf8')),h);
 for(const [name,key] of [['protocol.md','protocolSha256'],['cohort.json','cohortSha256'],['slots.json','slotsSha256']])assert.equal(hash(readFileSync(new URL('./'+name,import.meta.url),'utf8')),freeze[key]);
 assert.ok(freeze.priorConservativeUSD+freeze.additionalBudgetUSD<=.15);
});
