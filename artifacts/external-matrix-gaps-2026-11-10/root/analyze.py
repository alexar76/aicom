"""Offline validation of the coordinated public search and recovery probes."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    captures=[]
    for f in sorted(ROOT.glob('plan-*-index.json')):
        rows=json.loads(f.read_text())
        if not isinstance(rows,list):continue
        for r in rows:
            if r.get('file'):
                b=(ROOT/r['file']).read_bytes()
                assert len(b)==r['bytes'];assert hashlib.sha256(b).hexdigest()==r['sha256'];assert not r['truncated']
            captures.append(r)
    results=[]
    for r in captures:
        if '/search/' not in r['url']:continue
        data=json.loads((ROOT/r['file']).read_text())
        assert r['status']==200
        results.append({'key':r['key'],'url':r['url'],'observed_at_utc':r['observed_at_utc'],'status':r['status'],'total_count':data['total_count'],'incomplete_results':data['incomplete_results'],'items':data['items'],'evidence':r['file'],'sha256':r['sha256']})
    assert len(results)==10
    assert all(r['total_count']==0 and r['incomplete_results'] is False for r in results)
    summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'public_get_count':len(captures),'status_counts':dict(Counter(str(r.get('status','network_error')) for r in captures)),'saved_body_hashes_valid':True,'searches':results,'recovered_previous_search_gaps':['readme-acex','readme-pulse','readme-escrow','readme-treasury'],'new_confirmed_foreign_import_api_call_or_config':0,'remaining_limits':['GitHub CORE REST probe still403/remaining0; no repeated polling.','grep.app single normal retry429; no result interpretation as zero matches.','README and commit-message search are not a complete source-code search.','HTTP Date/reset fields differ from capture clock and are retained; reset time is not proof of renewed access.']}
    (ROOT/'findings.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'capture-integrity.json').write_text(json.dumps({'all_valid':True,'bodies':[{'file':r['file'],'bytes':r['bytes'],'sha256':r['sha256']} for r in captures if r.get('file')]},indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='searches'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
