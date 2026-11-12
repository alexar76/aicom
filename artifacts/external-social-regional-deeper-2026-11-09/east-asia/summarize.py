"""Verify second-pass captures and summarize native empty results / false candidates."""
import collections,hashlib,json,pathlib,re
R=pathlib.Path(__file__).parent;raw=R/'raw';captures=[]
for name in ['http-index.json','followup-index.json','aeee-index.json']:
 captures+=json.loads((R/name).read_text())
for x in captures:
 if 'sha256' in x:assert hashlib.sha256((raw/(x['name']+'.raw')).read_bytes()).hexdigest()==x['sha256']
native={}
for x in captures:
 if x['name'].startswith(('qiita-','zenn-','gitee-')):native[x['name']]=json.loads((raw/(x['name']+'.raw')).read_text())
findings=[]
markers=['alexar76','modelmarket.dev','@aimarket/warden','histor-mcp-tool-definitions','MCPTox']
for name in ['fjojo-daily','nccsec-index','aeee-daily','aiproducthub-1105','i3omb-compare','aeee-reports']:
 s=(raw/(name+'.raw')).read_text();findings.append({'source':name,'exact_identity_marker_counts':{m:len(re.findall(re.escape(m),s,re.I)) for m in markers},'whole_word_histor':len(re.findall(r'\bhistor\b',s,re.I)),'capture_limit_reached':len((raw/(name+'.raw')).read_bytes())==8_000_000})
aeee=json.loads((raw/'aeee-reports.raw').read_text());summary={'date':'2026-11-09','scope':'Second deeper East Asian branch only; public read-only sources.','query_novelty':json.loads((R/'query-novelty.json').read_text()),'get_count':len(captures),'statuses':dict(collections.Counter(str(x.get('status','error')) for x in captures)),'native_results':native,'candidate_checks':findings,'aeee_index':{'reports':len(aeee['reports']),'last_updated':aeee['last_updated'],'first_date':aeee['reports'][-1].get('date'),'last_date':aeee['reports'][0].get('date')},'new_confirmed_mentions':[],'excluded':['Known SelectDataset and translated LightNow catalog cards are not new independent national use.','Korean tool text inside the own HF dataset viewer is an observed third-party payload, not a Korean article about HISTOR.','NCC response is a JS shell with a CAPTCHA library; content not read, no bypass attempted.','i3omb comparison was capped at 8MB; no full-page absence claim or regional attribution established.','AEEE public index ends before HISTOR public release; it cannot establish November absence.'],'limits':['24 literal new search strings plus one known repeated reverse-title query; semantic overlap remains possible.','Empty API query samples do not establish whole-platform absence or no private users.','No account access, CAPTCHA bypass, publishing, messages, paid calls or GitHub writes.']}
(R/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({'get_count':len(captures),'statuses':summary['statuses'],'native_empty_queries':len(native),'new_literal_queries':24,'repeated_literal_queries':1,'new_confirmed_mentions':0},indent=2))
