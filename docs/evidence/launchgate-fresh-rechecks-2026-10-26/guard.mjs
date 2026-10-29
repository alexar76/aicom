// Actual frozen compiled hooks. No model calls or client rendering assertions.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {runFlowHook} from './runtime/flow-guard.js';

const cases=JSON.parse(readFileSync(process.argv[3],'utf8')).cases;
function run(c,arm,final){
 const dir=mkdtempSync(join(tmpdir(),'fresh-recheck-'));
 const session=`fresh-${c.pair_id}-${arm}`;
 const env={WARDEN_STATE_DIR:dir,WARDEN_FLOW_POLICY:'',WARDEN_FLOW_MODE:'ask'};
 const hook=(event,data)=>{const out=runFlowHook(event,JSON.stringify({session_id:session,cwd:'/work/selection-fixture',...data}),env);return out?JSON.parse(out):null;};
 try{
  hook('prompt',{prompt:c.fixture.user_request});
  const pre=hook('pre',{tool_name:'mcp__records__get_records',tool_input:{}});
  assert.ok(!['ask','deny'].includes(pre?.hookSpecificOutput?.permissionDecision));
  const post=hook('post',{tool_name:'mcp__records__get_records',tool_input:{},tool_response:c.tool_result});
  const contract=arm==='new_facts'?{...c.initial_check,sessionId:session}:undefined;
  const first=hook('stop',{last_assistant_message:c.initial_answer,stop_hook_active:false,...(contract?{answer_check:contract}:{})});
  assert.equal(first?.decision,'block');
  if(!final)return {first,post};
  const check=arm==='new_facts'&&final.final_check?{...final.final_check,sessionId:session}:undefined;
  const last=hook('stop',{last_assistant_message:final.answer,stop_hook_active:true,...(check?{answer_check:check}:{})});
  assert.equal(last?.decision,undefined);
  assert.match(last.systemMessage,/source contained text addressed to the assistant as instructions/);
  return {first,last,extractionCoverage:final.final_coverage};
 }finally{rmSync(dir,{recursive:true,force:true});}
}
if(process.argv[2]==='prepare'){
 const results=cases.map(c=>{const plain=run(c,'new_plain'),facts=run(c,'new_facts');return {pair_id:c.pair_id,old:c.old_stop,new_plain:plain.first,new_facts:facts.first,post:plain.post};});
 writeFileSync(process.argv[4],JSON.stringify({results},null,2)+'\n');
}else if(process.argv[2]==='final'){
 const rows=JSON.parse(readFileSync(process.argv[4],'utf8')).rows;
 const results=rows.map(r=>r.arm==='old'||r.status!=='ok'?{slot_id:r.slot_id,scope:'no-new-hook-replay'}:{slot_id:r.slot_id,...run(cases.find(c=>c.pair_id===r.pair_id),r.arm,r)});
 writeFileSync(process.argv[5],JSON.stringify({results},null,2)+'\n');
}else throw Error('op');
