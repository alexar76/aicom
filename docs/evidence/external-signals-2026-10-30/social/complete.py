"""Finish missing public comment threads at low request cadence after capture."""
import datetime, hashlib, json, pathlib, re, time, urllib.request
B=pathlib.Path(__file__).resolve().parent
records=json.loads((B/'http-index.json').read_text())
def get(label,url):
    rec=dict(label=label,url=url,method='GET',checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    data=None
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-external-signal-audit/1.0 (public read-only)'}),timeout=30) as r:
            raw=r.read(5_000_000)
            rec.update(status=r.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),file='raw/'+label+'.json')
            (B/rec['file']).write_bytes(raw)
            data=json.loads(raw)
    except Exception as e:rec.update(status=getattr(e,'code',None),error=str(e))
    records.append(rec)
    (B/'http-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    return data
articles=json.loads((B/'raw/dev-list.json').read_text())
for a in articles:
    if a.get('comments_count',0) and not (B/f"raw/dev-comments-{a['id']}.json").exists():
        get('dev-comments-'+str(a['id']),'https://dev.to/api/comments?a_id='+str(a['id']))
        time.sleep(1.2)
hn=json.loads((B/'raw/hn-histor.json').read_text())
for kid in hn.get('kids',[]):get('hn-comment-'+str(kid),f'https://hacker-news.firebaseio.com/v0/item/{kid}.json')
for term in ['magic-ai-factory.com','PingBlip','independentai.network']:
    get('hn-search-'+term.replace('.','-'),'https://hn.algolia.com/api/v1/search_by_date?query='+term+'&hitsPerPage=100')
flat=[]
threads=[]
def walk(cs,article_id):
    for c in cs:
        flat.append(dict(article_id=article_id,id_code=c.get('id_code'),created_at=c.get('created_at'),user=(c.get('user')or{}).get('username'),body_html=c.get('body_html')))
        walk(c.get('children',[]),article_id)
for a in articles:
    p=B/f"raw/dev-comments-{a['id']}.json"
    if p.exists():
        before=len(flat)
        walk(json.loads(p.read_text()),a['id'])
        threads.append(dict(id=a['id'],url=a['url'],metadata_comments=a.get('comments_count'),read_comments=len(flat)-before))
external=[c for c in flat if c['user']!='alexar76']
summary=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='public article list (62 entries); current public list now includes all 61 previously authenticated published articles plus 29 October publication',public_dev_list_count=len(articles),threads_read=len(threads),comments_read=len(flat),external_comments=len(external),own_comments=len(flat)-len(external),threads=threads,external_comments_since_2026_10_28=[c for c in external if(c.get('created_at')or'')>='2026-10-28'],latest_external_comments=sorted(external,key=lambda c:c.get('created_at')or'',reverse=True)[:5])
(B/'complete-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
