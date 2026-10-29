"""Prepare bounded historical projection inputs and one full raw transcript; no runtime tests."""
from hashlib import sha256
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'launchgate-review-factors-2026-10-26'
def main():
 audit=json.loads((OLD/'reason-audit.json').read_text())['pairs']
 rows={r['slot_id']:r for r in [json.loads(x) for x in (OLD/'run-01/out/runs.jsonl').read_text().splitlines()]}
 annotations={r['pair_id']:r for r in json.loads((OLD/'annotations.json').read_text())['reviews']}
 fixtures={r['pair_id']:r['fixture'] for r in json.loads((OLD/'scored-pairs.json').read_text())['pairs']}
 result=[]
 for row in audit:
  claims=annotations[row['pair_id']]['final']['claims']
  sets=[c['assertion']['record_ids'] for c in claims if c['kind']=='eligible_set']
  result.append({'slot_id':row['pair_id'],'fixture':fixtures[row['pair_id']],'selected_id':row['final']['selected_id'],'explicit_eligible_ids':sets[0] if sets else None,'original_answer':rows[row['pair_id']]['answer'],'reviewed_grounding':row['final']['grounding']})
 assert len(result)==384 and sum(x['reviewed_grounding']=='contradicted' for x in result)==50
 (HERE/'historical-inputs.json').write_text(json.dumps({'scope':'Post-hoc annotated structured projection, not automatic prose extraction.','cases':result},ensure_ascii=False,indent=2)+'\n')
 stubborn=[r for r in audit if r['slot']['source_pair_id']=='74f864750d11540c67eee5f6' and r['slot']['treatment']=='ordinal_directive']
 chosen=next(r for r in stubborn if annotations[r['pair_id']]['final'].get('acknowledges_C_but_retains_false_C_assertion'))
 raw=(OLD/'run-01/out/relay/req'/(chosen['pair_id']+'.json')).read_bytes();request=json.loads(raw);response=rows[chosen['pair_id']]['apiResponse']
 assert sha256(raw).hexdigest()==rows[chosen['pair_id']]['requestSha256']
 transcript={'slot_id':chosen['pair_id'],'slot':chosen['slot'],'request_sha256':sha256(raw).hexdigest(),'request':request,'response':response,'reviewed_final':chosen['final'],'interpretation':'The full answer asserts C eligible at 129 and also C excluded at 190. This is an observable inconsistent explanation, not evidence of internal reasoning or awareness.'}
 (HERE/'stubborn-transcript.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2)+'\n')
 print('Prepared 384 historical projection cases (50 contradicted) and one exact full stubborn-case transcript.')
if __name__=='__main__':main()
