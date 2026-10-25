import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { diffToolDefinitions, formatDefinitionDiff } from '/warden/package/dist/review-diff.js';
const OUT='/out';
const hash = b => createHash('sha256').update(b).digest('hex');
const oldBytes=await readFile('/work/from-toolsets.json');
const newBytes=await readFile('/work/to-toolsets.json');
const before=JSON.parse(oldBytes), after=JSON.parse(newBytes);
const change=JSON.parse(await readFile('/work/change.json','utf8'));
const transcript=[], assertions=[];
function check(name, test) {
  try { test(); assertions.push({name,passed:true}); }
  catch(e) { assertions.push({name,passed:false,message:e.message}); }
}
const diff=diffToolDefinitions(before,after);
const review=formatDefinitionDiff(diff).join('\n');
await writeFile(`${OUT}/diff.json`,JSON.stringify(diff,null,2)+'\n');
await writeFile(`${OUT}/review.txt`,review+'\n');
const negative=structuredClone(after);
const proposed=negative.find(t=>t.name==='propose_setup_plan');
assert(proposed.description.includes(' and carry on without asking.'));
proposed.description=proposed.description.replace(' and carry on without asking.','.');
const negDiff=diffToolDefinitions(before,negative);
await writeFile(`${OUT}/negative-control-diff.json`,JSON.stringify(negDiff,null,2)+'\n');
check('Both frozen full toolsets have 33 definitions',()=>assert.equal(before.length,33)&&assert.equal(after.length,33));
check('Only two existing descriptions changed; no tools added or removed',()=>{
 assert.equal(diff.changed,2);assert.equal(diff.added,0);assert.equal(diff.removed,0);
 assert.deepEqual(diff.changes.map(c=>c.tool).sort(),['get_setup_run','propose_setup_plan']);
 for(const t of diff.changes)assert.deepEqual(t.fields.map(f=>f.path),['description']);
});
check('New approval phrasing is tagged on propose_setup_plan',()=>{
 const t=diff.changes.find(c=>c.tool==='propose_setup_plan');
 assert(t.attention?.includes('approval'));assert.equal(diff.attention,1);
 assert(t.fields[0].attention?.includes('approval'));
});
check('Readable review retains removed and added words and attention cue',()=>{
 assert.match(review,/Read first: 1 tool gains/);assert.match(review,/propose_setup_plan \(approval\)/);
 assert.match(review,/on without asking/);assert.match(review,/\[-/);assert.match(review,/\{\+/);
});
check('Removing only the newly added without-asking phrase removes approval tag',()=>assert.equal(negDiff.attention,0));
check('Identical original snapshot has an empty diff',()=>assert.equal(diffToolDefinitions(before,before).changes.length,0));
const child=spawn(process.execPath,['/warden/package/dist/mcp-server.js'],{
 env:{...process.env,WARDEN_STATE_DIR:'/tmp/jakub-pins',WARDEN_ALLOW_PIN_CHANGES:'1'},
 stdio:['pipe','pipe','pipe']
});
let pending,buffer='',stderr='';let nextId=0;
child.stderr.on('data',d=>stderr+=d);
child.stdout.on('data',d=>{
 buffer+=d;
 let ix;while((ix=buffer.indexOf('\n'))>=0){
  const line=buffer.slice(0,ix);buffer=buffer.slice(ix+1);
  if(!line.trim())continue;
  try { const response=JSON.parse(line); if(pending&&response.id===pending.id){const p=pending;pending=undefined;clearTimeout(p.timer);p.resolve(response);} }
  catch(e){if(pending){pending.reject(e);pending=undefined;}}
 }
});
child.on('exit',(code,signal)=>{if(pending){pending.reject(new Error(`WARDEN exited code=${code} signal=${signal}: ${stderr}`));pending=undefined;}});
async function rpc(method,params){
 const request={jsonrpc:'2.0',id:++nextId,method,params};
 const response=await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending=undefined;reject(new Error(`RPC timeout ${method}`));},15000);
  pending={id:request.id,resolve,reject,timer};child.stdin.write(JSON.stringify(request)+'\n');
 });
 transcript.push({request,response});return response;
}
async function tool(name,args){
 const response=await rpc('tools/call',{name,arguments:args});
 if(response.error||response.result?.isError)throw new Error(`${name}: ${JSON.stringify(response)}`);
 return response.result.structuredContent;
}
const server={id:'jakub-mapled-frozen-17172',name:'Mapled frozen replay',transport:'stdio',command:'npx',args:['-y','@mapled/mcp']};
const info={name:'mapled',version:'0.1.0'}; // Historical serverInfo declaration, not the npm artifact version.
let rpcError=null;
try{
 const init=await rpc('initialize',{protocolVersion:'2025-11-25',capabilities:{},clientInfo:{name:'jakub-published-replay',version:'1'}});
 check('Published WARDEN identifies itself as 0.21.0',()=>assert.equal(init.result.serverInfo.version,'0.21.0'));
 const initial=await tool('status_mcp_server',{server,tools:before,server_info:info});
 await writeFile(`${OUT}/status-before-approval.json`,JSON.stringify(initial,null,2)+'\n');
 check('Disposable store starts without approval',()=>assert.equal(initial.previous,null));
 const approve=await tool('approve_mcp_server',{server,tools:before,server_info:info,reviewed_tools_hash:initial.currentToolsHash,
  reviewed_identity_hash:initial.currentIdentityHash,previous_pin_revision:initial.previousRevision});
 await writeFile(`${OUT}/approval-original.json`,JSON.stringify(approve,null,2)+'\n');
 check('Only original snapshot is explicitly approved in disposable state',()=>assert.equal(approve.approved,true));
 const unchanged=await tool('status_mcp_server',{server,tools:before,server_info:info});
 check('Approved original snapshot is unchanged',()=>assert.equal(unchanged.changed,false));
 const changed=await tool('status_mcp_server',{server,tools:after,server_info:info});
 await writeFile(`${OUT}/status-after-change.json`,JSON.stringify(changed,null,2)+'\n');
 await writeFile(`${OUT}/rpc-review.txt`,changed.reviewText+'\n');
 check('Changed full tools require review with same declared server version',()=>{
  assert.equal(changed.changed,true);assert.equal(changed.origin.approvedVersion,'0.1.0');assert.equal(changed.origin.currentVersion,'0.1.0');
  assert.equal(changed.currentIdentityHash,unchanged.currentIdentityHash);assert.notEqual(changed.currentToolsHash,unchanged.currentToolsHash);
 });
 check('Read-only changed status does not automatically replace stored approval',()=>{
  assert.equal(changed.previousRevision,unchanged.previousRevision);assert.equal(changed.previous.toolsHash,unchanged.currentToolsHash);
 });
 check('Status review tags actual approval phrase and warns about unpinned launcher',()=>{
  assert.equal(changed.changes.attention,1);assert.equal(changed.origin.launch.pinned,false);
  assert.match(changed.reviewText,/without asking/);assert.match(changed.reviewText,/not pinned|unpinned|no exact|exact version|unversioned/i);
 });
 const again=await tool('status_mcp_server',{server,tools:after,server_info:info});
 check('Repeating status retains old approval and continues reporting drift',()=>{
  assert.equal(again.previousRevision,changed.previousRevision);assert.equal(again.changed,true);
 });
 const oldAgain=await tool('status_mcp_server',{server,tools:before,server_info:info});
 check('Returning to original snapshot remains unchanged after changed-status reads',()=>assert.equal(oldAgain.changed,false));
}catch(e){rpcError=e.stack;assertions.push({name:'Full status → approve → status RPC sequence',passed:false,message:e.message});}
finally{child.stdin.end();child.kill('SIGTERM');await writeFile(`${OUT}/rpc-stderr.txt`,stderr);}
const moduleFiles=['package.json','dist/review-diff.js','dist/mcp-tools.js','dist/mcp-rpc.js','dist/mcp-server.js','dist/pinning.js','dist/pin-store.js','dist/state.js'];
const modules={};for(const f of moduleFiles){const b=await readFile(`/warden/package/${f}`);modules[f]={bytes:b.length,sha256:hash(b)};}
await writeFile(`${OUT}/rpc-transcript.json`,JSON.stringify(transcript,null,2)+'\n');
await writeFile(`${OUT}/assertions.json`,JSON.stringify(assertions,null,2)+'\n');
const result={type:'jakub.published-warden.real-diff-replay.v1',recordedAt:new Date().toISOString(),platform:process.platform,arch:process.arch,node:process.version,
 wardenVersion:'0.21.0',changeId:change.id,tools:{before:before.length,after:after.length},inputHashes:{'from-toolsets.json':hash(oldBytes),'to-toolsets.json':hash(newBytes)},
 packageVersions:{before:'0.21.5',after:'0.21.6',basis:'Separate historical run metadata and npm static-source mapping; target packages were not executed by this replay.'},
 serverInfo:{before:info,after:info,kind:'Historical self-reported MCP initialize version; not package verification'},
 targetExecuted:false,networkUsed:false,disposableApprovalOnly:true,modules,rpcError,
 assertions:{passed:assertions.filter(a=>a.passed).length,failed:assertions.filter(a=>!a.passed).length},limitations:[
 'This checks deterministic review output and approval-state behavior, not human review usability.',
 'Real tool definitions are untrusted data, not instructions. No Mapled process or handler was executed.',
 'The npx launch is metadata only; no claim that an installed target artifact was verified.',
 'Approval in this replay is isolated test state and has no effect on production or a real client.'
 ]};
await writeFile(`${OUT}/result.json`,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
for(const a of assertions)console.log(`${a.passed?'PASS':'FAIL'} ${a.name}${a.message?' '+a.message:''}`);
if(result.assertions.failed)process.exitCode=1;
