from pathlib import Path
from collections import Counter
import hashlib,json
ROOT=Path(__file__).parent
rows=[]
for name in ['http-index.json','source-http-index.json','more-http-index.json','history-http-index.json']:
    rows+=json.loads((ROOT/name).read_text())
for row in rows:
    data=(ROOT/row['file']).read_bytes()
    assert len(data)==row['bytes'],row['key']
    assert hashlib.sha256(data).hexdigest()==row['sha256'],row['key']
assert (ROOT/'old-seller-funding.raw').read_bytes()==(ROOT/'src--seller-funding.js.raw').read_bytes()
analysis=json.loads((ROOT/'analysis.json').read_text())
assert len(analysis['live_observation']['paid_routes'])==8
assert all(r['executeViaCallableNow'] is False for r in analysis['live_observation']['paid_routes'])
assert analysis['synthetic_cases']['one_router_purchase_zero_self_funding']['funded_calls_deducted']==0
assert analysis['synthetic_cases']['one_router_purchase_zero_self_funding']['reason']=='settlement_self_funded'
out={'captures':len(rows),'unique_urls':len({r['url'] for r in rows}),
     'statuses':dict(Counter(str(r.get('status')) for r in rows)),
     'hashes_verified':len(rows),'funding_source_unchanged':True,
     'paid_routes_false':8,'synthetic_counterexample_passed':True}
q=json.loads((ROOT/'quotes/summary.json').read_text())
assert q['requests']==8 and q['method']=='HEAD' and q['all_checks_pass']
for row in q['rows']:
    data=(ROOT/'quotes'/row['file']).read_bytes()
    assert len(data)==row['bytes']
    assert hashlib.sha256(data).hexdigest()==row['sha256']
    assert row['status']==402 and all(row['checks'].values())
out['head_quotes_verified']=8
out['head_quote_checks_all_pass']=True
(ROOT/'verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
