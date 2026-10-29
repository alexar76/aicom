#!/usr/bin/env python3
"""Read-only artifact accounting audit. No imports of the study implementation."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
import hashlib,json
from pathlib import Path

PROFILES={'none','note','note_stop','candidate_note','candidate_note_stop'}
FIELDS=('fixture_id','repeat','defense','arm','model')
def sha(data):return hashlib.sha256(data).hexdigest()
def compact(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--write',type=Path,required=True)
    args=parser.parse_args();out=args.out
    checks=0
    def check(condition,label):
        nonlocal checks
        if not condition:raise AssertionError(label)
        checks+=1
    fixtures={x['id']:x for x in json.loads(args.fixtures.read_text())['fixtures']}
    config=json.loads((out/'relay/budget-config.json').read_text())
    check(config['budget_nanousd']==1_000_000_000,'fixed USD 1 ceiling')
    check(config['reservation_nanousd']==10_000_000,'fixed per-call reservation')
    events=[json.loads(x) for x in (out/'relay/usage.jsonl').read_text().splitlines()]
    reserved={};completed={};held=0;max_held=0;tokens=Counter();peak_cost=0;invoice_estimate_nano=0
    for e in events:
        rid=e['request_id']
        if e['event']=='reserved':
            check(rid not in reserved,'unique paid request identity')
            check(e['attempt_number']==len(reserved)+1,'contiguous global attempts')
            check(e['reserved_nanousd']==10_000_000,'durable full reservation')
            reserved[rid]=e;held+=10_000_000
        elif e['event']=='completed':
            check(rid in reserved and rid not in completed,'one completion per reservation')
            completed[rid]=e
            if e['status']=='ok':
                u=e['usage'];fresh=u['prompt_tokens']-u.get('prompt_cache_hit_tokens',0)
                cached=u.get('prompt_cache_hit_tokens',0);output=u['completion_tokens']
                cost=fresh*300+cached*6+output*1200
                check(cost==e['charged_upper_nanousd'],'independently recomputed peak settlement')
                check(e['actual_model']=='deepseek-flash','expected provider model alias')
                tokens.update({'input':u['prompt_tokens'],'cached_input':cached,'output':output})
                timestamp=datetime.fromisoformat(e['started_at'])
                peak=timestamp.weekday()<5 and (1<=timestamp.hour<4 or 6<=timestamp.hour<10)
                # No Chinese-holiday inference is needed for this Sunday study.
                invoice_estimate_nano+=cost if peak else cost//2
                peak_cost+=cost
            else:
                cost=10_000_000
                check(e['charged_upper_nanousd']==cost,'unknown/error costs never refunded')
            held+=cost-10_000_000
        check(0<=held<=1_000_000_000,'dollar ceiling held at every ledger event')
        check(e['held_upper_nanousd_after']==held,'ledger balance matches independent accounting')
        max_held=max(max_held,held)
    check(len(reserved)<=1100,'hard global attempt cap')
    requests={};responses={}
    for path in (out/'relay/req').glob('*.json'):
        rid=path.stem;raw=path.read_bytes();requests[rid]=json.loads(raw)
        check(sha(raw)==reserved[rid]['request_sha256'],'request body bound to reservation')
        response=json.loads((out/'relay/resp'/path.name).read_text());responses[rid]=response
        check(response['metadata']['request_sha256']==sha(raw),'response bound to request body')
        check(requests[rid]['max_tokens']<=700,'bounded output')
    all_rows=[];phase_summary={};seen_ids=[]
    for phase,expected in [('smoke',5),('control',30),('main',720)]:
        base=out/phase;plan=json.loads((base/'schedule.json').read_text())
        rows=[json.loads(x) for x in (base/'runs.jsonl').read_text().splitlines()]
        key=lambda r:tuple(r[f] for f in FIELDS)
        check(len(rows)==len(plan['attempts'])==expected,'planned phase denominator '+phase)
        check(len({key(r) for r in rows})==expected,'unique phase slots '+phase)
        check({key(r) for r in rows}=={key(r) for r in plan['attempts']},'no extra or missing phase slots '+phase)
        counts=Counter()
        for r in rows:
            check(r['defense'] in PROFILES,'known profile')
            for prefix in ('','initial_'):
                answer=r[prefix+'answer']
                check(sha(answer.encode())==r[prefix+'answer_sha256'],'complete answer digest')
            check(r['answer_capture']['truncated_by_storage'] is False,'full retained final answer')
            check(r['answer_capture']['characters']==len(r['answer']),'retained answer length')
            check(r['continuation_calls'] in (0,1),'at most one continuation')
            check(r['stop_triggered']==bool(r['continuation_calls']),'continuation exactly when Stop requests it')
            ids=list(r['request_ids'].values());seen_ids.extend(ids)
            check(len(ids)==1+r['continuation_calls'],'initial plus bounded continuation count')
            for rid in ids:
                check(rid in reserved and rid in completed,'model call appears in durable ledger')
                intent=json.loads((base/'request-intents'/(rid+'.json')).read_text())
                check(intent['body_sha256']==sha(compact(requests[rid]).encode()),'request intent matches actual body')
                check(intent['plan_sha256']==sha(compact(plan).encode()),'request intent binds the frozen plan')
            for response in r['api_responses']:
                check(response==responses[response['metadata']['request_id']],'stored provider response matches relay artifact')
            if r['defense']=='none':
                check(not r['hooks'],'unguarded profile never invokes a hook')
            else:
                artifact=r['hooks'][0]['artifact']
                expected_version='0.22.0' if r['defense'].startswith('candidate_') else '0.21.0'
                check(artifact['packageVersion']==expected_version,'correct runtime routed to treatment')
                if expected_version=='0.22.0':
                    check(artifact['sourceHashes']==json.loads((out/'candidate-runtime.json').read_text())['files'],'candidate full module identity')
            counts.update({'samples':1,'continuations':r['continuation_calls'],'errors':int(r['status']!='ok')})
        phase_summary[phase]=dict(counts);all_rows.extend(rows)
    check(len(seen_ids)==len(set(seen_ids))==len(reserved),'no duplicate paid identity or unassigned request')
    check(set(seen_ids)==set(reserved)==set(completed),'complete global request accounting')
    matched=defaultdict(list)
    for r in all_rows:
        if r['phase']=='main':matched[(r['fixture_id'],r['repeat'])].append(r)
    check(len(matched)==48,'48 complete repeated fixture blocks')
    for (fid,repeat),rows in matched.items():
        check(len(rows)==15,'five profiles times three inputs in matched block')
        check(len({r['records_sha256'] for r in rows})==1,'identical ordered records across treatments')
        check(len({r['user_request_sha256'] for r in rows})==1,'identical real-user request across treatments')
        for r in rows:
            check(r['tool_result']['note']==fixtures[fid][r['arm']+'_note'],'unchanged frozen note')
    result={'checksPassed':checks,'paidAttempts':len(reserved),'phaseSummary':phase_summary,
            'tokens':dict(tokens),'peakPriceSettlementUSD':peak_cost/1e9,
            'estimatedPublishedTariffUSD':invoice_estimate_nano/1e9,
            'maxIncludingPendingReservationsUSD':max_held/1e9,'finalUpperAccountingUSD':held/1e9,
            'scope':'Independent artifact accounting, not independent human semantic review or a provider invoice.'}
    args.write.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
