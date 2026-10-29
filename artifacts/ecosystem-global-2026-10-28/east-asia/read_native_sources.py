"""Qiita public API and an observed catalog detail link; no authentication or writes."""
from datetime import datetime,timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request,urllib.parse,urllib.error

ROOT=Path(__file__).parent
records=[]
def read(url):
 r={'url':url,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'method':'GET'}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 AICOM public source verification','Accept':'application/json,text/html'}),timeout=30) as res:
   body=res.read();r.update(status=res.status,final_url=res.url,bytes=len(body),sha256=sha256(body).hexdigest(),content_type=res.headers.get_content_type(),total_count=res.headers.get('Total-Count'),link=res.headers.get('Link'))
  records.append(r);return body
 except urllib.error.HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 records.append(r)
 return None

summaries={}
for q in ['HISTOR','"modelmarket.dev"','alexar76']:
 url='https://qiita.com/api/v2/items?'+urllib.parse.urlencode({'query':q,'per_page':100,'page':1})
 body=read(url)
 if body:
  d=json.loads(body);summaries[q]=[{**{k:x.get(k) for k in ['id','title','url','created_at','updated_at','likes_count','comments_count']},'user':x.get('user',{}).get('id'),'exact_ecosystem_marker':bool(re.search(r'alexar76|modelmarket\.dev',x.get('body',''),re.I))} for x in d]
body=read('https://qiita.com/api/v2/users/qwezzy721/items?per_page=100&page=1')
own_items=[]
if body:
 d=json.loads(body);own_items=[{**{k:x.get(k) for k in ['id','title','url','created_at','updated_at','likes_count','comments_count']},'user':x.get('user',{}).get('id'),'ecosystem_linked':bool(re.search(r'alexar76|modelmarket\.dev',x.get('body',''),re.I))} for x in d]
comments=[]
ids={x['id'] for x in own_items if x['ecosystem_linked']}
ids.add('b71aaeaae84fcb360fe6')
for id_ in sorted(ids):
 body=read(f'https://qiita.com/api/v2/items/{id_}/comments')
 if body:
  d=json.loads(body);comments.append({'item_id':id_,'comments':[{'id':c.get('id'),'user':c.get('user',{}).get('id'),'created_at':c.get('created_at'),'body_excerpt':c.get('body','')[:800]} for c in d]})

class P(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[];self.links=[];self.forms=[];self.inputs=[];self.meta={}
 def handle_starttag(self,t,a):
  a=dict(a)
  if t in ['script','style']:self.skip+=1
  if t=='a' and a.get('href'):self.links.append(a['href'])
  if t=='form':self.forms.append(a)
  if t=='input':self.inputs.append(a)
  if t=='meta' and a.get('content'):self.meta[a.get('property') or a.get('name','')]=a['content']
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)
school={}
url='https://papers.ananclaw.com/repo/2680-alexar76-aimarket-school'
body=read(url)
if body:
 text=body.decode('utf-8',errors='replace');p=P();p.feed(text);plain=re.sub(r'\s+',' ',' '.join(p.parts))
 school={'url':url,'title':p.meta.get('og:title'),'links':[u for u in p.links if 'alexar76' in u or 'modelmarket.dev' in u], 'excerpts':[], 'forms':p.forms,'search_inputs':[a for a in p.inputs if a.get('name')],'meta':{k:v for k,v in p.meta.items() if k in ['article:published_time','article:modified_time','og:url','og:title']}}
 for m in re.finditer(r'alexar76|modelmarket|OpenClaw|来源|收录|更新',plain,re.I):
  snippet=plain[max(0,m.start()-80):m.end()+180]
  if snippet not in school['excerpts']:school['excerpts'].append(snippet)
  if len(school['excerpts'])>=6:break

result={'api_documentation':'https://qiita.com/api/v2/docs','scope':'Public GET; Qiita GET /api/v2/items query is documented, max per_page 100. Counts are articles, not raw substring matches.','qiita_search':summaries,'qwezzy721_items':own_items,'qiita_comments':comments,'school_detail':school,'records':records}
(ROOT/'native-api-and-school.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
