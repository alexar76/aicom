"""Eight unpaid HEAD-only quote reads. Never redirects or sends a payment."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
import base64,hashlib,json

ROOT=Path(__file__).parent
INDEX=json.loads((ROOT.parent/'index-modelmarket.raw').read_text())
ROUTES=[r for r in INDEX['tools'] if r.get('paid')]
assert len(ROUTES)==8
CANONICAL='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
PAYTO='0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a'
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch(route):
    path=route['route']
    assert path.startswith('/x402/') and '?' not in path and '..' not in path
    row={'url':'https://modelmarket.dev'+path,'method':'HEAD',
         'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
         'request_headers':{'User-Agent':'aicom-readonly-quote-check/1'},
         'request_body':False,'payment_sent':False,'redirects_followed':False}
    response=None
    try:
        request=Request(row['url'],headers=row['request_headers'],method='HEAD')
        try:response=build_opener(NoRedirect()).open(request,timeout=35)
        except HTTPError as e:response=e
        row['status']=response.code
        row['headers']={k.lower():v for k,v in response.headers.items()}
        challenge=row['headers'].get('payment-required') or row['headers'].get('x-payment-required')
        row['challenge_header_present']=bool(challenge)
        if challenge:
            assert len(challenge)<=100000
            raw=base64.b64decode(challenge+'='*(-len(challenge)%4),validate=True)
            row['challenge']=json.loads(raw)
        accepts=row.get('challenge',{}).get('accepts',[])
        expected_atomic=int(Decimal(str(route['price']))*1000000)
        row['accepts_summary']=[{
          'scheme':a.get('scheme'),'network':a.get('network'),'asset':a.get('asset'),
          'payTo':a.get('payTo'),'amount_atomic':a.get('amount',a.get('maxAmountRequired')),
          'domain_name':a.get('extra',{}).get('name'),
          'domain_version':a.get('extra',{}).get('version'),
        } for a in accepts]
        row['checks']={
          'status_402':row['status']==402,
          'allow_post':'POST' in row['headers'].get('allow',''),
          'has_accepts':bool(accepts),
          'all_accepts_exact_base_canonical_usdc':bool(accepts) and all(
             a.get('scheme')=='exact' and a.get('network')=='eip155:8453'
             and str(a.get('asset','')).lower()==CANONICAL for a in accepts),
          'all_accepts_expected_payto':bool(accepts) and all(str(a.get('payTo','')).lower()==PAYTO for a in accepts),
          'all_accepts_correct_usdc_domain':bool(accepts) and all(
             a.get('extra',{}).get('name')=='USD Coin' and a.get('extra',{}).get('version')=='2'
             for a in accepts),
          'all_amounts_match_index_price':bool(accepts) and all(
             str(a.get('amount',a.get('maxAmountRequired')))==str(expected_atomic) for a in accepts),
        }
        row['expected_index_price_usd']=str(route['price'])
        row['expected_atomic']=str(expected_atomic)
    except Exception as e:row['error']=str(e)
    finally:
        if response:response.close()
    name=path.rsplit('/',1)[-1]+'.json'
    data=(json.dumps(row,ensure_ascii=False,indent=2)+'\n').encode()
    (ROOT/name).write_bytes(data)
    return {'file':name,'url':row['url'],'method':'HEAD','status':row.get('status'),
            'retrieved_at_utc':row['retrieved_at_utc'],'bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest(),'checks':row.get('checks'),
            'accepts_summary':row.get('accepts_summary'),'error':row.get('error')}

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,ROUTES))
    out={'method':'HEAD','requests':len(rows),'payment_sent':False,
         'redirects_followed':False,'rows':rows,
         'all_checks_pass':all(r.get('checks') and all(r['checks'].values()) for r in rows),
         'scope':'Unpaid challenge readiness only. No POST/GET invoke, delivery, settlement or paid execution tested.'}
    (ROOT/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
