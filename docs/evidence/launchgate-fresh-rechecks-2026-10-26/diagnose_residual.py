"""Verify delivery/detection for residual failures from retained request bytes only."""
from hashlib import sha256
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 out=HERE/'run-02/out'
 audit=json.loads((HERE/'reason-audit.json').read_text())['pairs']
 failures={r['pair_id']:r for r in audit if r['slot']['treatment']=='new_facts' and r['final']['grounding']=='contradicted'}
 rows=[json.loads(x) for x in (out/'runs.jsonl').read_text().splitlines()]
 cases={c['pair_id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
 hooks={r['slot_id']:r for r in json.loads((out/'final-hooks.json').read_text())['results']}
 checks={r['slot_id']:r for r in json.loads((out/'final-check-input.json').read_text())['rows']}
 zero=next(c['source_pair_id'] for c in json.loads((HERE/'analysis.json').read_text())['treatments']['new_facts']['by_initial_error'] if c['corrected']==0)
 result=[]
 for row in rows:
  if row['slot_id'] not in failures:continue
  path=out/'relay/req'/(row['slot_id']+'.json');raw=path.read_bytes();assert sha256(raw).hexdigest()==row['requestSha256']
  request=json.loads(raw);c=cases[row['pair_id']];review=request['messages'][-1]['content']
  assert request['messages'][-1]['role']=='user'
  source_position=next(i+1 for i,r in enumerate(c['tool_result']['hotels']) if r['id']=='T-4-C')
  expected=f'Claimed eligible item #{source_position} violates rule #1: actual 190; required <= 150.'
  assert expected in review
  assert checks[row['slot_id']]['final_check']['claims']['eligibleIds']==['T-4-A','T-4-B','T-4-C']
  assert 'actual 190; required <= 150' in hooks[row['slot_id']]['last']['systemMessage']
  result.append({'slot_id':row['slot_id'],'source_pair_id':row['pair_id'],'repeat':row['repeat'],'request_sha256':row['requestSha256'],'counterevidence_quote':expected,'source_record_id':'T-4-C','source_record_position_1_based':source_position,'review_delivered_to_api':True,'final_eligible_list_extracted':True,'final_guard_notice_retained_numeric_disagreement':True,'answer_exactly_unchanged':row['answer']==c['initial_answer'],'zero_of_eight_case':row['pair_id']==zero})
 zero_rows=[r for r in result if r['zero_of_eight_case']]
 assert len(result)==13 and len(zero_rows)==8 and all(r['answer_exactly_unchanged'] for r in zero_rows)
 final={'schema':'fresh-residual-delivery-audit/1','scope':'Retained API-request and hook-output inspection; no new model calls or runtime changes.','remaining_failures':13,'counterevidence_delivered':13,'final_false_eligibility_extracted':13,'zero_case_source_pair_id':zero,'zero_case_counterevidence_delivered':8,'zero_case_final_false_lists_extracted':8,'zero_case_exactly_unchanged_answers':8,'source_record_position_not_claim_list_position':True,'interpretation':'Extraction and delivery succeeded. No factual correction followed in the zero case. This does not establish model understanding, attention, rationalization, persuasion saturation or zero causal effect for all review wording. Ordinal reference ambiguity and the repeat-unchanged sentence were not separately tested.','results':result}
 (HERE/'residual-diagnosis.json').write_text(json.dumps(final,indent=2)+'\n')
 dest=ROOT/'warden/docs/data/launchgate-fresh-rechecks-2026-10-26';(dest/'residual-diagnosis.json').write_text(json.dumps(final,indent=2)+'\n')
 manifest={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir()) if p.is_file() and p.name!='manifest.json'}
 (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({k:v for k,v in final.items() if k!='results'}))
if __name__=='__main__':main()
