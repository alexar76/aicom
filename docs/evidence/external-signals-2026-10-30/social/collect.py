"""Read-only public social/community capture; no credentials, posts, or writes remotely."""
import concurrent.futures, datetime, hashlib, json, pathlib, re, urllib.parse, urllib.request

BASE = pathlib.Path(__file__).resolve().parent
RAW = BASE / 'raw'
RAW.mkdir(exist_ok=True)
records = []

def get(label, url):
    rec = dict(label=label, url=url, method='GET', checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AICOM-external-signal-audit/1.0 (public read-only)', 'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(5_000_000)
            rec.update(status=r.status, final_url=r.url, content_type=r.headers.get('Content-Type'), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            path = RAW / (label + ('.json' if 'json' in (rec['content_type'] or '') else '.html'))
            path.write_bytes(data)
            rec['file'] = str(path.relative_to(BASE))
            try: parsed = json.loads(data)
            except Exception: parsed = None
    except Exception as e:
        rec.update(status=getattr(e, 'code', None), error=str(e))
        parsed = None
    records.append(rec)
    return parsed

def batch(targets):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda p: get(*p), targets))

targets = [
 ('dev-list', 'https://dev.to/api/articles?username=alexar76&per_page=100'),
 ('hn-histor', 'https://hacker-news.firebaseio.com/v0/item/50193565.json'),
 ('hn-search-modelmarket','https://hn.algolia.com/api/v1/search_by_date?query=modelmarket.dev&hitsPerPage=100'),
 ('hn-search-alexar76','https://hn.algolia.com/api/v1/search_by_date?query=alexar76&hitsPerPage=100'),
 ('hn-search-attestedmemory','https://hn.algolia.com/api/v1/search_by_date?query=attestedmemory.net&hitsPerPage=100'),
 ('itch-pingblip', 'https://pingblip.itch.io/pingblip'),
 ('itch-pingblip-topic', 'https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game'),
 ('itch-weight', 'https://alexar76.itch.io/the-weight-of-the-answer'),
 ('itch-white', 'https://alexar76.itch.io/the-white-on-the-map'),
 ('itch-shadow', 'https://alexar76.itch.io/the-right-to-a-shadow'),
 ('mastodon-modelmarket', 'https://mastodon.social/api/v2/search?q=modelmarket.dev&type=statuses&limit=40'),
 ('mastodon-alexar76', 'https://mastodon.social/api/v2/search?q=alexar76&type=statuses&limit=40'),
 ('bluesky-modelmarket', 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=modelmarket.dev&limit=100&sort=latest'),
 ('bluesky-alexar76', 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=alexar76&limit=100&sort=latest'),
 ('bluesky-attestedmemory', 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=attestedmemory.net&limit=100&sort=latest'),
 ('bluesky-pingblip', 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=PingBlip&limit=100&sort=latest'),
 ('reddit-modelmarket', 'https://www.reddit.com/search.json?q=%22modelmarket.dev%22&sort=new&limit=100'),
 ('reddit-alexar76', 'https://www.reddit.com/search.json?q=%22alexar76%22&sort=new&limit=100'),
 ('telegram-channel','https://t.me/s/just_for_agents'),
 ('youtube-channel','https://www.youtube.com/@My-AI-Factory'),
]
data = batch(targets)
dev_public = data[0]
scope = json.loads((BASE.parents[3] / 'artifacts/ecosystem-deep-2026-10-28/root/current-published-article-scope.json').read_text())
known = {a['id']:a for a in scope['articles']}
if isinstance(dev_public,list):
    known.update({a['id']:a for a in dev_public})
# Publication receipts only contribute explicitly public URLs; no credentials read.
promo = BASE.parents[4] / 'PromoMaterials/devto/mcp-hidden-billing-2026-10-29/devto-public.json'
if promo.exists():
    p = json.loads(promo.read_text())
    if isinstance(p,dict) and p.get('url'): known[p['id']] = p
article_targets=[]
for a in known.values():
    if a.get('comments_count',0) or str(a.get('published_at','')) >= '2026-10-27':
        parts=urllib.parse.urlparse(a['url']).path.strip('/')
        article_targets.append(('dev-article-'+str(a['id']), 'https://dev.to/api/articles/'+parts))
articles=batch(article_targets)
updated=[a for a in articles if isinstance(a,dict) and a.get('id')]
threads=batch([('dev-comments-'+str(a['id']), 'https://dev.to/api/comments?a_id='+str(a['id'])) for a in updated if a.get('comments_count',0)])
flat=[]
def flatten(comments):
    for c in comments:
        if not isinstance(c,dict): continue
        flat.append({k:c.get(k) for k in ['id_code','created_at','user','body_html']})
        flatten(c.get('children',[]))
for t in threads:
    if isinstance(t,list): flatten(t)
external=[c for c in flat if (c.get('user') or {}).get('username')!='alexar76']
summary=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), public_dev_list_count=len(dev_public) if isinstance(dev_public,list) else None, known_published_article_scope=len(known), dev_articles_refreshed=[{k:a.get(k) for k in ['id','url','title','comments_count','published_at','positive_reactions_count']} for a in updated], threads_read=len(threads), comments_read=len(flat), external_comments=len(external), external_comments_since_2026_10_28=[c for c in external if (c.get('created_at') or '')>='2026-10-28'], latest_external_comments=sorted(external,key=lambda c:c.get('created_at') or '',reverse=True)[:5])
(BASE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(BASE/'http-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ['dev_articles_refreshed','latest_external_comments']},ensure_ascii=False,indent=2))
print(json.dumps([{'label':r['label'],'status':r.get('status'),'error':r.get('error')} for r in records],ensure_ascii=False,indent=2))
