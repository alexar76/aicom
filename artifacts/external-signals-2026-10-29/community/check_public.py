"""Public GET-only community response delta; no authentication or tool calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parent
SINCE='2026-10-28T15:00:00Z'
records=[]
def read(key,url):
    record={'key':key,'url':url,'method':'GET','checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 public research'}),timeout=25) as response:
            raw=response.read();record.update(status=response.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),link=response.headers.get('Link'))
        (ROOT/(key+'.raw')).write_bytes(raw)
        try:data=json.loads(raw)
        except ValueError:data=raw.decode('utf-8',errors='replace')
    except urllib.error.HTTPError as error:record.update(status=error.code,error=str(error));data=None
    except Exception as error:record.update(status=None,error=str(error));data=None
    records.append(record)
    return data

def flatten(rows):
    for row in rows:
        yield row
        yield from flatten(row.get('children',[]))

def main():
    articles=read('dev-public-list','https://dev.to/api/articles?username=alexar76&per_page=100')
    summary={'since_utc':SINCE,'dev_public_count':len(articles) if isinstance(articles,list) else None}
    latest=[]
    for slug in ['why-our-mcp-server-stopped-trusting-localhost-by-default-26jm','same-mcp-version-different-tools-what-two-independent-captures-revealed-2p6d']:
        data=read('dev-'+slug,'https://dev.to/api/articles/alexar76/'+slug)
        if isinstance(data,dict):latest.append({k:data.get(k) for k in ['id','url','title','published_at','comments_count','public_reactions_count']})
    summary['known_latest']=latest
    by_id={r['id']:r for r in (articles or []) if isinstance(r,dict)}
    for row in latest:by_id[row['id']]=row
    tasks=[r for r in by_id.values() if r.get('comments_count',0)]
    def comments(article):
        rows=read('dev-comments-'+str(article['id']),'https://dev.to/api/comments?a_id='+str(article['id']))
        if not isinstance(rows,list):return {'article_id':article['id'],'error':'No comment list'}
        all_rows=list(flatten(rows))
        return {'article_id':article['id'],'url':article.get('url'),'metadata_comments':article['comments_count'],'visible_comments':len(all_rows),'new_comments':[{'id_code':r.get('id_code'),'created_at':r.get('created_at'),'author':r.get('user',{}).get('username'),'body_html':r.get('body_html')} for r in all_rows if r.get('created_at','')>SINCE]}
    with ThreadPoolExecutor(max_workers=2) as pool:summary['dev_threads']=list(pool.map(comments,tasks))
    other=[
      ('qiita-cost','https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7'),
      ('qiita-cost-comments','https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7/comments'),
      ('qiita-histor','https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6'),
      ('qiita-histor-comments','https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6/comments'),
      ('hn-histor','https://hacker-news.firebaseio.com/v0/item/50193565.json'),
      ('itch-pingblip-thread','https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game'),
      ('itch-pingblip-game','https://pingblip.itch.io/pingblip'),
      ('itch-weight','https://alexar76.itch.io/the-weight-of-the-answer'),
      ('itch-white','https://alexar76.itch.io/the-white-on-the-map'),
      ('itch-shadow','https://alexar76.itch.io/the-right-to-a-shadow'),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:others=dict(pool.map(lambda t:(t[0],read(*t)),other))
    summary['qiita']={k:([{x:r.get(x) for x in ['id','created_at','updated_at','body','user']} for r in d] if isinstance(d,list) else {x:d.get(x) for x in ['id','created_at','updated_at','comments_count','likes_count','url']} if isinstance(d,dict) else None) for k,d in others.items() if k.startswith('qiita')}
    hn=others.get('hn-histor')
    summary['hn_story']=hn
    if isinstance(hn,dict):
        summary['hn_comments']=[read('hn-comment-'+str(k),'https://hacker-news.firebaseio.com/v0/item/'+str(k)+'.json') for k in hn.get('kids',[])]
    summary['checked_at_utc']=datetime.now(timezone.utc).isoformat()
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'http-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
