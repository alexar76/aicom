import urllib.request, urllib.parse, json, pathlib, datetime, concurrent.futures, hashlib

out=pathlib.Path(__file__).parent
targets={
 'hn-modelmarket':'https://hn.algolia.com/api/v1/search_by_date?'+urllib.parse.urlencode({'query':'modelmarket.dev','hitsPerPage':100}),
 'hn-alexar76':'https://hn.algolia.com/api/v1/search_by_date?'+urllib.parse.urlencode({'query':'alexar76','hitsPerPage':100}),
 'hn-pingblip':'https://hn.algolia.com/api/v1/search_by_date?'+urllib.parse.urlencode({'query':'pingblip','hitsPerPage':100}),
 'bsky-modelmarket':'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?'+urllib.parse.urlencode({'q':'modelmarket.dev','limit':100,'sort':'latest'}),
 'bsky-pingblip':'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?'+urllib.parse.urlencode({'q':'pingblip','limit':100,'sort':'latest'}),
 'reddit-modelmarket':'https://www.reddit.com/search.json?'+urllib.parse.urlencode({'q':'"modelmarket.dev"','sort':'new','limit':100}),
 'itch-announcement':'https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game',
 'itch-game':'https://pingblip.itch.io/pingblip',
 'itch-book1':'https://alexar76.itch.io/the-weight-of-the-answer',
 'itch-book2':'https://alexar76.itch.io/the-white-on-the-map',
 'itch-book3':'https://alexar76.itch.io/the-right-to-a-shadow',
}

def run(t):
    k,u=t
    rec={'key':k,'url':u,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 (public mention research)'})
        with urllib.request.urlopen(req,timeout=25) as r:
            data=r.read()
            rec.update(status=r.status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            (out/(k+'.txt')).write_bytes(data)
        if k.startswith('hn-'):
            j=json.loads(data)
            rec['nbHits']=j.get('nbHits')
            rec['hits']=[{kk:v for kk,v in h.items() if kk in ['author','created_at','title','story_title','story_url','comment_text','url','objectID','points','num_comments']} for h in j.get('hits',[])][:30]
        elif k.startswith('bsky-'):
            j=json.loads(data)
            rec['cursor']=j.get('cursor')
            rec['posts']=j.get('posts',[])
    except Exception as e:
        rec['error']=str(e)
    return rec

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    rows=list(ex.map(run,targets.items()))
(out/'index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:
    print(json.dumps(r,ensure_ascii=False))
