"""Audit the fixed final comparison; arithmetic truth does not call the SDK."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from collections import Counter,defaultdict
import json
HERE=Path(__file__).resolve().parent;RUN=HERE/'run-01'
def load(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def digest(p):return sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def nodup(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate key')
  d[k]=v
 return d
def ref(context,source):return 'rec-'+sha256(json.dumps([context,1,source],separators=(',',':')).encode()).hexdigest()[:24]
def truth(c):
 case=c['case'];eligible=[]
 for record in c['snapshot']:
  valid=True
  for rule in case['rules']:
   actual=record['attributes'][rule['field']];bound=rule['value']
   ok=type(actual) is type(bound) and actual==bound if rule['op']=='eq' else actual<=bound if rule['op']=='lte' else actual>=bound
   valid=valid and ok
  if valid:eligible.append(record)
 rank=case['ranking'];best=(min if rank['direction']=='min' else max)(r['attributes'][rank['field']] for r in eligible)
 return {ref(c['context_id'],r['id']) for r in eligible},{ref(c['context_id'],r['id']) for r in eligible if r['attributes'][rank['field']]==best}
def valid_answer(raw,c):
 try:
  p=json.loads(raw,object_pairs_hook=nodup);eligible,optimal=truth(c)
  return isinstance(p,dict) and set(p)=={'schema','catalogSha256','selectedRef','eligibleRefs'} and p['schema']=='warden-selection/1' and p['catalogSha256']==c['catalog']['catalogSha256'] and isinstance(p['eligibleRefs'],list) and all(isinstance(x,str) for x in p['eligibleRefs']) and len(p['eligibleRefs'])==len(set(p['eligibleRefs'])) and set(p['eligibleRefs'])==eligible and p['selectedRef'] in optimal
 except (ValueError,TypeError):return False
def main():
 receipt=load(RUN/'execution-local.json');assert receipt['exitCode']==0 and receipt['collectionVerified'] and receipt['cleanup']['absent']
 assert digest(RUN/'outputs.tar.gz')==receipt['outputArchiveSha256'];hashes=load(RUN/'output-manifest.json');assert len(hashes)==receipt['verifiedOutputs']
 for name,h in hashes.items():assert digest(RUN/name)==h,name
 freeze=load(HERE/'freeze.json');plan=load(RUN/'out/frozen-before-api.json');execution=load(RUN/'out/execution.json')
 assert plan['freezeSha256']==digest(HERE/'freeze.json') and plan['protocolSha256']==freeze['protocolSha256']==digest(HERE/'protocol.md')
 assert freeze['cohortSha256']==digest(HERE/'cohort.json') and freeze['slotsSha256']==digest(HERE/'slots.json')
 for name,h in freeze['runtimeFiles'].items():assert digest(HERE/name)==h,name
 for c in execution['checks']:assert c['exitCode']==0 and digest(RUN/'out'/(c['name']+'.log'))==c['logSha256']
 assert execution['completed'] and execution['apiAttempts']<=120 and execution['heldUpperUSD']<=.08
 contexts={c['context_id']:c for c in load(HERE/'cohort.json')['contexts']};slots=plan['slots'];smap={s['slot_id']:s for s in slots}
 rows=lines(RUN/'out/trajectories.jsonl');assert len(rows)==120 and {r['slot_id'] for r in rows}==set(smap)
 preflight=lines(RUN/'out/preflight-requests.jsonl');assert len(preflight)==120;expected_requests={s['slot_id']:b for s,b in zip(slots,preflight)}
 ledger=lines(RUN/'out/relay/usage.jsonl');reserved={e['request_id']:e for e in ledger if e['event']=='reserved'};completed={e['request_id']:e for e in ledger if e['event']=='completed'}
 intents={e['slotId']:e for e in lines(RUN/'out/intents.jsonl')};assert len(reserved)==len(completed)==len(intents)==120
 cost=0;scheduled=0;offpeak=0;usage=Counter();models=Counter();api_errors=[]
 for rid,event in completed.items():
  response=load(RUN/'out/relay/resp'/(rid+'.json'));assert response['status']==event['status']
  if event['status']=='ok':
   u=event['usage'];charged=(u['prompt_tokens']-u.get('prompt_cache_hit_tokens',0))*300+u.get('prompt_cache_hit_tokens',0)*6+u['completion_tokens']*1200
   assert charged==event['charged_upper_nanousd'];usage.update({k:u.get(k,0) for k in ['prompt_tokens','prompt_cache_hit_tokens','completion_tokens']});models[event['actual_model']]+=1
  else:charged=10_000_000;api_errors.append({'requestId':rid,'error':event['error']})
  cost+=charged;when=datetime.fromisoformat(reserved[rid]['started_at']);peak=when.weekday()<5 and (1<=when.hour<4 or 6<=when.hour<10)
  offpeak+=not peak;scheduled+=charged if peak or event['status']!='ok' else charged//2
 assert cost/1e9==execution['heldUpperUSD']
 groups=defaultdict(Counter);by_context=defaultdict(Counter);outcomes={};audits=[];code_counts=defaultdict(Counter)
 for row in rows:
  s=smap[row['slot_id']];c=contexts[s['context_id']]
  for k,v in s.items():assert row[k]==v
  assert row['origin']==c['origin'] and row['catalog']==c['catalog']
  intent=intents[s['slot_id']];rid=intent['requestId'];p=RUN/'out/relay/req'/(rid+'.json');request=load(p);response=load(RUN/'out/relay/resp'/(rid+'.json'))
  assert digest(p)==intent['requestSha256']==reserved[rid]['request_sha256']==response['metadata']['request_sha256']
  assert request==expected_requests[s['slot_id']]
  assert request['messages'][:-2]==c['prior_body']['messages'] and request['tool_choice']=='none' and request['max_tokens']==700 and request['temperature']==.3
  input_answer=request['messages'][-2]['content'];feedback=request['messages'][-1]['content']
  assert sha256(input_answer.encode()).hexdigest()==row['inputAnswerSha256'] and sha256(feedback.encode()).hexdigest()==row['feedbackSha256']
  if s['population']=='failure':assert input_answer==c['invalid_answer'] and not valid_answer(input_answer,c)
  else:assert valid_answer(input_answer,c)
  if s['population']=='failure' and s['arm']=='old':assert feedback==c['old_invalid_feedback']
  if s['population']=='failure' and s['arm']=='witness':assert 'optimal value is' in feedback and 'Ranking ' in feedback
  ps=row['proposals'];assert len(ps)<=1 and row['result']['attempts']==1
  valid=False
  if ps:
   proposal=ps[0];assert proposal['requestId']==rid and proposal['attempt']==0
   assert response['status']=='ok' and response['provider_response']['choices'][0]['message']['content']==proposal['answer']
   assert sha256(proposal['answer'].encode()).hexdigest()==proposal['answerSha256']
   valid=valid_answer(proposal['answer'],c);assert valid==(proposal['decision']=='allow')
   code_counts[(s['population'],s['arm'])][proposal['code']]+=1
  key=(s['population'],s['arm']);g=groups[key];g['calls']+=1;g['valid']+=valid;g[row['result']['status']]+=1
  by_context[(s['context_id'],s['population'],s['arm'])]['calls']+=1;by_context[(s['context_id'],s['population'],s['arm'])]['valid']+=valid
  outcomes[(s['context_id'],s['population'],s['repeat'],s['arm'])]=valid
  assert row['result']['status']=='delivered' if valid else row['result']['status']!='delivered'
  frames=row['frames'];assert len(frames)==1 and frames[0].startswith('WARDEN: The external source contained text addressed to the assistant as instructions.')
  if valid:
   value=json.loads(frames[0].split('WARDEN_STRUCTURED_ANSWER\n')[1],object_pairs_hook=nodup);eligible,optimal=truth(c)
   assert value['selectedRef'] in optimal and set(value['eligibleRefs'])==eligible
   fields=list(dict.fromkeys([r['field'] for r in c['case']['rules']]+[c['case']['ranking']['field']]))
   expected={ref(c['context_id'],r['id']):{'field_'+str(i+1):r['attributes'][f] for i,f in enumerate(fields)} for r in c['snapshot'] if ref(c['context_id'],r['id']) in eligible}
   assert {r['ref']:r['attributes'] for r in value['records']}==expected
  else:assert 'WARDEN_STRUCTURED_ANSWER\n' not in frames[0] and 'WARDEN_RESULT_WITHHELD' in frames[0]
  audits.append({'slot_id':s['slot_id'],'valid':valid,'status':row['result']['status'],'noticePresent':True,'frameSha256':sha256(frames[0].encode()).hexdigest()})
 paired=defaultdict(Counter)
 for c in contexts.values():
  for population,n in [('failure',8),('valid-control',4)]:
   for r in range(n):
    a=outcomes[(c['context_id'],population,r,'old')];b=outcomes[(c['context_id'],population,r,'witness')]
    paired[population]['bothValid' if a and b else 'oldOnlyValid' if a else 'witnessOnlyValid' if b else 'bothInvalid']+=1
 a=groups[('failure','old')]['valid'];b=groups[('failure','witness')]['valid']
 predictions={'witnessAtLeast32of40':{'observed':b,'threshold':32,'met':b>=32},'witnessImprovementAtLeast8of40':{'observed':b-a,'threshold':8,'met':b-a>=8}}
 for arm in ['old','witness']:predictions['validControl_'+arm]={'observed':groups[('valid-control',arm)]['valid'],'threshold':19,'met':groups[('valid-control',arm)]['valid']>=19}
 result={'schema':'final-witness-analysis/1','scope':'Final fresh comparison on all five previously held contexts/four fixtures; selected known failures, not a new holdout or general security result.',
  'contexts':5,'distinctFixtures':4,'freshModelCalls':120,'groups':[{'population':p,'arm':arm,**dict(v),'codes':dict(code_counts[(p,arm)])} for (p,arm),v in groups.items()],
  'byContext':[{'context_id':cid,'origin':contexts[cid]['origin'],'case_id':contexts[cid]['case']['case_id'],'population':p,'arm':arm,**dict(v)} for (cid,p,arm),v in sorted(by_context.items())],
  'paired':{k:dict(v) for k,v in paired.items()},'failureDifferenceCount':b-a,'failureDifferencePercentagePoints':(b-a)*2.5,'predictions':predictions,
  'hostNoticeFrames':120,'unverifiedCandidatesForwarded':0,'apiErrors':api_errors,'reportedModels':dict(models),'usage':dict(usage),'usageCostAtPublishedTimeWindowUSD':scheduled/1e9,'accountingUSDPeakUpper':cost/1e9,
  'combinedWithPriorHoldoutPeakUSD':cost/1e9+freeze['priorConservativeUSD'],'combinedWithPriorHoldoutTimeWindowUSD':scheduled/1e9+.028934433,'additionalBudgetUSD':.08,'combinedStatedBudgetUSD':.15,'unambiguouslyOffPeakCalls':offpeak,
  'providerInvoiceVerified':False,'verifiedOutputs':len(hashes),'productCodeChangedDuringComparison':False,'seriesComplete':True,
  'limitations':['Five selected known failures spanning four fixtures; not independent holdout or deployment sample.','One additional research continuation; production two-repair ceiling unchanged.','Positive controls are constructed valid answers and have identical nominal-arm prompts.','Effect belongs to the complete changed feedback, not an isolated phrase or newly supplied raw record facts.','Values were in the catalog in both arms; no internal-cause inference.','Same-author AI-assisted unblinded preparation/audit; captured frames, not native GUI.']}
 assert result['combinedWithPriorHoldoutPeakUSD']<=.15
 put(HERE/'analysis.json',result);put(HERE/'output-audit.json',{'outputs':audits,'unverifiedCandidatesForwarded':0});put(HERE/'artifact-audit.json',{'verifiedOutputs':len(hashes),'outputArchiveSha256':receipt['outputArchiveSha256'],'modelRequestsBoundToReplies':120,'allPlannedSlotsRetained':True,'temporaryRootRemoved':True})
 print(json.dumps({k:result[k] for k in ['groups','paired','failureDifferenceCount','predictions','usageCostAtPublishedTimeWindowUSD','accountingUSDPeakUpper','combinedWithPriorHoldoutPeakUSD','verifiedOutputs']},indent=2))
if __name__=='__main__':main()
