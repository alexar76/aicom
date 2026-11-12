import urllib.request,urllib.error,urllib.parse,pathlib,json,datetime,hashlib,concurrent.futures
root=pathlib.Path(__file__).parent;urls={}
for q in ['modelmarket.dev','histor.modelmarket.dev','@aimarket/warden','attestedmemory.net']:
 key='hn-'+q.replace('/','-').replace('@','')
 urls[key]='https://hn.algolia.com/api/v1/search?query='+urllib.parse.quote(q,safe='')+'&hitsPerPage=100&typoTolerance=false'
urls.update({'itch-pingblip':'https://pingblip.itch.io/pingblip','itch-topic':'https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game','itch-weight':'https://alexar76.itch.io/the-weight-of-the-answer','itch-white':'https://alexar76.itch.io/the-white-on-the-map','itch-shadow':'https://alexar76.itch.io/the-right-to-a-shadow','witness-request':'https://lists.witness-network.org/mailman3/hyperkitty/list/participate%40lists.witness-network.org/thread/J5ZRRQ2EQRVIFF7LL23TWMTL4AVCLYNZ/'})
def fetch(k,u):
 row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-social-audit/1.0'}),timeout=30)as x:b=x.read();row.update(status=x.status,final_url=x.url)
 except urllib.error.HTTPError as e:b=e.read();row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e);return row
 p=root/'raw'/(k+'.raw');p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as ex:out=list(ex.map(lambda kv:fetch(*kv),urls.items()))
(root/'http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
