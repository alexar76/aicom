import concurrent.futures
from datetime import datetime,timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request
import urllib.error

ROOT=Path(__file__).parent
class Extract(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.scripts=[];self.parts=[];self.forms=[];self.inputs=[]
 def handle_starttag(self,t,a):
  x=dict(a)
  if t=='a' and x.get('href'):self.links.append(x['href'])
  if t=='script' and x.get('src'):self.scripts.append(x['src'])
  if t=='form':self.forms.append(x)
  if t=='input':self.inputs.append(x)
 def handle_data(self,s):self.parts.append(s)

def read(pair):
 name,url=pair;r={'key':name,'url':url,'method':'GET','retrieved_at':datetime.now(timezone.utc).isoformat()}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 AICOM public-source research'})
  with urllib.request.urlopen(req,timeout=25) as response:b=response.read(10*1024*1024);r.update(status=response.status,final_url=response.url,content_type=response.headers.get_content_type(),bytes=len(b),sha256=sha256(b).hexdigest())
  s=b.decode(errors='replace');p=Extract();p.feed(s);txt=' '.join(' '.join(p.parts).split())
  r.update(title=re.findall(r'<title[^>]*>(.*?)</title>',s,re.S|re.I)[:1],scripts=p.scripts,forms=p.forms,inputs=p.inputs,
   exact_links=[x for x in p.links if any(k in x.lower() for k in ['alexar76','modelmarket','650555','ftf1508544'])],
   identifiers={k:len(re.findall(re.escape(k),s,re.I)) for k in ['alexar76','modelmarket.dev','Пантеон','Вес ответа','Комментарии','Отзывы','Читател','MCP','api/']},
   contexts=[txt[max(0,m.start()-100):m.end()+200] for term in ['alexar76','modelmarket.dev','Пантеон','Вес ответа','Отзывы','Комментарии','Это произведение','reader'] for m in list(re.finditer(re.escape(term),txt,re.I))[:3]])
  if 'javascript' in r['content_type']:
   r['observed_endpoints']=sorted(set(re.findall(r'.{0,100}(?:/api/|https://[^\s\"\']+).{0,160}',s)))[:80]
 except urllib.error.HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 (ROOT/(name+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 return r

if __name__=='__main__':
 pairs=[('fanfics-weight','https://fanfics.me/ftf1508544'),('mcp-fr-shell','https://mcp-servers.fr/server/server%20implementations-alexar76-argus'),('awesome-viz','https://awesome.ecosyste.ms/projects?keyword=3d-visualization'),('awesome-home','https://awesome.ecosyste.ms/')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(read,pairs))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(rows,ensure_ascii=False,indent=2))
