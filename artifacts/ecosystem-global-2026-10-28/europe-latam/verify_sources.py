"""Public GET verification for selected sources; no auth, submissions or tool calls."""
import concurrent.futures
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

HERE = Path(__file__).parent
URLS = [
 ('radyz','https://radyz.cz/rychle-zpravy/histor-otevrel-dataset-zmen-nastroju-mcp-nikoli-seznam-skodlivych-serveru/'),
 ('legit-histor','https://legit.show/s/histor-modelmarket-dev'),
 ('agent-tools','https://agent-tools.org/p/modelmarket'),
 ('mcp-fr-argus','https://mcp-servers.fr/server/server%20implementations-alexar76-argus'),
 ('forge-warden-es','https://forgeregistry.com/es/registry/%40aimarket%2Fwarden'),
 ('turkish-mirror','https://ccn.web.tr/web-api/iframe-proxy?url=http%3A%2F%2Fgithub.com%2Ftopics%2Ftransaction-signing'),
]
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.text=[];self.title=[];self.in_title=False;self.ignore=0;self.links=[];self.meta=[]
 def handle_starttag(self,t,a):
  v=dict(a)
  if t in ('script','style'):self.ignore+=1
  if t=='title':self.in_title=True
  if t=='a' and v.get('href') and any(x in v['href'] for x in ['modelmarket','alexar76','github','histor']):self.links.append(v['href'])
  if t=='meta' and v.get('content') and any(x in (v.get('property','')+' '+v.get('name','')) for x in ['published','modified']):self.meta.append(v)
 def handle_endtag(self,t):
  if t in ('script','style'):self.ignore=max(0,self.ignore-1)
  if t=='title':self.in_title=False
 def handle_data(self,s):
  if self.in_title:self.title.append(s)
  if not self.ignore:self.text.append(s)
def get(pair):
 key,url=pair;result={'key':key,'url':url,'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'method':'GET'}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; public mention verification)'})
  with urllib.request.urlopen(req,timeout=25) as res:
   body=res.read();result.update(status=res.status,final_url=res.url,content_type=res.headers.get_content_type(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
  p=Parser();p.feed(body.decode(errors='replace'));text=re.sub(r'\s+',' ',' '.join(p.text));result.update(title=' '.join(p.title),links=sorted(set(p.links)),metadata=p.meta[:10],identifiers={x:bool(re.search(re.escape(x),text,re.I)) for x in ['HISTOR','WARDEN','modelmarket.dev','alexar76','ARGUS','escrow-signer']})
  contexts=[]
  for marker in ['HISTOR','modelmarket.dev','alexar76','73/100','Privacy','Performance','FADING','0.21.0']:
   match=re.search(re.escape(marker),text,re.I)
   if match:contexts.append(text[max(0,match.start()-70):match.end()+160])
  result['short_contexts']=[' '.join(contexts[0].split()[:20])] if contexts else []
 except urllib.error.HTTPError as e:result.update(status=e.code,error=str(e))
 except Exception as e:result.update(status=None,error=str(e))
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(get,URLS))
(HERE/'http-index.json').write_text(json.dumps({'records':records},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(records,ensure_ascii=False,indent=2))
