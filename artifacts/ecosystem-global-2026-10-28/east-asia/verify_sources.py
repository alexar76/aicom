"""Public read-only page verification; retain metadata and bounded excerpts only."""
import concurrent.futures
import datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import urllib.error

ROOT=Path(__file__).parent
TARGETS=[
 ('hubwiz','https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/'),
 ('qiita-author','https://qiita.com/qwezzy721/items/b71aaeaae84fcb360fe6'),
 ('ai-outline','https://ai-outline.com/2026/10/21/'),
 ('billionare-histor','https://billionare.me/items/jb1aevxo65vp3w52bi7vy1kh4'),
 ('bittide','https://bittide.aicompass.dev/article/bb82d6c4-9c7b-4cb6-92ed-0afcd6fa0e7f?locale=zh'),
 ('claudeskills-zh-hant','https://claudeskills.info/zh-hant/mcp/alexar76/aimarket-mcp/'),
 ('papers-ananclaw','https://papers.ananclaw.com/repos?category=ai&form=tutorial&primary=engineering'),
 ('zenn-azure-candidate','https://zenn.dev/kazu_aiengineer/articles/azure-mcp-server-3-ga'),
 ('note-aimarket-candidate','https://note.com/magic_otter8503/n/nfe572e964b88?hl=ko'),
 ('github-cn-mirror','https://github.itlym.cn/topics/aicom'),
]
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[];self.title=[];self.in_title=False;self.links=[];self.meta={}
 def handle_starttag(self,t,a):
  a=dict(a)
  if t in ['script','style']:self.skip+=1
  if t=='title':self.in_title=True
  if t=='a' and a.get('href'):self.links.append(a['href'])
  if t=='meta' and a.get('content'):self.meta[a.get('property') or a.get('name','')]=a['content']
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
  if t=='title':self.in_title=False
 def handle_data(self,s):
  if self.in_title:self.title.append(s)
  if not self.skip:self.parts.append(s)
def fetch(pair):
 key,url=pair
 r={'key':key,'url':url,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET'}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 AICOM public source verification'}),timeout=30) as res:
   b=res.read();r.update(status=res.status,final_url=res.url,content_type=res.headers.get_content_type(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  text=b.decode('utf-8',errors='replace');p=Parser();p.feed(text);plain=re.sub(r'\s+',' ',' '.join(p.parts));r['title']=''.join(p.title)
  r['markers']={m:len(re.findall(re.escape(m),text,re.I)) for m in ['alexar76','modelmarket.dev','HISTOR','WARDEN','attestedmemory.net','pingblip','independentai.network']}
  r['ecosystem_links']=[u for u in p.links if any(k in urllib.parse.unquote(u).lower() for k in ['alexar76','modelmarket.dev','attestedmemory.net','independentai.network','pingblip.com'])][:25]
  r['excerpts']=[]
  for m in re.finditer(r'alexar76|modelmarket\.dev|HISTOR|WARDEN|attestedmemory\.net|pingblip',plain,re.I):
   snippet=plain[max(0,m.start()-100):m.end()+210]
   if snippet not in r['excerpts']:r['excerpts'].append(snippet)
   if len(r['excerpts'])>=4:break
  r['article_meta']={k:v for k,v in p.meta.items() if k in ['article:published_time','article:modified_time','author','og:title','og:url']}
  r['datePublished_fields']=re.findall(r'"datePublished"\s*:\s*"([^"]+)"',text)[:6]
 except urllib.error.HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(fetch,TARGETS))
(ROOT/'http-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
for r in records:print(json.dumps(r,ensure_ascii=False))
