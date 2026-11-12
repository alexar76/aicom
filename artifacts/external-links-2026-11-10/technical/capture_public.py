"""Bounded unauthenticated GET evidence capture; no remote code execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json, re

ROOT = Path(__file__).resolve().parent
URLS = {
 'rugsnare-readme':'https://raw.githubusercontent.com/Paraphern/rugsnare/main/README.md',
 'heldfast-readme':'https://raw.githubusercontent.com/rufat325/heldfast/main/README.md',
 'agentavow-readme':'https://raw.githubusercontent.com/AgentAvow/AgentAvow/main/README.md',
 'scraperwatch':'https://scraperwatch.com/mcp-changes',
 'crawlcheck-spec':'https://crawlcheck.io/spec/mcp-lockfile',
 'crawlcheck-fixture':'https://raw.githubusercontent.com/emmanuelorta/crawlcheck-core/main/sdk/test/fixtures/continuity.json',
 'histor-crawlcheck':'https://histor.modelmarket.dev/api/v1/servers?q=io.github.emmanuelorta/crawlcheck',
 'registry-issue':'https://api.github.com/repos/modelcontextprotocol/registry/issues/82',
 'registry-comments':'https://api.github.com/repos/modelcontextprotocol/registry/issues/82/comments?per_page=100',
 'owasp-issue':'https://api.github.com/repos/OWASP/secure-agent-playbook/issues/33',
 'owasp-comments':'https://api.github.com/repos/OWASP/secure-agent-playbook/issues/33/comments?per_page=100',
 'acs-issue':'https://api.github.com/repos/GenAI-Security-Project/agent-control-standard/issues/38',
 'acs-comments':'https://api.github.com/repos/GenAI-Security-Project/agent-control-standard/issues/38/comments?per_page=100',
 'agentavow-issue':'https://api.github.com/repos/AgentAvow/AgentAvow/issues/240',
 'agentavow-comments':'https://api.github.com/repos/AgentAvow/AgentAvow/issues/240/comments?per_page=100',
 'pr14':'https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14',
 'skills-readme':'https://raw.githubusercontent.com/basitalisandhu/agent-skills-state-2026/main/README.md',
 'hf-dataset':'https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions',
 'openalex':'https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760',
 'warden-house-check':'https://theagentforge.io/api/v1/check?id=npm%3A%40aimarket%2Fwarden',
 'histor-house-check':'https://theagentforge.io/api/v1/check?id=github.com%2Falexar76%2Fhistor',
}

class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   d=dict(attrs)
   if d.get('href'):self.links.append(d['href'])

def relevant(u):return bool(re.search(r'(alexar76|modelmarket\.dev|2351275[9]|23512760)',u,re.I))
def read(item):
 key,url=item; meta={'key':key,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'AICOM external-link audit/1.0','Accept':'application/json,text/html,text/plain'}),timeout=35) as response:
   data=response.read(5000001)
   meta.update(status=response.status,final_url=response.url,content_type=response.headers.get('content-type'),link_header=response.headers.get('link'))
 except HTTPError as e:
  data=e.read(5000001);meta.update(status=e.code,final_url=e.url,error=str(e),location=e.headers.get('location'))
 except Exception as e:
  meta.update(status=None,error=str(e));return meta
 meta.update(bytes=len(data),sha256=sha256(data).hexdigest(),body_file=key+'.raw',truncated=len(data)>5000000)
 (ROOT/(key+'.raw')).write_bytes(data)
 s=data.decode(errors='replace'); p=Links()
 try:p.feed(s)
 except Exception:pass
 meta['ecosystem_hrefs']=[u for u in dict.fromkeys(p.links) if relevant(u)]
 meta['ecosystem_markdown_urls']=[u.rstrip('.,;') for u in dict.fromkeys(re.findall(r'https?://[^\s<>"\)\]]+',s)) if relevant(u)]
 return meta

if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(read,URLS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(rows,ensure_ascii=False,indent=2))
