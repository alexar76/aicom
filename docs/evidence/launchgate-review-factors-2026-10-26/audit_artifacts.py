"""Read-only collected-artifact accounting; no semantic inference or model calls."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'warden/scripts/selection-probe'))
from study import body,digest,canonical,schedule,review_for

HERE=Path(__file__).resolve().parent
RUN=HERE/'run-01'
def main():
 local=json.loads((RUN/'execution-local.json').read_text());assert local['exitCode']==0 and local['cleanup']['absent']
 assert sha256((RUN/'outputs.tar.gz').read_bytes()).hexdigest()==local['outputArchiveSha256']
 hashes=json.loads((RUN/'output-manifest.json').read_text())
 for name,h in hashes.items():assert sha256((RUN/name).read_bytes()).hexdigest()==h,name
 out=RUN/'out';execution=json.loads((out/'execution.json').read_text());plan=json.loads((out/'frozen-before-api.json').read_text())
 cases=json.loads((out/'workcases.json').read_text())['cases'];cmap={c['pair_id']:c for c in cases}
 assert execution['completed'] and execution['attempts']==384 and execution['recordedSlots']==384
 assert all(c['exitCode']==0 for c in execution['checks'])
 assert plan['slots']==schedule(cases)
 assert plan['protocolSha256']==sha256((HERE/'protocol.md').read_bytes()).hexdigest()
 assert plan['custodySha256']==sha256((HERE/'custody.md').read_bytes()).hexdigest()
 prepared={p['pair_id']:p for p in json.loads((out/'prepared.json').read_text())['results']}
 rows=[json.loads(x) for x in (out/'runs.jsonl').read_text().splitlines()]
 intents=[json.loads(x) for x in (out/'intents.jsonl').read_text().splitlines()]
 ledger=[json.loads(x) for x in (out/'relay/usage.jsonl').read_text().splitlines()]
 reserved=[x for x in ledger if x['event']=='reserved'];completed=[x for x in ledger if x['event']=='completed']
 assert len(rows)==len(intents)==len(reserved)==len(completed)==384
 assert not any(x['event']=='rejected' for x in ledger)
 assert len({r['slot_id'] for r in rows})==384
 tokens={'input':0,'cache_hit':0,'output':0};charged=0
 for i,(row,slot,intent) in enumerate(zip(rows,plan['slots'],intents)):
  assert all(row[k]==slot[k] for k in slot)
  assert row['status']=='ok' and row['finish_reason']=='stop' and row['response_model']=='deepseek-flash'
  c=cmap[row['pair_id']];expected=body(c,review_for(c,prepared[c['pair_id']]['new_facts']['reason'],row['arm']))
  assert row['slot_id']==digest({'planSha256':digest(plan),'slot':slot})[:32]
  path=out/'relay/req'/(row['slot_id']+'.json');raw=path.read_bytes()
  assert json.loads(raw)==expected and sha256(raw).hexdigest()==row['requestSha256']==intent['requestSha256']
  response=json.loads((out/'relay/resp'/(row['slot_id']+'.json')).read_text());assert response==row['apiResponse']
  assert response['metadata']['request_sha256']==row['requestSha256']
  assert datetime.fromisoformat(response['metadata']['started_at'])>=datetime.fromisoformat(plan['startedAt'])
  provider=response['provider_response'];assert provider['choices'][0]['message']['content']==row['answer']
  assert digest(row['answer'])==row['answer_sha256']
  u=provider['usage'];tokens['input']+=u['prompt_tokens'];tokens['cache_hit']+=u.get('prompt_cache_hit_tokens',0);tokens['output']+=u['completion_tokens']
  charged+=(u['prompt_tokens']-u.get('prompt_cache_hit_tokens',0))*300+u.get('prompt_cache_hit_tokens',0)*6+u['completion_tokens']*1200
 assert charged==sum(x['charged_upper_nanousd'] for x in completed)==ledger[-1]['held_upper_nanousd_after']
 assert charged/1e9==execution['heldUpperUSD']<.12
 hooks=json.loads((out/'final-hooks.json').read_text())['results'];assert len(hooks)==384
 notices=[r for r in hooks if r.get('last',{}).get('systemMessage')]
 assert len(notices)==384 and all(r['last'].get('decision') is None for r in notices)
 result={'schema':'review-factor-artifact-audit/1','paidAttempts':384,'completeAnswers':384,'errors':0,'retainedRequests':384,'retainedResponses':384,'allOutputsHashVerified':len(hashes),'protocolFrozenBeforeEveryDispatch':True,'usageTokens':tokens,'conservativeAccountingUSD':charged/1e9,'guardContinuationNotices':384,'newGuardSecondContinuations':0,'remoteTemporaryRootRemoved':True,'semanticClaims':'not assessed by this accounting audit','currentInvoiceTariffVerified':False,'previousStudyAccountingUSDIncludingLostAttempt':0.106847232,'combinedAccountingUSDWithPreviousStudy':charged/1e9+0.106847232}
 (HERE/'artifact-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
