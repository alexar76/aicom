"""Offline per-component scope and primary evidence checks."""
from collections import Counter
from datetime import datetime,timezone
import base64
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[2]

def read(name):return json.loads((ROOT/name).read_text())

def main():
    indexes=[]
    for f in sorted(ROOT.glob('plan-*-index.json')):indexes.extend(json.loads(f.read_text()))
    integrity=[]
    for r in indexes:
        if not r.get('file'):continue
        b=(ROOT/r['file']).read_bytes()
        assert len(b)==r['bytes'];assert hashlib.sha256(b).hexdigest()==r['sha256'];assert not r['truncated']
        integrity.append({'file':r['file'],'status':r['status'],'bytes_valid':True,'sha256_valid':True})
    graphs=[]
    for f in sorted(ROOT.glob('deps-*.raw')):
        d=json.loads(f.read_text());graphs.append({'file':f.name,**d})
        assert d['totalCount']==0
    graph_by={g['package']['name']:g for g in graphs}
    searches={f.stem:json.loads(f.read_text()) for f in ROOT.glob('search-*.raw')}
    search_summary={key:{'total_count':d.get('total_count'),'incomplete_results':d.get('incomplete_results'),'repositories':[r['full_name'] for r in d.get('items',[])]} for key,d in searches.items()}
    sg=[]
    for key in ['sourcegraph-packages','sourcegraph-origins']:
        raw=(ROOT/(key+'.raw')).read_text();events=[]
        for match in re.finditer(r'event: (\w+)\ndata: ([^\n]+)',raw):
            try:events.append((match.group(1),json.loads(match.group(2))))
            except json.JSONDecodeError:continue
        progress=[d for k,d in events if k=='progress'];last=progress[-1] if progress else {}
        sg.append({'file':key+'.raw','match_count':last.get('matchCount'),'skipped':last.get('skipped'),'complete_negative_evidence':False,'alerts':[d for k,d in events if k=='alert']})
    readme=base64.b64decode(read('helios-candidate-readme.raw')['content']).decode()
    assert '@aionbuilders/helios' in readme
    for marker in ['helios-broadcast','alexar76','modelmarket.dev','AIMarket']:assert marker.lower() not in readme.lower()
    family_specs=[
      ('symmartys',['aimarket-symmartys','aimarket-emporion','symmartys.modelmarket.dev'],['search-symmartys','search-emporion'],['aimarket-symmartys','aimarket-emporion'],['web-01-1','web-02-1','web-04-1']),
      ('helios',['helios-broadcast','alexar76/helios'],['search-helios'],['helios-broadcast'],['web-01-2','web-03-1']),
      ('dioscuri',['@alexar76/dioscuri','alexar76/dioscuri'],['search-dioscuri'],['@alexar76/dioscuri'],['web-01-3','web-03-2']),
      ('theoros',['alexar76/theoros','Agent Sovereignty Canon'],['search-theoros'],[],['web-02-3','web-03-3','web-04-3']),
      ('alien-monitor',['alexar76/alien-monitor','monitor.modelmarket.dev'],['search-alien'],[],['web-02-2','web-03-4']),
      ('signal-hunt',['aimarket-signal-hunt','hunt.modelmarket.dev'],['search-signal'],['aimarket-signal-hunt'],['web-01-4','web-02-4','web-04-2']),
      ('pantheon',['pantheon.modelmarket.dev'],['search-pantheon'],[],['web-04-4']),
      ('lottery',['lottery.modelmarket.dev','alexar76/lottery'],[],[],['web-lottery-1','web-lottery-2'])
    ]
    coverage=[]
    for family,markers,searchkeys,packages,webkeys in family_specs:
        row={'component':family,'identity_markers':markers,'local_sources':[family+'/README.md'],'web_query_ids':webkeys,'repository_queries':{k:search_summary[k] for k in searchkeys},'version_scoped_dependents':[graph_by[n] for n in packages],'new_runtime_integration_confirmed':False,'new_independent_product_review_confirmed':False,'result':'no_new_qualifying_external_use_in_bounded_returns','limits':['README and version-scoped graphs are not a search of all public/private code.','Sourcegraph streams skipped shards and do not prove absence.']}
        if family=='helios':row['candidate_resolution']={'repository':'aionbuilders/helios','classification':'unrelated_homonym','evidence':['helios-candidate-meta.raw','helios-candidate-readme.raw'],'baseline':'Repository already appeared in Oct28 search; exact primary read confirms Bun WebSocket package, no identity linkage.'}
        if family=='lottery':row['limits'].append('Web-only exact identity queries in this round; no fresh contract execution or code-index query. Search snippets of old availability are not current liveness evidence.')
        coverage.append(row)
    summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'public_get_attempts':len(indexes),'http_statuses':dict(Counter(str(r.get('status','network_error')) for r in indexes)),'saved_bodies':len(integrity),'all_hashes_and_lengths_valid':True,'family_count':len(coverage),'new_runtime_integrations_confirmed':0,'new_independent_product_reviews_confirmed':0,'dependents_scope':graphs,'sourcegraph_limits':sg,'repository_search_scope':search_summary,'scope_limit':'No HISTOR/WARDEN research in this branch. Public observations only; no foreign execution, writes, login or invocations.'}
    (ROOT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'findings.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'capture-integrity.json').write_text(json.dumps({'all_valid':True,'captures':integrity},indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['dependents_scope','sourcegraph_limits','repository_search_scope']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
