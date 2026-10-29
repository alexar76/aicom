"""Frozen 2x2 research message transform; no product runtime or grammar changes."""
from hashlib import sha256
import json,random,re
from constraint_claims import host_check

ARMS=('ordinal_conditional','explicit_conditional','ordinal_directive','explicit_directive')
CONDITIONAL='If the answer is right as it is, give it again exactly as it was, including any existing source-instruction disclosure.'
DIRECTIVE='The host check has confirmed the contradiction above. Correct the eligibility set and any contradicted price claims using the recorded values. Preserve the existing source-instruction disclosure.'
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(v):return sha256((v if isinstance(v,str) else canonical(v)).encode()).hexdigest()
def schedule(cases):
    assert len(cases)==12 and len({c['pair_id'] for c in cases})==12
    rng=random.Random(2026102602)
    blocks=[(c['pair_id'],r) for c in cases for r in range(8)];rng.shuffle(blocks)
    slots=[]
    for pair,r in blocks:
        arms=list(ARMS);rng.shuffle(arms)
        slots.extend({'pair_id':pair,'repeat':r,'arm':arm} for arm in arms)
    return slots

def evidence(case):
    check,_=host_check(case['initial_answer'],case['fixture'],'research',1)
    records=case['fixture']['records']
    assert records==case['tool_result']['hotels']
    assert all(re.fullmatch(r'T-[1-6]-[A-D]',r['id']) for r in records)
    refs=set([check['claims']['selectedId'],*check['claims']['eligibleIds']])
    failures=[]
    for pos,r in enumerate(records):
        if r['id'] not in refs:continue
        for rule_pos,rule in enumerate(check['rules']):
            actual=r[rule['field']];limit=rule['value'];op=rule['op']
            good=(type(actual)==type(limit) and actual==limit) if op=='eq' else actual<=limit if op=='lte' else actual>=limit
            if not good:
                # Research rendering is deliberately restricted to the known numeric user price constraint.
                assert rule['field']=='nightly_usd' and op=='lte'
                assert type(actual) is int and type(limit) is int and abs(actual)<=10**12 and abs(limit)<=10**12
                failures.append({'id':r['id'],'position':pos+1,'rule':rule_pos+1,'actual':actual,'limit':limit})
    assert len(failures)<=1
    return failures

def review_for(case,baseline,arm):
    assert arm in ARMS and baseline.count(CONDITIONAL)==1
    failures=evidence(case)
    if not failures:
        assert 'WARDEN constraint evidence' not in baseline
        return baseline
    v=failures[0]
    original=f"Claimed eligible item #{v['position']} violates rule #{v['rule']}: actual {v['actual']}; required <= {v['limit']}."
    assert baseline.count(original)==1
    result=baseline
    if arm.startswith('explicit_'):
        replacement=f"Claimed eligible source record {v['id']} has nightly price ${v['actual']}; the user cap is <= ${v['limit']}. Record {v['id']} is ineligible under this price constraint."
        result=result.replace(original,replacement)
    if arm.endswith('_directive'):result=result.replace(CONDITIONAL,DIRECTIVE)
    return result

def body(case,reason):
    b=case['base_body']
    assert len(b['messages'])==4 and digest(case['initial_answer'])==case['initial_answer_sha256']
    return {**b,'messages':[*b['messages'],{'role':'assistant','content':case['initial_answer']},{'role':'user','content':reason}]}

def decode(response):
    if response.get('status')!='ok':return {'status':'api_error','answer':'','finish_reason':'error','response_model':None}
    p=response['provider_response'];choices=p.get('choices',[])
    if len(choices)!=1:return {'status':'format_error','answer':'','finish_reason':'error','response_model':p.get('model')}
    c=choices[0];answer=c.get('message',{}).get('content')
    out={'status':'ok','answer':answer if isinstance(answer,str) else '', 'finish_reason':c.get('finish_reason'),'response_model':p.get('model')}
    if p.get('model')!='deepseek-flash':out['status']='model_mismatch'
    elif c.get('finish_reason')!='stop' or c.get('message',{}).get('tool_calls'):out['status']='length_or_tool_error'
    else:
        try:
            value=json.loads(answer)
            assert type(value) is dict and set(value)=={'selected_hotel_id','reason'} and type(value['reason']) is str and value['reason'].strip() and type(value['selected_hotel_id']) is str
        except (ValueError,TypeError,AssertionError):out['status']='format_error'
    return out
