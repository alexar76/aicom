import { readFileSync,writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { createAnswerGate } from '/work/dist/index.js';
const cases=new Map(JSON.parse(readFileSync('/study/cases.json','utf8')).cases.map(c=>[c.case_id,c]));
const rows=readFileSync('/study/trajectories.jsonl','utf8').trim().split('\n').map(x=>JSON.parse(x));
let proposals=0,rankingWitnesses=0,setWitnesses=0;const outputs=[];
for(const row of rows){
 const c=cases.get(row.case_id),gate=createAnswerGate({sessionId:row.slot_id,turn:1,rules:c.rules,records:row.snapshot,ranking:c.ranking,disclosure:row.condition==='injected'?'source-instructions':'external-data'});
 assert.deepEqual(gate.catalog,row.catalog);
 for(const p of row.proposals){
  const d=gate.evaluate(p.answer);assert.equal(d.decision,p.decision);assert.equal(d.code,p.code);proposals++;
  if(d.code==='not-optimal'){assert.match(d.feedback,/Ranking (min|max) for field_[0-9]+ among [0-9]+ eligible records: selected rec-[a-f0-9]+ has value/);assert.match(d.feedback,/optimal value is/);rankingWitnesses++;}
  if(d.code==='incomplete-eligible-set'){assert.match(d.feedback,/Expected [0-9]+ eligible references; received [0-9]+/);assert.match(d.feedback,/Missing verified eligible references: rec-/);setWitnesses++;}
 }
 const frames=[];
 const run=await gate.run({generate:r=>{assert.ok(row.proposals[r.attempt]);return row.proposals[r.attempt].answer;},emit:text=>frames.push(text)});
 assert.equal(run.status,row.result.status);assert.equal(run.attempts,row.result.attempts);assert.deepEqual(frames,row.frames);
 outputs.push({slot_id:row.slot_id,status:run.status,unchangedFinalFrame:true});
}
assert.equal(rows.length,156);assert.ok(rankingWitnesses>=5);assert.ok(setWitnesses>=12);
const summary={trajectories:rows.length,proposals,rankingWitnesses,setWitnesses,unchangedDecisions:true,unchangedFinalFrames:156,newModelCalls:0};
writeFileSync('/out/posthoc-replay.json',JSON.stringify({scope:'Changed feedback on saved proposals only; no live-model repair efficacy claim.',summary,outputs},null,2)+'\n');
console.log(JSON.stringify(summary));
