import concurrent.futures, datetime, hashlib, json, re, urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser
from pathlib import Path
BASE=Path(__file__).resolve().parent
class Page(HTMLParser):
 def __init__(self): super().__init__();self.skip=0;self.text=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style'):self.skip+=1
  if tag=='a':
   href=dict(attrs).get('href','')
   if any(x in href.lower() for x in ['alexar76','modelmarket','trovark','histor','warden']):self.links.append(href)
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
 def handle_data(self,data):
  if not self.skip:self.text.append(data)
def get(url,query=None):
 row={'url':url,'method':'GET','retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 if query:row['query']=query
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public source research)'}),timeout=30) as r:
   raw=r.read();row.update(status=r.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  if '/search/issues?' in url:
   d=json.loads(raw);row.update(total_count=d.get('total_count'),incomplete_results=d.get('incomplete_results'),items=[{'url':v['html_url'],'title':v['title'],'user':v['user']['login'],'created_at':v['created_at'],'updated_at':v['updated_at'],'state':v['state'],'comments':v['comments'],'body_excerpt':(v.get('body')or'')[:1800]} for v in d.get('items',[])])
  elif 'grep.app/api' in url:row['result']=json.loads(raw)
  else:
   p=Page();p.feed(raw.decode('utf-8','replace'));plain=' '.join(' '.join(p.text).split());row['selected_links']=sorted(set(p.links));row['contexts']=[]
   for needle in ['alexar76','modelmarket.dev','warden','histor','under-read']:
    for m in list(re.finditer(re.escape(needle),plain,re.I))[:5]:row['contexts'].append({'needle':needle,'context':plain[max(0,m.start()-220):m.end()+650]})
 except urllib.error.HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=='__main__':
 queries=['"alexar76" in:body -user:alexar76 -author:alexar76','"histor-mcp-tool-definitions" in:body -user:alexar76 -author:alexar76','"alexar76/warden" in:body -user:alexar76 -author:alexar76','"@alexar76/argus3" -user:alexar76 -author:alexar76','"aimarket-agent" in:body -user:alexar76 -author:alexar76','"histor.modelmarket.dev" in:body -user:alexar76 -author:alexar76']
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  rows=list(pool.map(lambda q:get('https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':q,'per_page':100,'sort':'updated'}),q),queries))
 (BASE/'github-issue-search.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 urls=['https://github.com/lets-order-some-fries/trovark/issues/22','https://github.com/myoshi2891/Next-Store/pull/28','https://github.com/hyperpolymath/rsr-template-repo/pull/83','https://grep.app/api/search?q=alexar76']
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:pages=list(pool.map(get,urls))
 (BASE/'issue-pages-grep.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'searches':[{'query':r['query'],'status':r['status'],'total':r.get('total_count'),'items':[x['url'] for x in r.get('items',[])]} for r in rows],'pages':[{'url':r['url'],'status':r['status'],'contexts':len(r.get('contexts',[]))} for r in pages]},ensure_ascii=False))
