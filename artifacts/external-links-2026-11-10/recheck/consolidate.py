"""Build a deduplicated reference register from saved public evidence, offline."""
import csv
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

ROOT = Path(__file__).resolve().parent
SESSION = ROOT.parent

def read(path): return json.loads(path.read_text())

def main():
    sources=read(ROOT/'source-index.json');targets=read(ROOT/'target-index.json')
    verified=[]
    for kind, rows in [('source',sources),('target',targets)]:
        for row in rows:
            if not row.get('file'): continue
            body=(ROOT/row['file']).read_bytes()
            assert len(body)==row['captured_bytes'], row['file']
            assert hashlib.sha256(body).hexdigest()==row['sha256'], row['file']
            verified.append({'kind':kind,'file':row['file'],'bytes':len(body),'truncated':row['truncated'],'sha256_valid':True})
    bytarget={r['requested_url']:r for r in targets}
    bysource={r['requested_url']:r for r in sources}
    eco=read(SESSION/'ecosystem/findings.json')
    ecoby={r['source_url']:r for r in eco['records']}
    technical=read(SESSION/'technical/findings.json')['findings']
    techby={r['source_url']:r for r in technical}
    register={}
    def add(source,target,kind,branch,classification,rel='',file=''):
        key=(source,target,kind)
        record=register.setdefault(key,{'source_url':source,'target_url':target,'evidence_kind':kind,'branches':set(),'classifications':set(),'rel_values':set(),'evidence_files':set()})
        record['branches'].add(branch);record['classifications'].add(classification)
        if rel: record['rel_values'].add(rel)
        if file: record['evidence_files'].add(file)
    for r in read(ROOT/'backlinks.json'):
        classification='external_catalogue_or_monitor'
        if r['source_name'] in ('gemivo','teckdeck','webpulse'): classification='redistribution_of_own_article'
        if r['source_name']=='hlido': classification='historical_external_review'
        add(r['source_url'],r['target_url'],'html_a_href','recheck',classification,r['rel'],'recheck/'+r['source_file'])
    for r in read(SESSION/'ecosystem/source-target-links.json'):
        source=ecoby.get(r['source_url'],{})
        add(r['source_url'],r['target_url'],r['evidence_kind'],'ecosystem',source.get('classification','external_reference'),r.get('rel',''),'ecosystem/'+source.get('evidence_body',''))
    for r in technical:
        for t in r.get('targets',[]):
            if not str(t.get('target','')).startswith('https://'): continue
            kind={'html_href':'html_a_href'}.get(t['kind'],t['kind'])
            add(r['source_url'],t['target'],kind,'technical',r['classification'],file=';'.join('technical/'+f for f in r.get('evidence_files',[])))
    rows=[]
    for r in register.values():
        r={k:('; '.join(sorted(v)) if isinstance(v,set) else v) for k,v in r.items()}
        check=bytarget.get(urldefrag(r['target_url']).url,{})
        r['target_get_status']=check.get('status','not_requested_in_root_target_batch')
        r['source_status']=bysource.get(r['source_url'],{}).get('status',ecoby.get(r['source_url'],{}).get('source_status',techby.get(r['source_url'],{}).get('source_http_status','see_branch_index')))
        r['checked_at_utc']=bysource.get(r['source_url'],{}).get('observed_at_utc',ecoby.get(r['source_url'],{}).get('checked_at_utc',techby.get(r['source_url'],{}).get('checked_at_utc','see_branch_index')))
        r['source_identity_scope']='publisher_owned_on_external_host' if any(s in r['source_url'] for s in ('huggingface.co/datasets/alexar76/','github.com/alexar76/','dev.to/alexar76/')) else 'external_surface_operator_independence_not_attested'
        rows.append(r)
    rows.sort(key=lambda r:(r['source_url'],r['target_url'],r['evidence_kind']))
    (SESSION/'reference-register.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    with (SESSION/'reference-register.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    html=[r for r in rows if r['evidence_kind']=='html_a_href' and r['source_identity_scope'].startswith('external_surface')]
    summary={
      'root_sources':len(sources),'root_source_200':sum(x.get('status')==200 for x in sources),'root_source_403':sum(x.get('status')==403 for x in sources),
      'root_pages_with_owned_html_href':sum(x.get('status')==200 and bool(x.get('owned_links')) for x in sources),
      'root_distinct_linking_domains':len({urlsplit(x['requested_url']).hostname.removeprefix('www.') for x in sources if x.get('status')==200 and x.get('owned_links')}),
      'root_unique_source_target':len({(r['source_url'],r['target_url']) for r in read(ROOT/'backlinks.json')}),
      'root_target_gets':len(targets),'root_target_200':sum(x.get('status')==200 for x in targets),'root_target_405_post_only_a2a':sum(x.get('status')==405 and x['requested_url']=='https://modelmarket.dev/a2a' for x in targets),
      'root_target_errors':sum('error' in x for x in targets),'root_target_truncated_captures':sum(x['truncated'] for x in targets),
      'reference_register_records':len(rows),'register_external_html_source_target_records':len(html),'register_external_html_source_pages':len({x['source_url'] for x in html}),
      'root_capture_integrity':{'checked':len(verified),'valid':True},
      'limits':['Register contains references, not a count of users or independent operators.','Only the root target batch was individually GET-checked; other rows retain branch evidence.','Root target captures are bounded at 120000 bytes; HTTP reachability does not verify full content or behavior.','Source body caps are 6000000 bytes; all 23 source captures were complete.','Markdown links and metadata URL references are retained separately from HTML anchors.']}
    (ROOT/'capture-integrity.json').write_text(json.dumps({'summary':summary['root_capture_integrity'],'bodies':verified},indent=2)+'\n')
    (SESSION/'review-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
