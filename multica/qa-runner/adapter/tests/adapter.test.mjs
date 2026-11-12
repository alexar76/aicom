import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:https';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {TaskAdapter} from '../../../../warden/dist/task-adapter.js';
import {flowPre,flowPost,loadPolicy} from '../../../../warden/dist/flow-guard.js';
import {refuses} from '../../../../warden/dist/flow-guard-unattended.js';
import {createWardenPlugin} from '../../../../warden/dist/opencode-plugin.js';

const hash=value=>createHash('sha256').update(value).digest('hex');
const serverPath=fileURLToPath(new URL('../../../../warden/dist/mcp-server.js',import.meta.url));
const status={job:'platform_smoke',checks:[{name:'backend_health',pass:true,status:200},{name:'modelmarket_https',pass:true,status:200},{name:'hub_https',pass:true,status:200}],passed:true,exit_code:0};
async function fixture(t){
  const root=mkdtempSync(join(tmpdir(),'qa-adapter-tls-'));const state=join(root,'state');mkdirSync(state,{mode:0o700});
  const policyPath=join(root,'policy.json'),manifestPath=join(state,'task-manifest.json');
  const seen=[];
  const server=createServer({key:readFileSync(process.env.QA_TEST_TLS_KEY),cert:readFileSync(process.env.QA_TEST_TLS_CERT)},(req,res)=>{
    let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{seen.push({method:req.method,url:req.url,body,authorization:req.headers.authorization,cookie:req.headers.cookie,transferEncoding:req.headers['transfer-encoding'],contentLength:req.headers['content-length']});res.setHeader('content-type','application/json');res.end(JSON.stringify(status));});
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  t.after(async()=>{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));rmSync(root,{recursive:true,force:true});});
  const url=`https://127.0.0.1:${server.address().port}/run/platform-smoke`;
  const manifest={version:1,taskId:'qa_tls_fixture',expiresAt:new Date(Date.now()+3600000).toISOString(),transport:'https',resources:[],operations:[{id:'platform_smoke',title:'Fixed secretless platform smoke',maxUses:10,request:{method:'POST',url,headers:{accept:'application/json'}}}]};
  const save=()=>{const bytes=JSON.stringify(manifest)+'\n';writeFileSync(manifestPath,bytes,{mode:0o600});writeFileSync(policyPath,JSON.stringify({mode:'ask',answerNote:'instruction',taskAdapter:{mode:'capabilities',server:'qa_runner',manifestSha256:hash(bytes)}}),{mode:0o600});};save();
  const env={PATH:'/usr/local/bin:/usr/bin:/bin',HOME:root,WARDEN_STATE_DIR:state,WARDEN_FLOW_POLICY:policyPath};
  const base={session_id:'qa-tainted-root',cwd:join(root,'project')};
  const taint=()=>{flowPost({...base,tool_name:'Read',tool_input:{file_path:join(root,'project','.env')},tool_response:'KEY='+['ghp','A7bCd9EfGh2IjKl5MnOp8QrSt1UvWx4YzAb6C'].join('_')},env);flowPost({...base,tool_name:'Bash',tool_input:{command:'multica issue get SYNTHETIC-1'},tool_response:'External issue data'},env);};
  const pre=(name,args)=>flowPre({...base,tool_name:name,tool_input:args},env);
  return{root,state,policyPath,manifestPath,manifest,save,env,seen,taint,pre,adapter:new TaskAdapter(env)};
}

test('fixed ID executes real TLS bytes after credentials/outside text while generic Bash stays refused',async t=>{
  const f=await fixture(t);f.taint();
  assert.equal(f.pre('mcp__qa_runner__task_execute',{id:'platform_smoke'}),undefined);
  const detail={};const decision=flowPre({session_id:'qa-tainted-root',cwd:join(f.root,'project'),tool_name:'Bash',tool_input:{command:'npm run smoke'}},f.env,'hook',detail);
  assert.ok(decision);assert.equal(refuses(decision,detail,'data'),true);
  const result=await f.adapter.call('task_execute',{id:'platform_smoke'});
  assert.deepEqual(JSON.parse(result.text),status);assert.equal(result.status,200);
  assert.deepEqual(f.seen,[{method:'POST',url:'/run/platform-smoke',body:'',authorization:undefined,cookie:undefined,transferEncoding:undefined,contentLength:'0'}]);
  assert.equal(loadPolicy(f.env).mode,'ask');assert.equal(loadPolicy(f.env).answerNote,'instruction');
});

