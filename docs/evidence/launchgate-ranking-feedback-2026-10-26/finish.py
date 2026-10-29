"""Verify the separate offline build/replay and synchronize generated files locally."""
from pathlib import Path
from hashlib import sha256
import json,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];RUN=HERE/'run-02'
def digest(p):return sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
 receipt=load(RUN/'execution-local.json');assert receipt['exitCode']==0 and receipt['collectionVerified'] and receipt['cleanup']['absent']
 assert digest(RUN/'outputs.tar.gz')==receipt['outputArchiveSha256'];hashes=load(RUN/'output-manifest.json');assert len(hashes)==receipt['verifiedOutputs']
 for name,h in hashes.items():assert digest(RUN/name)==h,name
 execution=load(RUN/'out/execution.json');assert execution['completed'] and execution['newModelCalls']==0 and execution['testNetwork']=='none'
 assert len(execution['checks'])==8
 for c in execution['checks']:assert c['exitCode']==0 and digest(RUN/'out'/(c['name']+'.log'))==c['logSha256']
 manifest=load(RUN/'input-manifest.json');generated_inputs=[]
 for name,m in manifest.items():
  if name.startswith('project/'):
   relative=name.removeprefix('project/');p=ROOT/'warden'/relative
   if digest(p)!=m['sha256']:
    built=RUN/'out/generated'/relative
    assert relative.startswith('claude-plugin/scripts/flow-guard') and built.is_file() and digest(p)==digest(built),name
    generated_inputs.append(relative)
 tests=load(RUN/'out/vitest.json');new=load(RUN/'out/answer-gate-vitest.json')
 assert tests['success'] and tests['numFailedTests']==0 and len(tests['testResults'])==24
 assert new['success'] and new['numFailedTests']==0 and len(new['testResults'])==2
 replay=load(RUN/'out/posthoc-replay.json')['summary'];assert replay['unchangedFinalFrames']==156 and replay['unchangedDecisions'] and replay['newModelCalls']==0
 assert '"scenarios":28' in (RUN/'out/redteam.log').read_text()
 synced={}
 for p in (RUN/'out/generated').rglob('*'):
  if p.is_file():
   relative=p.relative_to(RUN/'out/generated');target=ROOT/'warden'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);synced[str(relative)]=digest(target)
 put(HERE/'build-sync.json',{'sourceManifestSha256':digest(RUN/'input-manifest.json'),'nonGeneratedInputsStillMatch':True,'generatedInputsReplaced':generated_inputs,'linuxGeneratedFiles':synced})
 results={'scope':'Separate post-hoc feedback improvement; no model rerun, frozen study outcomes unchanged.','run':'run-02','host':'factory-vps','wardenTestsPassed':tests['numPassedTests'],'wardenTestFiles':24,'gateTestsPassed':new['numPassedTests'],'gateTestFiles':2,'redteamScenarios':28,'verifiedOutputs':len(hashes),'linuxGeneratedFiles':len(synced),'replay':replay,'newModelCalls':0,'failedOfflineRunRetained':'run-01: test supplied records instead of reference strings; fixed test, not validator relaxation.','npmPublished':False,'githubWrites':False}
 put(HERE/'results.json',results)
 data=ROOT/'warden/docs/data/launchgate-ranking-feedback-2026-10-26';data.mkdir(parents=True,exist_ok=True)
 sources={'results.json':HERE/'results.json','execution.json':RUN/'out/execution.json','posthoc-replay.json':RUN/'out/posthoc-replay.json','input-manifest.json':RUN/'input-manifest.json','protocol.md':HERE/'protocol.md'}
 for name,p in sources.items():shutil.copyfile(p,data/name)
 put(data/'manifest.json',{name:digest(data/name) for name in sources})
 print(json.dumps(results,indent=2))
if __name__=='__main__':main()
