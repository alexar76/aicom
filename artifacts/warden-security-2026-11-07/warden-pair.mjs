// Offline gVisor-only paired regression harness. Upstream tool implementations
// and attack text are never executed. The real CLI talks to our JSON replay.
import {readFileSync, writeFileSync, readdirSync, mkdirSync, rmSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';

const root='/shared', out='/results', replay='/harness/replay-server.mjs';
const site=process.env.WARDEN_TEST_HOST;
if(!['attested','blip'].includes(site)) throw Error('Explicit host label required');
const pilot=process.argv.includes('--pilot');
const sha=b=>createHash('sha256').update(b).digest('hex');
const hash=p=>sha(readFileSync(p));
const read=p=>JSON.parse(readFileSync(p,'utf8'));
const write=(p,v)=>writeFileSync(p,JSON.stringify(v,null,2)+'\n');
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v}
const stable=v=>JSON.stringify(canonical(v));
function tree(dir){const files={};function visit(p){for(const d of readdirSync(p,{withFileTypes:true}).sort((a,b)=>a.name<b.name?-1:a.name>b.name?1:0)){if(d.name==='node_modules'||d.name==='.git')continue;const f=join(p,d.name);if(d.isDirectory())visit(f);else if(d.isFile())files[f.slice(dir.length+1)]=hash(f)}}visit(dir);return files}
function toolsFor(c){
 let raw=c.tools;
 if(raw===undefined&&typeof c.toolsFile==='string'){
  const p=resolve(root,c.toolsFile);
  if(!p.startsWith(root+'/'))throw Error('toolsFile escapes shared input');
  if(c.toolsFileSha256&&hash(p)!==c.toolsFileSha256)throw Error('Shared tool file hash mismatch');
  const value=read(p); raw=Array.isArray(value)?value:value.tools;
 }
 if(!Array.isArray(raw))throw Error('Tools not an array');
 const names=new Set();
 return raw.map(t=>{
  if(!t||typeof t!=='object'||Array.isArray(t)||typeof t.name!=='string'||!t.name.length||names.has(t.name))throw Error('Invalid/duplicate tool name');
  names.add(t.name);
  for(const key of ['description','title'])if(t[key]!==undefined&&typeof t[key]!=='string')throw Error('Invalid '+key);
  for(const key of ['inputSchema','outputSchema','annotations'])if(t[key]!==undefined&&(!t[key]||typeof t[key]!=='object'||Array.isArray(t[key])))throw Error('Invalid '+key);
  return {...t,description:t.description===undefined?'':t.description,inputSchema:t.inputSchema===undefined?{type:'object',properties:{}}:t.inputSchema};
 });
}
mkdirSync(out,{recursive:true});
const inputBefore=tree(root), sourceBefore={v18:tree('/baseline'),v19:tree('/candidate')};
const document=read(root+'/cases.json');
if(!Array.isArray(document.cases)||document.cases.length!==3177)throw Error('Expected exactly3177 common cases');
const all=document.cases.map((c,i)=>{
 if(!c||typeof c!=='object'||typeof c.key!=='string'||typeof c.set!=='string'||typeof c.label!=='string')throw Error('Missing stable case metadata');
 const {tools,...metadata}=c;
 return {...metadata,wireId: c.wireId??c.opaqueId??('w'+sha('warden shared opaque IDs20261107|'+c.key).slice(0,24)),ordinal:i};
});
for(const field of ['key','wireId'])if(new Set(all.map(c=>c[field])).size!==all.length)throw Error('Duplicate '+field);
if(all.some(c=>typeof c.wireId!=='string'||!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(c.wireId)))throw Error('Unsafe opaque replay identity');
const cases=pilot?all.filter(c=>all.filter(x=>x.set===c.set).findIndex(x=>x.key===c.key)<2||/\/X-FileSystem_(?:20|22|23)$/.test(c.key)||c.originalCaseKey==='B11-ssh-howto'):all;
const sets=[...new Set(cases.map(c=>c.set))].sort();
const policy={blockAtSeverity:'high',sensitiveToolPatterns:[],allowUnknownServers:true,pinToolDefs:true};
write(out+'/policy.json',policy);
write(out+'/case-manifest.json',{pilot,cases:cases.map(c=>({...c,tools:undefined})),scheduled:cases.length,totalAvailable:all.length});
const provenance={format:'warden.paired-regression/v1',site,pilot,startedAt:new Date().toISOString(),node:process.version,policy,caseManifestSha256:hash(out+'/case-manifest.json'),sharedCasesSha256:hash(root+'/cases.json'),harnessSha256:hash('/harness/warden-pair.mjs'),replaySha256:hash(replay),inputBefore,sourceBefore,versions:{v18:'/baseline',v19:'/candidate'},method:'Identical advertised tool definitions through full library gates and actual MCP initialize/tools/list via CLI; no upstream tool execution, network or model calls.',limitations:['The paired v19 repair is post hoc on observed v18 regressions.','MCPTox native/decorated/full-scenario views overlap; totals are not independent attacks.','These rates classify tool definitions and do not measure LLM attack success.']};
write(out+'/provenance.json',provenance);
const replayDir=out+'/replay';mkdirSync(replayDir,{recursive:true});
const originalByKey=new Map(document.cases.map(c=>[c.key,c]));
const inputErrors=[];
for(const c of cases){try{const tools=toolsFor(originalByKey.get(c.key));write(join(replayDir,c.wireId+'.json'),{wireId:c.wireId,tools})}catch(e){inputErrors.push({key:c.key,error:String(e)})}}
write(out+'/input-errors.json',inputErrors);
if(inputErrors.length)throw Error('Common input normalization errors: '+inputErrors.length);
const server=c=>({id:c.wireId,name:c.wireId,transport:'stdio',command:process.execPath,args:[replay,join(replayDir,c.wireId+'.json')]});
const choose=v=>({allow:v.allow,score:v.score,decidedBy:v.decidedBy??null,allowedTools:v.allowedTools,blockedTools:v.blockedTools,findings:v.findings,rulesets:v.rulesets});
function summary(rows){const counts={};for(const set of sets){const part=rows.filter(r=>r.set===set);const group=x=>({N:x.length,C:x.filter(r=>r.status==='scanned').length,B:x.filter(r=>r.status==='scanned'&&r.allow===false).length,A:x.filter(r=>r.status==='scanned'&&r.allow===true&&r.findings?.some(f=>f.advisory&&['static-scan','threat-feed'].includes(f.gate))).length,E:x.filter(r=>r.status!=='scanned').length,S:0,U:0});counts[set]={...group(part),labels:Object.fromEntries([...new Set(part.map(r=>r.label))].sort().map(label=>[label,group(part.filter(r=>r.label===label))])),splits:Object.fromEntries([...new Set(part.map(r=>r.split??'none'))].sort().map(split=>[split,group(part.filter(r=>(r.split??'none')===split))]))}}return counts}
const libraries={}, modules={};
for(const version of ['v18','v19']){
 const sdk=await import(pathToFileURL((version==='v18'?'/baseline':'/candidate')+'/dist/index.js').href);modules[version]=sdk;
 const rows=[],start=performance.now();
 for(const c of cases){let row={...c};const t=performance.now();try{const tools=toolsFor(originalByKey.get(c.key));const w=sdk.Warden.create({policy,threatFeed:new sdk.ThreatFeed(),store:{getPin:async()=>undefined,putPin:async()=>{}},log:sdk.silentLogger()});const verdict=await w.vet(server(c),tools),failures=verdict.findings.filter(f=>f.code==='GATE_ERROR');row={...row,status:failures.length?'error':'scanned',toolCount:tools.length,...choose(verdict),...(failures.length?{error:failures.map(f=>f.message).join('; ')}:{})}}catch(error){row={...row,status:'error',error:String(error)}}row.durationMs=performance.now()-t;rows.push(row);if(rows.length%100===0)console.log(JSON.stringify({stage:'library',version,completed:rows.length,total:cases.length}))}
 libraries[version]=rows;write(out+'/library-'+version+'.json',{version,ruleset:sdk.staticScanRulesetRef(),summary:summary(rows),durationMs:performance.now()-start,results:rows});
}
function comparable(r){return{status:r.status,toolCount:r.toolCount??null,allow:r.allow??null,score:r.score??null,decidedBy:r.decidedBy??null,allowedTools:r.allowedTools??null,blockedTools:r.blockedTools??null,findings:(r.findings??[]).map(f=>stable({...f,advisory:f.advisory??false})).sort()}}
const protocols={};
for(const version of ['v18','v19']){
 const product=version==='v18'?'/baseline':'/candidate',dir=out+'/protocol-'+version;
 mkdirSync(dir,{recursive:true});
 const expected=new Map(libraries[version].map(r=>[r.wireId,r])),rows=[],differences=[],batches=[],start=performance.now();
 for(let at=0;at<cases.length;at+=64){
  const group=cases.slice(at,at+64),batch=String(at/64+1).padStart(3,'0'),config=dir+'/batch-'+batch+'-config.json',report=dir+'/batch-'+batch+'-report.json';
  write(config,{mcpServers:Object.fromEntries(group.map(c=>[c.wireId,{command:process.execPath,args:server(c).args}]))});
  rmSync(report,{force:true});
  const command=[product+'/dist/mcp-server.js','scan',config,'--json-file',report,'--policy',out+'/policy.json','--state-dir','/tmp/pins-'+version,'--timeout','15000','--concurrency','1'];
  const p=spawnSync(process.execPath,command,{env:{PATH:'/usr/local/bin:/usr/bin:/bin',HOME:'/tmp',NO_COLOR:'1',WARDEN_STATE_DIR:'/tmp/state-'+version},encoding:'utf8',timeout:240000,maxBuffer:64*1024*1024,detached:true,killSignal:'SIGTERM'});
  try{if(p.pid)process.kill(-p.pid,'SIGKILL')}catch{}
  writeFileSync(dir+'/batch-'+batch+'.stdout',p.stdout??'');writeFileSync(dir+'/batch-'+batch+'.stderr',p.stderr??'');
  let output,parseError;try{output=read(report);if(!Array.isArray(output.servers))throw Error('Missing servers')}catch(e){parseError=String(e)}
  const returned=new Map(),duplicates=[];for(const r of output?.servers??[]){if(returned.has(r.key))duplicates.push(r.key);returned.set(r.key,r)}
  const extra=[...returned.keys()].filter(k=>!group.some(c=>c.wireId===k));
  const expectedExit=(output?.servers??[]).some(r=>r.allow===false)?1:0;
  batches.push({batch,command:[process.execPath,...command],exitCode:p.status,signal:p.signal,error:p.error?String(p.error):null,parseError,expectedExit,duplicates,extra,metadataMatches:output?.tool==='warden-scan'&&output?.launch===true&&stable(output?.policy)===stable(policy)&&stable(output?.ruleset)===stable(modules[version].staticScanRulesetRef())});
  for(const c of group){const actual=returned.get(c.wireId);const row=actual?{...c,status:actual.status,toolCount:actual.toolCount,...choose(actual),error:actual.error}:{...c,status:'missing',error:parseError??'Missing CLI row'};rows.push(row);if(stable(comparable(row))!==stable(comparable(expected.get(c.wireId))))differences.push({key:c.key,wireId:c.wireId,library:comparable(expected.get(c.wireId)),protocol:comparable(row)})}
  write(dir+'/progress.json',{completed:rows.length,total:cases.length,differences:differences.length});console.log(JSON.stringify({stage:'protocol',version,completed:rows.length,total:cases.length,differences:differences.length}));
 }
 protocols[version]={version,ruleset:modules[version].staticScanRulesetRef(),summary:summary(rows),durationMs:performance.now()-start,checked:rows.length,matches:rows.length-differences.length,differences,batches,results:rows};write(out+'/protocol-'+version+'.json',protocols[version]);
}
const prior=new Map(libraries.v18.map(r=>[r.key,r])),changes=[];
for(const r of libraries.v19){const before=prior.get(r.key);if(stable(comparable(before))!==stable(comparable(r)))changes.push({key:r.key,set:r.set,label:r.label,before:comparable(before),after:comparable(r)})}
const inputUnchanged=stable(inputBefore)===stable(tree(root));
const sourceUnchanged=stable(sourceBefore)===stable({v18:tree('/baseline'),v19:tree('/candidate')});
const parity=Object.fromEntries(Object.entries(protocols).map(([v,p])=>[v,{checked:p.checked,matches:p.matches,differences:p.differences.length,batchesValid:p.batches.every(b=>b.metadataMatches&&b.exitCode===b.expectedExit&&!b.error&&!b.parseError&&!b.duplicates.length&&!b.extra.length)}]));
const libraryErrors=Object.fromEntries(Object.entries(libraries).map(([v,r])=>[v,r.filter(x=>x.status!=='scanned').map(({key,error})=>({key,error}))]));
const passed=inputUnchanged&&sourceUnchanged&&Object.values(libraryErrors).every(x=>!x.length)&&Object.values(parity).every(p=>p.checked===cases.length&&p.matches===cases.length&&p.batchesValid);
const final={format:provenance.format,site,pilot,startedAt:provenance.startedAt,completedAt:new Date().toISOString(),node:process.version,scheduled:cases.length,sharedCasesSha256:provenance.sharedCasesSha256,caseManifestSha256:provenance.caseManifestSha256,versions:Object.fromEntries(Object.entries(libraries).map(([v,r])=>[v,{ruleset:modules[v].staticScanRulesetRef(),summary:summary(r)}])),parity,libraryErrors,inputUnchanged,sourceUnchanged,changes,passed};
write(out+'/summary.json',final);console.log('COMPLETE',JSON.stringify({...final,changes:changes.map(c=>({key:c.key,before:c.before.allow,after:c.after.allow}))}));process.exitCode=passed?0:1;
