"""Read public citation and dataset metadata only; do not install or call dataset code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parent
urls={
 'zenodo-version':'https://zenodo.org/api/records/23512760',
 'zenodo-concept':'https://zenodo.org/api/records/23512759',
 'datacite-version':'https://api.datacite.org/dois/10.5281/zenodo.23512760',
 'datacite-concept':'https://api.datacite.org/dois/10.5281/zenodo.23512759',
 'datacite-related':'https://api.datacite.org/dois?'+urlencode({'query':'relatedIdentifiers.relatedIdentifier:"10.5281/zenodo.23512760"','page[size]':100}),
 'hf-dataset':'https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions',
 'hf-search':'https://huggingface.co/api/datasets?'+urlencode({'search':'histor-mcp-tool-definitions','full':'true','limit':100}),
 'hf-discussions':'https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions/discussions',
 'openalex-doi':'https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760',
 'semantic-scholar-doi':'https://api.semanticscholar.org/graph/v1/paper/DOI:10.5281/zenodo.23512760?fields=title,year,citationCount,citations.title,citations.url',
 'europe-pmc-doi':'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':'DOI:10.5281/zenodo.23512760','format':'json'}),
 'pr14':'https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14',
 'research-readme':'https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/readme',
}

def select(key,d):
 if key.startswith('datacite-'):
  if isinstance(d.get('data'),list):return {'meta':d.get('meta'),'items':[{'id':x.get('id'),'attributes':{k:x.get('attributes',{}).get(k) for k in ['doi','titles','relatedIdentifiers','citationCount','viewCount','downloadCount','url','published']}} for x in d['data']]}
  a=d.get('data',{}).get('attributes',{});return {k:a.get(k) for k in ['doi','titles','relatedIdentifiers','citationCount','viewCount','downloadCount','url','published','created','registered']}
 if key.startswith('zenodo-'):
  return {k:d.get(k) for k in ['id','doi','conceptdoi','created','modified','metadata','stats','links']}
 if key=='hf-dataset':
  return {k:d.get(k) for k in ['id','author','createdAt','lastModified','downloads','downloadsAllTime','likes','tags','cardData','siblings','usedBy']}
 if key=='hf-search':return [{'id':x.get('id'),'author':x.get('author'),'downloads':x.get('downloads'),'likes':x.get('likes')} for x in d]
 if key=='pr14':return {k:d.get(k) for k in ['id','html_url','state','merged','merged_at','merged_by','updated_at','comments','review_comments','merge_commit_sha']}
 if key=='research-readme':return {k:d.get(k) for k in ['html_url','sha','size','content','encoding']}
 return d

def read(pair):
 key,url=pair;r={'key':key,'url':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'method':'GET'}
 try:
  with urlopen(Request(url,headers={'User-Agent':'AICOM public citation audit/1.0','Accept':'application/json'}),timeout=30) as res:
   b=res.read();r.update(status=res.status,sha256=sha256(b).hexdigest(),bytes=len(b),final_url=res.url)
  d=json.loads(b);r['selected_metadata']=select(key,d)
 except HTTPError as e:r.update(status=e.code,error=e.read().decode(errors='replace')[:250])
 except Exception as e:r.update(status=None,error=str(e))
 (ROOT/(key+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 return r
with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(read,urls.items()))
(ROOT/'native-index.json').write_text(json.dumps({'records':[{k:v for k,v in x.items() if k!='selected_metadata'} for x in rows]},ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{'key':x['key'],'status':x.get('status'),'metadata':x.get('selected_metadata'),'error':x.get('error')} for x in rows],ensure_ascii=False,indent=2)[:33000])
