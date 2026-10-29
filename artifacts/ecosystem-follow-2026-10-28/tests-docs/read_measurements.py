"""Read public measurement pages without executing their JavaScript."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
import hashlib,json,re,urllib.request,urllib.error
class Page(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[];self.links=[];self.scripts=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ('script','style'):self.skip+=1
  if tag=='a' and a.get('href'):self.links.append(a['href'])
  if tag=='script' and a.get('src'):self.scripts.append(a['src'])
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.parts.append(data)
def read(url):
 r={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 public source research'}),timeout=25) as response:
   raw=response.read();r.update(status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  p=Page();p.feed(raw.decode('utf-8','replace'));text=' '.join(' '.join(p.parts).split())
  r['links']=[u for u in p.links if any(s in u.lower() for s in ['alexar','modelmarket','method','about','rubric','score','how','source','evidence','report','raw','api','json'])]
  r['scripts']=p.scripts;r['contexts']=[]
  for needle in ['2026-10-23','18 checks','did not','No security','protocol','96','AIMarket','aimarket-plugins','How we','scoring','Scoring','static','runtime','test','audit','evidence','Evidence','confidence']:
   for m in list(re.finditer(re.escape(needle),text))[:2]:r['contexts'].append({'needle':needle,'text':text[max(0,m.start()-100):m.start()+650]})
 except urllib.error.HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 return r
with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(read,['https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security','https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins']))
Path(__file__).with_name('measurement-pages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False)[:18000])
