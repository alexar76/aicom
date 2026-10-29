import urllib.request,urllib.parse,json,pathlib,datetime,concurrent.futures,hashlib
out=pathlib.Path(__file__).parent
queries=['alexar76','independentai.network','attestedmemory.net','emberlinedesk.com','pantheon.modelmarket.dev','Trace of Refusal','pingblip']
def run(q):
    u='https://hn.algolia.com/api/v1/search_by_date?'+urllib.parse.urlencode({'query':q,'hitsPerPage':100,'typoTolerance':'false','restrictSearchableAttributes':'title,comment_text,url,story_text'})
    r={'query':q,'url':u,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(u,timeout=20) as response:
            data=response.read(); r.update(status=response.status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        (out/('hn-exact-'+q.replace('.','-').replace(' ','-')+'.json')).write_bytes(data)
        j=json.loads(data);r['nbHits']=j.get('nbHits');r['hits']=[{k:v for k,v in h.items() if k in ['author','created_at','title','story_title','story_url','comment_text','url','objectID','points','num_comments']} for h in j.get('hits',[])]
    except Exception as e:r['error']=str(e)
    return r
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: rows=list(ex.map(run,queries))
(out/'extra-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(json.dumps(r,ensure_ascii=False))
