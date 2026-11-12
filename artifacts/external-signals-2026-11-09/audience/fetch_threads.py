import urllib.request,urllib.error,json,datetime,pathlib,hashlib,concurrent.futures,urllib.parse
root=pathlib.Path(__file__).parent;raw=root/'raw';arts=json.loads((raw/'devto-articles.raw').read_text());feed=json.loads((raw/'bsky-feed.raw').read_text())
urls={f'devto-comments-{a["id"]}':f'https://dev.to/api/comments?a_id={a["id"]}' for a in arts if a['comments_count']}
for x in feed['feed']:
 p=x['post']
 if p.get('replyCount'):urls['bsky-thread-'+p['uri'].rsplit('/',1)[-1]]='https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri='+urllib.parse.quote(p['uri'],safe='')+'&depth=10'
urls.update({'youtube-shorts':'https://www.youtube.com/channel/UCdhqQ5UAdUHPyX8BnolB4dQ/shorts?hl=en','telegram-meta':'https://t.me/just_for_agents','bsky-profile':'https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=alexar76.bsky.social','devto-user':'https://dev.to/api/users/by_username?url=alexar76'})
def get(k,u):
 row={'key':k,'url':u,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-audience-check/1.0'}),timeout=30) as r:b=r.read();row.update(status=r.status,final_url=r.url)
  p=raw/f'{k}.raw';p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except urllib.error.HTTPError as e:row.update(status=e.code,error=str(e));(raw/f'{k}.error').write_bytes(e.read())
 except Exception as e:row['error']=str(e)
 return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:out=list(ex.map(lambda kv:get(*kv),urls.items()))
(root/'thread-http-index.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
