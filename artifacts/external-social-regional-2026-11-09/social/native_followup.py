import urllib.request,urllib.error,urllib.parse,pathlib,json,datetime,hashlib,concurrent.futures
root=pathlib.Path(__file__).parent;urls={'hn-item':'https://hn.algolia.com/api/v1/items/50193565','reddit-search':'https://www.reddit.com/search.json?q=%22modelmarket.dev%22&sort=new&limit=100&type=link','bsky-search':'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=modelmarket.dev&limit=100&sort=latest','mastodon-search':'https://mastodon.social/api/v2/search?q=modelmarket.dev&type=statuses&limit=40'}
def fetch(k,u):
 row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-social-audit/1.0'}),timeout=30)as x:b=x.read();row.update(status=x.status,final_url=x.url)
 except urllib.error.HTTPError as e:b=e.read();row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e);return row
 p=root/'raw'/(k+'.raw');p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:out=list(ex.map(lambda kv:fetch(*kv),urls.items()))
(root/'native-http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
