"""Derive bounded native-source observations and verify capture hashes."""
import collections,hashlib,json,pathlib,re,urllib.parse
from html.parser import HTMLParser
R=pathlib.Path(__file__).parent;raw=R/'raw'
captures=json.loads((R/'native-index.json').read_text())
for x in captures:
 if 'sha256' in x:assert hashlib.sha256((raw/(x['name']+'.raw')).read_bytes()).hexdigest()==x['sha256']
def read(name):return json.loads((raw/(name+'.raw')).read_text())
def meta(name):
 d=read(name);return {k:d.get(k) for k in ['id','title','url','created_at','updated_at','likes_count','stocks_count','comments_count']}
class Links(HTMLParser):
 def __init__(self):super().__init__();self.current=None;self.rows=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.current={'href':dict(attrs).get('href',''),'text':''}
 def handle_data(self,data):
  if self.current is not None:self.current['text']+=data
 def handle_endtag(self,tag):
  if tag=='a' and self.current is not None:self.rows.append(self.current);self.current=None
naver={}
for name in ['naver-domain','naver-alexar']:
 p=Links();p.feed((raw/(name+'.raw')).read_text());seen=set();rows=[]
 for x in p.rows:
  h=x['href'];host=urllib.parse.urlsplit(h).netloc.lower()
  if not h.startswith('http') or host.endswith('naver.com'):continue
  if any(s in (h+' '+x['text']).lower() for s in ['alexar76','modelmarket.dev','attestedmemory']) and h not in seen:
   rows.append(x);seen.add(h)
 naver[name]=rows
comments=[]
before=json.loads(pathlib.Path('docs/evidence/external-signals-2026-10-30/regional/qiita-tool-cost-comments.json').read_text())
old={x['id']:x for x in before}
for x in read('qiita-cost-comments'):
 comments.append({'id':x['id'],'author':x['user']['id'],'created_at':x['created_at'],'updated_at':x['updated_at'],'known_before':x['id'] in old,'body_unchanged':x.get('body')==old.get(x['id'],{}).get('body'),'url':'https://qiita.com/qwezzy721/items/4dfe9dc2fbe9d69b1fb7#comment-'+x['id']})
queries=[]
for p in sorted(R.glob('search-*.json')):
 for q in json.loads(p.read_text())['queries']:queries.append({'query':q,'response_file':p.name})
(R/'query-index.json').write_text(json.dumps(queries,ensure_ascii=False,indent=2))
dates={}
for name in ['hubwiz','juejin','selectdataset']:
 text=(raw/(name+'.raw')).read_text();dates[name]={'datePublished':re.findall(r'"datePublished"\s*:\s*"([^"]+)"',text)[:1],'dateModified':re.findall(r'"dateModified"\s*:\s*"([^"]+)"',text)[:1]}
summary={'scope':'East Asia; public source reading only; no new confirmed independent mention/runtime adopter found in this bounded sample.','date':'2026-11-09','search_strings':len(queries),'unique_search_strings':len({x['query'] for x in queries}),'web_response_batches':7,'native_get_count':len(captures),'native_statuses':dict(collections.Counter(str(x.get('status','error')) for x in captures)),'qiita':{'author_item_count':len(read('qiita-author')),'domain_search_items':len(read('qiita-domain-search')),'articles':[meta('qiita-cost'),meta('qiita-histor')],'cost_comments':comments,'histor_comments':len(read('qiita-histor-comments'))},'zenn':{k:read(k) for k in ['zenn-domain','zenn-alexar','zenn-attested-scraps']},'hatena':{k:read(k) for k in ['hatena-cost','hatena-histor','hatena-histor-site']},'gitee_repositories':read('gitee-public-search'),'naver_relevant_external_links':naver,'known_chinese_source_dates':dates,'weibo':'Web tool reported robots.txt non-retryable restriction; unrelated signup/app results excluded.','new_independent_mentions':[],'limits':['Only exact native query/page samples, not all national web content.','Own Qiita qwezzy721 posts and own replies excluded from independent reactions.','Known Hubwiz/Juejin and autoaggregators SelectDataset/billionare/NicheDB are not counted as new national adoption.','Paper Vault GET HTTP502 does not establish removal or absence.','No login, CAPTCHA bypass, publishing, messages or GitHub writes.']}
(R/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({'queries':len(queries),'get_count':len(captures),'statuses':summary['native_statuses'],'cost_comments':comments,'naver_links':naver},ensure_ascii=False,indent=2))
