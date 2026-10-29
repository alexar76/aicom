"""Verify collected Linux outputs and synchronize that exact validated build locally."""
from hashlib import sha256
import json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUN=HERE/'run-03'
def digest(path):return sha256(path.read_bytes()).hexdigest()
def put(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def main():
 receipt=json.loads((RUN/'execution-local.json').read_text())
 assert receipt['exitCode']==0 and receipt['collectionVerified'] and receipt['cleanup']['absent']
 assert digest(RUN/'outputs.tar.gz')==receipt['outputArchiveSha256']
 hashes=json.loads((RUN/'output-manifest.json').read_text())
 assert len(hashes)==receipt['verifiedOutputs']
 for name,h in hashes.items():assert digest(RUN/name)==h,name
 execution=json.loads((RUN/'out/execution.json').read_text())
 assert execution['completed'] and execution['testNetwork']=='none' and execution['newModelCalls']==0
 assert len(execution['checks'])==8 and all(c['exitCode']==0 for c in execution['checks'])
 for c in execution['checks']:assert digest(RUN/'out'/(c['name']+'.log'))==c['logSha256']
 inputs=json.loads((RUN/'input-manifest.json').read_text())
 generated_inputs=[]
 for name,meta in inputs.items():
  if name.startswith('project/'):
   relative=name.removeprefix('project/');current=ROOT/'warden'/relative
   if digest(current)!=meta['sha256']:
    generated=RUN/'out/generated'/relative
    assert relative.startswith('claude-plugin/scripts/flow-guard') and generated.is_file() and digest(current)==digest(generated),(name,'changed after validation')
    generated_inputs.append(relative)
 vitest=json.loads((RUN/'out/vitest.json').read_text());new=json.loads((RUN/'out/answer-gate-vitest.json').read_text())
 assert vitest['success'] and vitest['numFailedTests']==0 and len(vitest['testResults'])==24
 assert new['success'] and new['numFailedTests']==0 and len(new['testResults'])==2
 replay=json.loads((RUN/'out/historical-replay.json').read_text())
 assert replay['summary']['historicalAnswers']==384 and replay['summary']['contradictedProjectionsDenied']==50
 assert '"scenarios":28' in (RUN/'out/redteam.log').read_text()
 synced={}
 for p in (RUN/'out/generated').rglob('*'):
  if p.is_file():
   relative=p.relative_to(RUN/'out/generated');target=ROOT/'warden'/relative
   target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);synced[str(relative)]=digest(target)
 put(HERE/'build-sync.json',{'sourceManifestSha256':digest(RUN/'input-manifest.json'),'nonGeneratedSourceInputsStillMatch':True,'generatedInputsReplacedByValidatedBuild':generated_inputs,'linuxGeneratedFiles':synced})
 summary={'scope':'Offline SDK/stdio verification; historical structured projection, no new model calls or automatic prose validation.',
  'run':'run-03','host':'factory-vps','runtime':'runc','testNetwork':'none','wardenTestsPassed':vitest['numPassedTests'],'wardenTestFiles':24,
  'newGateTestsPassed':new['numPassedTests'],'newGateTestFiles':2,'redteamScenarios':28,'verifiedOutputs':len(hashes),'linuxGeneratedFiles':len(synced),
  'historicalReplay':replay['summary'],'temporaryRootRemoved':True,'newModelCalls':0,'githubWrites':False,'npmPublished':False,
  'failedRunsRetained':['run-01: duplicate-key test syntax error','run-02: escaped-duplicate-key test syntax error']}
 put(HERE/'results.json',summary)
 data=ROOT/'warden/docs/data/launchgate-answer-gate-2026-10-26';data.mkdir(parents=True,exist_ok=True)
 for origin,name in [(HERE/'results.json','results.json'),(RUN/'out/execution.json','execution.json'),(RUN/'input-manifest.json','input-manifest.json'),(HERE/'stubborn-transcript.json','stubborn-transcript.json'),(RUN/'out/historical-replay.json','historical-replay.json')]:shutil.copyfile(origin,data/name)
 put(data/'manifest.json',{p.name:digest(p) for p in data.iterdir() if p.is_file() and p.name!='manifest.json'})
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
