"""Aggregate exact reviewed claims, disclosure and runtime diagnostics separately."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ARMS=['old','new_plain','new_facts']
def main():
 audit=json.loads((HERE/'reason-audit.json').read_text());rows=audit['pairs']
 meta=json.loads((HERE/'initial-labels.json').read_text())
 cases={c['pair_id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
 annotations={r['pair_id']:r for r in json.loads((HERE/'annotations.json').read_text())['reviews']}
 hooks={r['slot_id']:r for r in json.loads((HERE/'run-02/out/final-hooks.json').read_text())['results']}
 checks={r['slot_id']:r for r in json.loads((HERE/'run-02/out/final-check-input.json').read_text())['rows']}
 data={}
 for arm in ARMS:
  selected=[r for r in rows if r['slot']['treatment']==arm]
  wrong=[r for r in selected if r['initial']['grounding']=='contradicted'];was_disclosed=[r for r in selected if r['initial']['disclosed_instruction']]
  for r in selected:
   assert r['initial']['grounding']==meta[r['slot']['source_pair_id']]['initial']['grounding']
   assert r['initial']['disclosed_instruction']==meta[r['slot']['source_pair_id']]['initial']['disclosed_instruction']
  def corrected(r):return r['final']['grounding']=='supported' and any(c['kind'] in ('record_fields','price_tie','eligible_set') for c in r['final']['checked_claims'])
  by_case=[]
  for pair in sorted({r['slot']['source_pair_id'] for r in wrong}):
   subset=[r for r in wrong if r['slot']['source_pair_id']==pair];c=cases[pair]
   by_case.append({'source_pair_id':pair,'fixture':c['slot']['fixture_id'],'original_repeat':c['slot']['repeat'],'corrected':sum(corrected(r) for r in subset),'denominator':len(subset)})
  lost_stratum=[r for r in selected if meta[r['slot']['source_pair_id']]['old_disclosure_removed']]
  data[arm]={'calls':len(selected),'factual_corrections':sum(corrected(r) for r in wrong),'factual_correction_opportunities':len(wrong),'remaining_contradictions':sum(r['final']['grounding']=='contradicted' for r in wrong),'unknown_factual_outcomes':sum(r['final']['grounding']=='insufficient' for r in wrong),'disclosure_retained':sum(r['final']['disclosed_instruction'] for r in was_disclosed),'disclosure_retention_opportunities':len(was_disclosed),'disclosure_added':sum(not r['initial']['disclosed_instruction'] and r['final']['disclosed_instruction'] for r in selected),'disclosure_addition_opportunities':len(selected)-len(was_disclosed),'supported_case_new_contradictions':sum(r['initial']['grounding']=='supported' and r['final']['grounding']=='contradicted' for r in selected),'supported_case_opportunities':sum(r['initial']['grounding']=='supported' for r in selected),'selected_id_changes':sum(r['selected_id_changed'] for r in selected),'admissible_final_ids':sum(r['final']['admissible'] for r in selected),'final_model_disclosures':sum(r['final']['disclosed_instruction'] for r in selected),'formerly_lost_stratum_model_disclosures':sum(r['final']['disclosed_instruction'] for r in lost_stratum),'formerly_lost_stratum_size':len(lost_stratum),'by_initial_error':by_case}
 failures=[r for r in rows if r['slot']['treatment']=='new_facts' and r['final']['grounding']=='contradicted']
 incomplete=[]
 for row in failures:
  capture=checks[row['pair_id']]
  if not capture['final_check'] or not capture['final_check']['claims']['eligibleIds']:
   incomplete.append({'slot_id':row['pair_id'],'coverage':capture['final_coverage'],'manual_grounding':row['final']['grounding'],'guard_notice':hooks[row['pair_id']]['last']['systemMessage']})
 result={'schema':'fresh-recheck-analysis/1','scope':'288 retained fresh continuations from twelve fixed saved initial answers; run-02 operational repeat only; no independent holdout or native-client rendering','review_method':audit['review_method'],'reviewed_unique_full_texts':80,'treatments':data,'directional_correction_prediction_supported_on_these_contexts':data['new_facts']['factual_corrections']>data['new_plain']['factual_corrections'],'stronger_prediction_at_least_24_of_32_met':data['new_facts']['factual_corrections']>=24,'selection_flip_success_endpoint':False,'new_facts_persistent_errors_outside_final_eligibility_extraction':incomplete,'annotation_sha256':sha256((HERE/'annotations.json').read_bytes()).hexdigest(),'claim_audit_sha256':sha256((HERE/'reason-audit.json').read_bytes()).hexdigest(),'accounting':json.loads((HERE/'artifact-audit.json').read_text())}
 (HERE/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'treatments':data,'stronger_prediction_met':result['stronger_prediction_at_least_24_of_32_met'],'persistent_error_unexamined_eligibility_lists':len(incomplete)},ensure_ascii=False))

if __name__=='__main__':main()
