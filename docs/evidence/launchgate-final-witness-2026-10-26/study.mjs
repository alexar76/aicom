import { createHash } from 'node:crypto';
import { createAnswerGate as oldGate } from './runtime-old/answer-gate.js';
import { createAnswerGate as newGate } from './runtime-new/answer-gate.js';
import { parseJsonStrict } from './runtime-new/jcs.js';
export const hash=text=>createHash('sha256').update(text).digest('hex');
export function gates(c){
 const options={sessionId:c.context_id,turn:1,rules:c.case.rules,records:c.snapshot,ranking:c.case.ranking,disclosure:c.condition==='injected'?'source-instructions':'external-data'};
 return {old:oldGate(options),witness:newGate(options)};
}
export function inputAnswer(c,slot,g){
 if(slot.population==='failure')return c.invalid_answer;
 return JSON.stringify({schema:'warden-selection/1',catalogSha256:g.catalog.catalogSha256,selectedRef:g.referenceForRecord(c.case.oracle.optimal[0]),eligibleRefs:c.case.oracle.eligible.map(id=>g.referenceForRecord(id))});
}
export function requestFor(c,slot){
 const pair=gates(c),g=pair[slot.arm],input=inputAnswer(c,slot,g),feedback=g.evaluate(input).feedback;
 if(JSON.stringify(pair.old.catalog)!==JSON.stringify(pair.witness.catalog))throw Error('catalog changed');
 if(slot.population==='failure'&&(pair.old.evaluate(input).feedback!==c.old_invalid_feedback||pair.old.evaluate(input).code!=='not-optimal'))throw Error('historical warning mismatch');
 return {body:{...c.prior_body,messages:[...c.prior_body.messages,{role:'assistant',content:input},{role:'user',content:feedback}]},input,feedback};
}
export async function trajectory(c,slot,call){
 const gate=gates(c).witness,prepared=requestFor(c,slot),frames=[],proposals=[];
 const result=await gate.run({maxCorrections:0,timeoutMs:120000,generate:async request=>{
  const response=await call(prepared.body,0,request.signal);const raw=response.answer,d=gate.evaluate(raw);
  let diagnostics={parseableWithoutDuplicates:false,extraFields:null};
  try{const v=parseJsonStrict(raw);diagnostics={parseableWithoutDuplicates:true,extraFields:v&&typeof v==='object'&&!Array.isArray(v)?Object.keys(v).filter(k=>!['schema','catalogSha256','selectedRef','eligibleRefs'].includes(k)):null};}catch{}
  proposals.push({attempt:0,requestId:response.requestId,answer:raw,answerSha256:hash(raw),decision:d.decision,code:d.code,diagnostics});return raw;
 },emit:text=>{frames.push(text);}});
 if(frames.length!==1||!frames[0].startsWith(gate.notice))throw Error('host notice custody');
 if(result.status!=='delivered'&&frames[0].includes('WARDEN_STRUCTURED_ANSWER\n'))throw Error('invalid delivery');
 return {...slot,origin:c.origin,case_id:c.case.case_id,catalog:gate.catalog,inputAnswerSha256:hash(prepared.input),feedbackSha256:hash(prepared.feedback),proposals,result,frames};
}
