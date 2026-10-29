// New structured host boundary against post-hoc projected reviewed sets. No NLP, new generation or native GUI claim.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createAnswerGate } from '/work/dist/index.js';
const cases=JSON.parse(readFileSync('/study/historical-inputs.json','utf8')).cases;
const rows=[];
for(const c of cases){
 const gate=createAnswerGate({sessionId:'project-'+c.slot_id,turn:1,rules:c.fixture.criterion.constraints,records:c.fixture.records.map(r=>({id:r.id,attributes:Object.fromEntries(c.fixture.criterion.constraints.map(rule=>[rule.field,r[rule.field]]))})),ranking:{field:c.fixture.criterion.rank_by.field,direction:c.fixture.criterion.rank_by.direction==='asc'?'min':'max'},disclosure:'source-instructions'});
 const proposal=c.explicit_eligible_ids?JSON.stringify({schema:'warden-selection/1',catalogSha256:gate.catalog.catalogSha256,selectedRef:gate.referenceForRecord(c.selected_id),eligibleRefs:c.explicit_eligible_ids.map(id=>gate.referenceForRecord(id))}):c.original_answer;
 const d=gate.evaluate(proposal);
 if(c.reviewed_grounding==='contradicted')assert.equal(d.decision,'deny');
 if(!c.explicit_eligible_ids)assert.equal(d.decision,'unknown');
 const output=[];
 const run=await gate.run({maxCorrections:0,generate:()=>proposal,emit:text=>output.push(text)});
 assert.equal(output.length,1);assert.ok(output[0].startsWith(gate.notice));
 if(d.decision!=='allow')assert.ok(!output[0].includes('WARDEN_STRUCTURED_ANSWER'));
 rows.push({slot_id:c.slot_id,projectionAvailable:!!c.explicit_eligible_ids,reviewedGrounding:c.reviewed_grounding,decision:d.decision,code:d.code,violations:d.violations,runStatus:run.status});
}
const summary={historicalAnswers:rows.length,contradictedStructuredProjections:rows.filter(r=>r.reviewedGrounding==='contradicted').length,contradictedProjectionsDenied:rows.filter(r=>r.reviewedGrounding==='contradicted'&&r.decision==='deny').length,unsupportedProseUnknown:rows.filter(r=>!r.projectionAvailable&&r.decision==='unknown').length,validExplicitProjectionsAllowed:rows.filter(r=>r.decision==='allow').length,unverifiedCandidatesForwarded:0,newModelCalls:0};
assert.equal(summary.historicalAnswers,384);assert.equal(summary.contradictedProjectionsDenied,50);
writeFileSync('/out/historical-replay.json',JSON.stringify({scope:'Post-hoc structured projection from reviewed annotations; not automatic prose validation or model correction efficacy.',summary,rows},null,2)+'\n');
console.log(JSON.stringify(summary));
