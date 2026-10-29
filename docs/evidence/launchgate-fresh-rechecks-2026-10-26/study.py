"""Frozen continuation schedule and strict response capture; no semantic keyword scoring."""
from hashlib import sha256
import json
import random

ARMS=('old','new_plain','new_facts')
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(v):return sha256((v if isinstance(v,str) else canonical(v)).encode()).hexdigest()
def schedule(cases):
    assert len(cases)==12 and len({c['pair_id'] for c in cases})==12
    rng=random.Random(20261026)
    blocks=[(c['pair_id'],r) for c in cases for r in range(8)];rng.shuffle(blocks)
    slots=[]
    for pair,r in blocks:
        arms=list(ARMS);rng.shuffle(arms)
        slots.extend({'pair_id':pair,'repeat':r,'arm':arm} for arm in arms)
    return slots

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
