"""Verify collected evidence and synchronize the Linux-generated local build."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUN=HERE/'run-01'

def digest(p): return sha256(p.read_bytes()).hexdigest()

def main():
    receipt=json.loads((RUN/'execution.json').read_text())
    assert len(receipt['checks'])==8 and all(c['exitCode']==0 for c in receipt['checks'])
    assert receipt['runtimeNetwork']=='none' and receipt['newModelCalls']==0 and receipt['cleanup']['absent']
    for c in receipt['checks']: assert digest(RUN/(c['name']+'.log'))==c['logSha256']
    assert digest(RUN/'outputs.tar.gz')==receipt['outputSha256']
    hashes=json.loads((RUN/'manifest.json').read_text())
    assert len(hashes)==receipt['verifiedOutputs']
    for name,h in hashes.items(): assert digest(RUN/name)==h,(name,'collected output mismatch')
    inputs=json.loads((RUN/'input-manifest.json').read_text())
    generated_inputs=[]
    for name,meta in inputs.items():
        if name.startswith('project/'):
            relative=name.removeprefix('project/')
            p=ROOT/'warden'/relative
            if digest(p)!=meta['sha256']:
                generated=RUN/'generated'/relative
                assert relative.startswith('claude-plugin/scripts/flow-guard') and generated.is_file() and digest(p)==digest(generated),(name,'source changed since the validated build')
                generated_inputs.append(relative)
    results=json.loads((RUN/'out/replay.json').read_text())
    assert results['summary']=={'savedPairs':12,'deterministicContradictions':4,'remainingContradictionsInUnchangedFinalAnswers':4,'supportedAnnotationPairsWithoutThisContradiction':8,'guardContinuationNotices':12,'modelTextDisclosureLosses':3,'lossesWithGuardNotice':3,'secondRechecksRequested':0,'modelCalls':0,'changedModelOutcomes':0}
    vitest=json.loads((RUN/'out/vitest.json').read_text())
    assert vitest['success'] and vitest['numPassedTests']==743 and vitest['numFailedTests']==0
    assert len(vitest['testResults'])==21
    assert 'Ran 24 tests' in (RUN/'probe-tests.log').read_text()
    assert '"scenarios":28' in (RUN/'redteam.log').read_text()
    synced={}
    for p in (RUN/'generated').rglob('*'):
        if p.is_file():
            relative=p.relative_to(RUN/'generated')
            target=ROOT/'warden'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
            synced[str(relative)]=digest(target)
    (HERE/'build-sync.json').write_text(json.dumps({'sourceManifestSha256':digest(RUN/'input-manifest.json'),'nonGeneratedSourceInputsStillMatch':True,'generatedInputsReplacedByValidatedBuild':generated_inputs,'linuxGeneratedFiles':synced},indent=2)+'\n')
    data=ROOT/'warden/docs/data/launchgate-constraint-evidence-2026-10-26'
    data.mkdir(parents=True,exist_ok=True)
    for origin,name in [('out/replay.json','results.json'),('out/cases.json','cases.json'),('input-manifest.json','input-manifest.json')]: shutil.copyfile(RUN/origin,data/name)
    public={key:receipt[key] for key in ['image','runtime','runtimeNetwork','inputFiles','archiveBytes','archiveSha256','newModelCalls','githubWrites','npmPublished','checks','outputSha256','verifiedOutputs']}
    public['temporaryRootRemoved']=receipt['cleanup']['absent']
    public['wardentests']={'passed':743,'files':21,'newConstraintTests':29}
    public['pythonTestsPassed']=24
    public['deterministicGateScenarios']=28
    (data/'execution.json').write_text(json.dumps(public,indent=2)+'\n')
    names=['results.json','cases.json','input-manifest.json','execution.json']
    (data/'manifest.json').write_text(json.dumps({name:digest(data/name) for name in names},indent=2)+'\n')
    print('Verified',len(hashes),'output hashes; synchronized',len(synced),'Linux-generated files; product evidence copied.')

if __name__=='__main__': main()