test('arbitrary arguments/job/URL/body are refused before any TLS request',async t=>{
  const f=await fixture(t);f.taint();
  for(const args of [{id:'other_job'},{id:'platform_smoke',url:'https://example.invalid'},{id:'platform_smoke',body:'data'},{id:'platform_smoke',command:'cat .env'},{id:'platform_smoke',headers:{}},{id:'platform_smoke',nested:{value:1}}]){
    assert.ok(f.pre('mcp__qa_runner__task_execute',args));await assert.rejects(f.adapter.call('task_execute',args));
  }
  await assert.rejects(f.adapter.call('task_run',{id:'platform_smoke'}));await assert.rejects(f.adapter.call('task_read',{id:'platform_smoke'}));
  assert.equal(f.seen.length,0);
});

test('expired and tampered manifests remove delegation and never reach the broker',async t=>{
  const f=await fixture(t);f.taint();
  f.manifest.expiresAt=new Date(Date.now()-1000).toISOString();f.save();
  assert.ok(f.pre('mcp__qa_runner__task_execute',{id:'platform_smoke'}));await assert.rejects(f.adapter.call('task_execute',{id:'platform_smoke'}));
  f.manifest.expiresAt=new Date(Date.now()+3600000).toISOString();f.save();
  const tampered=JSON.parse(readFileSync(f.manifestPath,'utf8'));tampered.operations[0].request.url='https://example.invalid/run/platform-smoke';writeFileSync(f.manifestPath,JSON.stringify(tampered));
  assert.ok(f.pre('mcp__qa_runner__task_execute',{id:'platform_smoke'}));await assert.rejects(f.adapter.call('task_execute',{id:'platform_smoke'}));assert.equal(f.seen.length,0);
});

test('ten-use capability remains spent across adapter recreation and identical lease rewrite',async t=>{
  const f=await fixture(t);
  for(let i=0;i<10;i++)await new TaskAdapter(f.env).call('task_execute',{id:'platform_smoke'});
  f.save();await assert.rejects(new TaskAdapter(f.env).call('task_execute',{id:'platform_smoke'}),/budget/);
  assert.equal(f.seen.length,10);
});

async function mcp(t,f,withCA=true){
  const assignments=Object.entries({...f.env,...(withCA?{NODE_EXTRA_CA_CERTS:process.env.NODE_EXTRA_CA_CERTS}:{})}).map(([key,value])=>key+'='+value);
  const child=spawn('/usr/bin/env',['-i',...assignments,process.execPath,serverPath,'task'],{stdio:['pipe','pipe','pipe'],env:{PATH:'/usr/bin:/bin'}});
  t.after(()=>child.kill('SIGKILL'));
  let buffer='',sequence=0;const pending=new Map();
  child.stdout.on('data',chunk=>{buffer+=chunk;let cut;while((cut=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,cut);buffer=buffer.slice(cut+1);if(!line)continue;const msg=JSON.parse(line);const finish=pending.get(msg.id);if(finish){pending.delete(msg.id);finish(msg);}}});
  const call=(method,params)=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('MCP fixture timeout'));},5000);pending.set(id,value=>{clearTimeout(timer);resolve(value);});child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');});
  await call('initialize',{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'qa-fixture',version:'1'}});
  return{name:'qa_runner',call};
}

test('actual env-i MCP TaskAdapter succeeds only with fixed ID and rejects custom URL over stdio',async t=>{
  const f=await fixture(t);f.taint();const client=await mcp(t,f);
  const plugin=await createWardenPlugin({block:'data',env:f.env,mcpServers:['qa_runner']})({directory:join(f.root,'project')});
  await plugin.event({event:{type:'session.created',properties:{info:{id:'qa-tainted-root'}}}});
  await plugin['tool.execute.before']({tool:'qa_runner_task_execute',sessionID:'qa-tainted-root'},{args:{id:'platform_smoke'}});
  await assert.rejects(plugin['tool.execute.before']({tool:'bash',sessionID:'qa-tainted-root'},{args:{command:'npm run smoke'}}),/Refused/);
  const listing=await client.call('tools/list',{});assert.ok(listing.result.tools.some(tool=>tool.name==='task_execute'));
  const bad=await client.call('tools/call',{name:'task_execute',arguments:{id:'platform_smoke',url:'https://example.invalid'}});assert.equal(bad.result.isError,true);assert.equal(f.seen.length,0);
  assert.equal(f.pre('mcp__qa_runner__task_execute',{id:'platform_smoke'}),undefined);
  const good=await client.call('tools/call',{name:'task_execute',arguments:{id:'platform_smoke'}});assert.notEqual(good.result.isError,true);
  const outcome=JSON.parse(good.result.content[0].text);assert.deepEqual(JSON.parse(outcome.text),status);assert.equal(f.seen.length,1);
});

test('actual env-i MCP refuses TLS without the public CA and never sends a broker request',async t=>{
  const f=await fixture(t);const client=await mcp(t,f,false);
  const value=await client.call('tools/call',{name:'task_execute',arguments:{id:'platform_smoke'}});assert.equal(value.result.isError,true);assert.equal(f.seen.length,0);
});
