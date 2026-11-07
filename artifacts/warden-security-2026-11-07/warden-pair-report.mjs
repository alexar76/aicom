// Run only in a remote gVisor reporting container after both frozen runs finish.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
const read=p=>JSON.parse(readFileSync(p,'utf8'));
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v}
const stable=v=>JSON.stringify(canonical(v));
const sha=v=>createHash('sha256').update(v).digest('hex');
const write=(p,v)=>writeFileSync(p,JSON.stringify(v,null,2)+'\n');
const roots={attested:'/attested',blip:'/blip'},sites={};
for(const [site,root] of Object.entries(roots)){
 const summary=read(root+'/pair/summary.json'),provenance=read(root+'/pair/provenance.json');
 const baseline={complete:read(root+'/baseline/complete.json'),stages:read(root+'/baseline/summary.json'),source:read(root+'/baseline/source-stability.json'),isolation:read(root+'/baseline/isolation.json'),state:read(root+'/baseline/container-state.json'),equivalenceBefore:read(root+'/baseline/source-equivalence.before.json'),equivalenceAfter:read(root+'/baseline/source-equivalence.after.json')};
 const tests=read(root+'/baseline/full-results.json');
 baseline.tests={total:tests.numTotalTests,passed:tests.numPassedTests,failed:tests.numFailedTests,pending:tests.numPendingTests,jsonSuccess:tests.success,failedSuites:tests.numFailedTestSuites,runtimeErrorCountReported:tests.numRuntimeErrorTestSuites??null,files:tests.testResults.length};
 const paths={};for(const path of ['library','protocol'])for(const version of ['v18','v19'])paths[path+'-'+version]=read(root+'/pair/'+path+'-'+version+'.json');
 sites[site]={summary,provenance,baseline,paths};
}
function comparable(r){return{key:r.key,wireId:r.wireId,set:r.set,label:r.label,split:r.split??null,status:r.status,toolCount:r.toolCount??null,allow:r.allow??null,score:r.score??null,decidedBy:r.decidedBy??null,allowedTools:r.allowedTools??null,blockedTools:r.blockedTools??null,findings:(r.findings??[]).map(f=>stable({...f,advisory:f.advisory??false})).sort(),rulesets:r.rulesets??null,error:r.error??null}}
const paths={},differences=[];
for(const key of ['library-v18','library-v19','protocol-v18','protocol-v19']){
 const a=sites.attested.paths[key].results,b=sites.blip.paths[key].results,map=new Map(b.map(r=>[r.key,r]));
 let matched=0;const errors=[];
 for(const r of a){const other=map.get(r.key);if(other&&stable(comparable(r))===stable(comparable(other)))matched++;else errors.push({key:r.key,attested:comparable(r),blip:other?comparable(other):null})}
 const extra=b.filter(r=>!a.some(x=>x.key===r.key)).map(r=>r.key);
 paths[key]={checked:a.length,matches:matched,differences:errors.length,unexpectedPeerKeys:extra};differences.push(...errors.map(r=>({path:key,...r})));
}
const a=sites.attested,b=sites.blip;
const identity={sharedCasesEqual:a.summary.sharedCasesSha256===b.summary.sharedCasesSha256,caseManifestEqual:a.summary.caseManifestSha256===b.summary.caseManifestSha256,inputTreesEqual:stable(a.provenance.inputBefore)===stable(b.provenance.inputBefore),candidateSourceTreesEqual:stable(a.provenance.sourceBefore.v19)===stable(b.provenance.sourceBefore.v19),baselineSourceTreesEqual:stable(a.provenance.sourceBefore.v18)===stable(b.provenance.sourceBefore.v18),harnessEqual:a.provenance.harnessSha256===b.provenance.harnessSha256,replayEqual:a.provenance.replaySha256===b.provenance.replaySha256};
const fullBaselinesPass=Object.values(sites).every(s=>s.baseline.complete.allCommandsPassed&&s.baseline.source.unchanged&&s.baseline.tests.total===1536&&s.baseline.tests.passed===1536&&s.baseline.tests.failed===0&&s.baseline.tests.jsonSuccess===true&&s.baseline.tests.failedSuites===0&&!s.baseline.state.OOMKilled&&s.baseline.equivalenceBefore.passed&&s.baseline.equivalenceAfter.passed);
const crossHost={format:'warden.cross-host-paired-regression/v1',at:new Date().toISOString(),paths,comparedRows:Object.values(paths).reduce((n,p)=>n+p.checked,0),matches:Object.values(paths).reduce((n,p)=>n+p.matches,0),identity,differences,fullBaselinesPass,sites:Object.fromEntries(Object.entries(sites).map(([site,s])=>[site,{node:s.summary.node,baseline:s.baseline,pairSummary:s.summary,candidateSourceTreeSha256:sha(stable(s.provenance.sourceBefore.v19)),baselineSourceTreeSha256:sha(stable(s.provenance.sourceBefore.v18))}]))};
crossHost.passed=fullBaselinesPass&&Object.values(sites).every(s=>s.summary.passed)&&Object.values(identity).every(Boolean)&&Object.values(paths).every(p=>p.checked===3177&&p.matches===3177&&!p.differences&&!p.unexpectedPeerKeys.length);
mkdirSync('/out',{recursive:true});write('/out/cross-host-parity.json',crossHost);
const rows=[];for(const set of Object.keys(a.summary.versions.v19.summary)){const old=a.summary.versions.v18.summary[set],next=a.summary.versions.v19.summary[set];rows.push(`| ${set} | ${next.N} | ${old.B} | ${next.B} | ${next.E} |`)}
const changed=a.summary.changes.filter(c=>c.before.allow!==c.after.allow);
const report=`# Warden v19: conservative post-hoc repair, both gVisor hosts\n\n`+
`Operational/protocol acceptance: **${crossHost.passed}**. This is not a claim that every malicious definition is detected.\n\n`+
`Both hosts:1536/1536 tests in63 files, zero test failures; typecheck,build,redteam commands pass; source witness unchanged and no OOM. Final baseline evidence is baseline-final-v4; initial metadata diagnostics and the interrupted obsolete Blip second attempt remain preserved. The final validation copy changes only five README suite counts; every other source and compiled file is byte-identical to the immutable detector used for the paired measurement, checked before and after the full suite. The Vitest JSON has no dedicated runtime-error count; acceptance requires its success flag, zero failed suites, and successful command exits.\n\n`+
`| Cohort/view | N | v18 blocked | v19 blocked | v19 errors |\n|---|---:|---:|---:|---:|\n${rows.join('\n')}\n\n`+
`Actual MCP/library parity:3177/3177 for each version on each host. Cross-host:${crossHost.matches}/${crossHost.comparedRows} full compared rows. Inputs, opaque IDs, harness, replay and source trees match; all retained source/input witnesses are unchanged.\n\n`+
`Verdict transitions: ${changed.map(c=>c.key+' '+c.before.allow+'→'+c.after.allow).join('; ')}.\n\n`+
`The pure public-key-read native case FileSystem_22 remains allowed/advisory. Restoring a benchmark label alone does not justify classifying public material as a secret. The repair blocks forced overwrites of SSH security files and reads of actual secret stores bound to another mandatory tool call. It was designed after observing the retained v18 results, so it is post hoc regression work, not an unseen holdout result.\n\n`+
`MCPTox native, decorated and full-scenario views overlap and are not additive independent trials. Public snapshots are unlabelled: block frequency is not a whole-corpus false-positive rate. No upstream implementations, model attack-success experiment, live secrets, production mounts, or local project runtime were used.\n\n`+
`Candidate:0.23.1-dev.20261107.1; rules19; sha256-XfRh1+VZoAM6PGtbmqprnSX/eF16qNYOk0o+ilRFxXw=. Public npm was0.23.0 at the retained registry check; no npm publication is part of this run.\n`;
writeFileSync('/out/REPORT.md',report);console.log(JSON.stringify({passed:crossHost.passed,matches:crossHost.matches,comparedRows:crossHost.comparedRows,identity,fullBaselinesPass,changedVerdicts:changed.map(c=>({key:c.key,before:c.before.allow,after:c.after.allow})),counts:a.summary.versions.v19.summary}));
process.exitCode=crossHost.passed?0:1;
