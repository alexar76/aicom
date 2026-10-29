"""Freeze all five retained live failures and matched message arms before API calls."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json,random,tarfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=HERE.parent/'launchgate-prospective-holdout-2026-10-26'
def digest(p):return sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 assert not (HERE/'cohort.json').exists(),'do not change an existing fixed cohort'
 cases={c['case_id']:c for c in json.loads((OLD/'cases.json').read_text())['cases']}
 rows=[json.loads(x) for x in (OLD/'run-01/out/trajectories.jsonl').read_text().splitlines()]
 failures=sorted([r for r in rows if r['population']!='deterministic' and r['result']['status']=='withheld'],key=lambda r:r['slot_id'])
 assert len(failures)==5 and sum(r['population']=='natural' for r in failures)==2
 cohort=[]
 for r in failures:
  last=r['proposals'][-1];assert last['code']=='not-optimal' and not last['synthetic']
  p=OLD/'run-01/out/relay/req'/(last['requestId']+'.json');request=json.loads(p.read_text())
  cohort.append({'context_id':r['slot_id'],'case':cases[r['case_id']],'origin':r['population'],'condition':r['condition'],'snapshot':r['snapshot'],
   'catalog':r['catalog'],'prior_body':request,'prior_body_sha256':digest(p),'invalid_answer':last['answer'],'invalid_answer_sha256':last['answerSha256'],
   'old_invalid_feedback':r['result']['decisions'][-1]['feedback']})
 put(HERE/'cohort.json',{'at':datetime.now(timezone.utc).isoformat(),'sourceOutputsSha256':digest(OLD/'run-01/outputs.tar.gz'),'contexts':cohort})
 slots=[]
 for c in cohort:
  for population,repeats in [('failure',8),('valid-control',4)]:
   for repeat in range(repeats):
    arms=['old','witness'];random.Random(c['context_id']+population+str(repeat)).shuffle(arms)
    block=[]
    for arm in arms:
     s={'context_id':c['context_id'],'population':population,'repeat':repeat,'arm':arm}
     s['slot_id']=sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()[:32];block.append(s)
    slots.append(block)
 random.Random(2026102607).shuffle(slots);slots=[s for block in slots for s in block]
 assert len(slots)==120 and len({s['slot_id'] for s in slots})==120
 put(HERE/'slots.json',slots)
 old_runtime=HERE/'runtime-old';new_runtime=HERE/'runtime-new';old_runtime.mkdir();new_runtime.mkdir()
 sync=json.loads((HERE.parent/'launchgate-ranking-feedback-2026-10-26/build-sync.json').read_text())
 with tarfile.open(OLD/'run-01/inputs.tar.gz') as archive:
  for name in ['answer-gate.js','jcs.js']:
   (old_runtime/name).write_bytes(archive.extractfile('runtime/'+name).read())
   p=ROOT/'warden/dist'/name;assert digest(p)==sync['linuxGeneratedFiles']['dist/'+name]
   (new_runtime/name).write_bytes(p.read_bytes())
 for folder in [old_runtime,new_runtime]:(folder/'package.json').write_text('{"type":"module"}\n')
 put(HERE/'freeze.json',{'at':datetime.now(timezone.utc).isoformat(),'protocolSha256':digest(HERE/'protocol.md'),'cohortSha256':digest(HERE/'cohort.json'),'slotsSha256':digest(HERE/'slots.json'),
  'runtimeFiles':{str(p.relative_to(HERE)):digest(p) for folder in [old_runtime,new_runtime] for p in folder.iterdir()},'currentSourceSha256':digest(ROOT/'warden/src/answer-gate.ts'),
  'priorConservativeUSD':.057868866,'additionalBudgetUSD':.08,'combinedUpperCapUSD':.137868866,'maxCalls':120})
 print(json.dumps({'contexts':5,'failureCalls':80,'validControlCalls':40,'maxCalls':120,'additionalBudgetUSD':.08,'combinedUpperCapUSD':.137868866}))
if __name__=='__main__':main()
