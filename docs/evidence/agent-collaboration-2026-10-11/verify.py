import json,urllib.request,concurrent.futures
from html.parser import HTMLParser
phrases={'en':'Your AI doesn’t have to do it all.','ru':'Вашему ИИ не нужно уметь всё.','es':'Tu IA no tiene que saber hacerlo todo.','fr':'Votre IA n’a pas besoin de tout savoir faire.','zh':'你的 AI 不必无所不能。'}
class Page(HTMLParser):
 def __init__(self,body):
  super().__init__();self.ids=[];self.links=[];self.canonical=None;self.lang=None;self.main_lang=None;self.feed(body)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='a':self.links.append(a.get('href',''))
  if tag=='html':self.lang=a.get('lang')
  if tag=='main':self.main_lang=a.get('lang')
  if tag=='link' and a.get('rel')=='canonical':self.canonical=a.get('href')
def get(url):
 with urllib.request.urlopen(url,timeout=60) as r:return r.status,r.read().decode()
def check(args):
 domain,lang=args;route='/' if lang=='en' else '/'+lang+'/'
 url='https://'+domain+route;status,body=get(url);page=Page(body)
 content_lang=page.main_lang or page.lang
 assert phrases[lang] in body and content_lang==lang,url
 assert page.canonical==url,(url,page.canonical)
 assert 'https://magic-ai-factory.com/?lang='+lang in page.links,url
 required=['factory-content','outputs','inside','specialists'] if domain.startswith('modeldev') else ['exchange','explore']
 assert all(x in page.ids for x in required),url
 assert len(page.ids)==len(set(page.ids)),url
 return {'url':url,'status':status,'content_language':content_lang,'canonical':page.canonical,'working_factory_link':True,'original_sections_preserved':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 pages=list(pool.map(check,[(d,l) for d in ['modeldev.modelmarket.dev','ecosystem.modelmarket.dev'] for l in phrases]))
status,body=get('https://magic-ai-factory.com/?lang=en')
assert all(x in body for x in ['landing-products','full-products','factory-build'])
_,body=get('https://magic-ai-factory.com/api/products');products=json.loads(body)['products']
print(json.dumps({'pages':pages,'working_factory':{'status':status,'catalog_entries':len(products),'landing_pages':sum(p.get('delivery_profile')=='marketing_landing' for p in products),'full_products':sum(p.get('delivery_profile')!='marketing_landing' for p in products)}},ensure_ascii=False,indent=2))
