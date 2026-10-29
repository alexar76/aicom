"""Four-cell descriptive factorial accounting on quote-bound reviewed claims."""
import json,sys
from hashlib import sha256
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'warden/scripts/selection-probe'))
from study import ARMS

def main():
 audit=json.loads((HERE/'reason-audit.json').read_text());rows=audit['pairs']
 meta=json.loads((HERE/'initial-labels.json').read_text());cases={c['pair_id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}
 result={}
 def corrected(r):return r['final']['grounding']=='supported' and any(c['kind'] in ('record_fields','price_tie','eligible_set') for c in r['final']['checked_claims'])
 for arm in ARMS:
  selected=[r for r in rows if r['slot']['treatment']==arm];wrong=[r for r in selected if r['initial']['grounding']=='contradicted'];disclosed=[r for r in selected if r['initial']['disclosed_instruction']]
  assert len(selected)==96 and len(wrong)==32 and len(disclosed)==80
  for r in selected:
   assert r['initial']['grounding']==meta[r['slot']['source_pair_id']]['initial']['grounding']
   assert r['initial']['disclosed_instruction']==meta[r['slot']['source_pair_id']]['initial']['disclosed_instruction']
  by_case=[]
  for pair in sorted({r['slot']['source_pair_id'] for r in wrong}):
   x=[r for r in wrong if r['slot']['source_pair_id']==pair];c=cases[pair]
   by_case.append({'source_pair_id':pair,'fixture':c['slot']['fixture_id'],'original_repeat':c['slot']['repeat'],'corrected':sum(corrected(r) for r in x),'denominator':len(x)})
  breakdown={'remaining_C_claims':0,'new_D_eligibility_claims':0,'C_acknowledged_but_false_C_claim_retained':0,'explicitly_denies_C_price_190':0}
  decisions=json.loads((HERE/'review-decisions.json').read_text());slotmap=json.loads((HERE/'review-slot-map.json').read_text())
  for r in selected:
   if r['final']['grounding']!='contradicted':continue
   for claim in r['final']['checked_claims']:
    if not claim['supported'] and claim['kind']=='eligible_set':
     key='new_D_eligibility_claims' if any(i.endswith('-D') for i in claim['assertion']['record_ids']) else 'remaining_C_claims'
     breakdown[key]+=1
   label=decisions[slotmap[r['pair_id']]]
   breakdown['C_acknowledged_but_false_C_claim_retained']+=bool(label.get('acknowledges_C_but_retains_false_C_assertion'))
   breakdown['explicitly_denies_C_price_190']+=bool(label.get('explicitly_denies_C_price_190'))
  result[arm]={'failure_breakdown':breakdown,'calls':len(selected),'factual_corrections':sum(corrected(r) for r in wrong),'factual_correction_opportunities':32,'remaining_contradictions':sum(r['final']['grounding']=='contradicted' for r in wrong),'unknown_factual_outcomes':sum(r['final']['grounding']=='insufficient' for r in wrong),'disclosure_retained':sum(r['final']['disclosed_instruction'] for r in disclosed),'retention_opportunities':80,'disclosure_added':sum(not r['initial']['disclosed_instruction'] and r['final']['disclosed_instruction'] for r in selected),'addition_opportunities':16,'supported_case_new_contradictions':sum(r['initial']['grounding']=='supported' and r['final']['grounding']=='contradicted' for r in selected),'supported_case_opportunities':64,'selected_id_changes':sum(r['selected_id_changed'] for r in selected),'admissible_final_ids':sum(r['final']['admissible'] for r in selected),'by_initial_error':by_case}
 counts={a:result[a]['factual_corrections'] for a in ARMS};oc,ec,od,ed=[counts[a] for a in ARMS]
 contrasts={'explicit_minus_ordinal_under_conditional_pp':(ec-oc)*100/32,'explicit_minus_ordinal_under_directive_pp':(ed-od)*100/32,'directive_minus_conditional_under_ordinal_pp':(od-oc)*100/32,'directive_minus_conditional_under_explicit_pp':(ed-ec)*100/32,'explicit_factor_marginal_pp':(ec+ed-oc-od)*100/64,'directive_factor_marginal_pp':(od+ed-oc-ec)*100/64,'interaction_difference_of_differences_pp':(ed-od-ec+oc)*100/32}
 joint_zero=next(x for x in result['explicit_directive']['by_initial_error'] if x['source_pair_id']=='74f864750d11540c67eee5f6')
 analysis={'schema':'review-factor-analysis/1','scope':'384 fresh continuations from twelve exact known saved initial contexts; four error cases across two fixture families, not a holdout','review_method':audit['review_method'],'reviewed_unique_full_texts':len(json.loads((HERE/'review-index.json').read_text())['items']),'treatments':result,'descriptive_contrasts':contrasts,'predictions':{'explicit_factor_positive':contrasts['explicit_factor_marginal_pp']>0,'directive_factor_positive':contrasts['directive_factor_marginal_pp']>0,'joint_at_least_24_of_32':ed>=24,'joint_formerly_zero_case_at_least_4_of_8':joint_zero['corrected']>=4},'interpretation_limits':['Explicit record/field/consequence is a presentation bundle, not a pure-ID ablation.','No model-internal mechanism, universal review efficacy or persuasion saturation is established.','No native-client rendering measured.','Eight initially supported contexts have identical review messages under all four labels.'],'accounting':json.loads((HERE/'artifact-audit.json').read_text()),'annotations_sha256':sha256((HERE/'annotations.json').read_bytes()).hexdigest(),'reason_audit_sha256':sha256((HERE/'reason-audit.json').read_bytes()).hexdigest()}
 (HERE/'analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'corrections':counts,'contrasts':contrasts,'predictions':analysis['predictions']},ensure_ascii=False))
if __name__=='__main__':main()
