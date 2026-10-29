"""Read-only collected-artifact accounting; no semantic inference or model calls."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from study import body,digest,canonical,schedule

HERE=Path(__file__).resolve().parent
RUN=HERE/'run-02'
def main():
 local=json.loads((RUN/'execution-local.json').read_text());assert local['exitCode']==0 and local['cleanup']['absent']
 assert sha256((RUN/'outputs.tar.gz').read_bytes()).hexdigest()==local['outputArchiveSha256']
 hashes=json.loads((RUN/'output-manifest.json').read_text())
 for name,h in hashes.items():assert sha256((RUN/name).read_bytes()).hexdigest()==h,name
 out=RUN/'out';execution=json.loads((out/'execution.json').read_text());plan=json.loads((out/'frozen-before-api.json').read_text())
 cases=json.loads((out/'workcases.json').read_text())['cases'];cmap={c['pair_id']:c for c in cases}
 assert execution['completed'] and execution['attempts']==288 and execution['recordedSlots']==288
 assert all(c['exitCode']==0 for c in execution['checks'])
 assert plan['slots']==schedule(cases)
 assert plan['protocolSha256']==sha256((HERE/'protocol.md').read_bytes()).hexdigest()
 assert plan['amendmentSha256']==sha256((HERE/'collection-amendment.md').read_bytes()).hexdigest()
 prepared={p['pair_id']:p for p in json.loads((out/'prepared.json').read_text())['results']}
 rows=[json.loads(x) for x in (out/'runs.jsonl').read_text().splitlines()]
 intents=[json.loads(x) for x in (out/'intents.jsonl').read_text().splitlines()]
 ledger=[json.loads(x) for x in (out/'relay/usage.jsonl').read_text().splitlines()]
 reserved=[x for x in ledger if x['event']=='reserved'];completed=[x for x in ledger if x['event']=='completed']
 assert len(rows)==len(intents)==len(reserved)==len(completed)==288
 assert not any(x['event']=='rejected' for x in ledger)
 assert len({r['slot_id'] for r in rows})==288
 tokens={'input':0,'cache_hit':0,'output':0};charged=0
 for i,(row,slot,intent) in enumerate(zip(rows,plan['slots'],intents)):
  assert all(row[k]==slot[k] for k in slot)
  assert row['status']=='ok' and row['finish_reason']=='stop' and row['response_model']=='deepseek-flash'
  c=cmap[row['pair_id']];expected=body(c,prepared[c['pair_id']][row['arm']]['reason'])
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
 assert charged/1e9==execution['heldUpperUSD']<.25
 hooks=json.loads((out/'final-hooks.json').read_text())['results'];assert len(hooks)==288
 notices=[r for r in hooks if r.get('last',{}).get('systemMessage')]
 assert len(notices)==192 and all(r['last'].get('decision') is None for r in notices)
 result={'schema':'fresh-recheck-artifact-audit/1','paidAttempts':288,'completeAnswers':288,'errors':0,'retainedRequests':288,'retainedResponses':288,'allOutputsHashVerified':len(hashes),'protocolFrozenBeforeEveryDispatch':True,'usageTokens':tokens,'conservativeAccountingUSD':charged/1e9,'guardContinuationNotices':192,'newGuardSecondContinuations':0,'remoteTemporaryRootRemoved':True,'semanticClaims':'not assessed by this accounting audit','currentInvoiceTariffVerified':False,'priorUnretainedCallsReported':288,'priorUnretainedConservativeAccountingUSDReported':0.053408928,'combinedConservativeAccountingUSD':charged/1e9+0.053408928}
 (HERE/'artifact-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
