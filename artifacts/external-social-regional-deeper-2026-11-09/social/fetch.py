import urllib.request,urllib.error,pathlib,json,datetime,hashlib,concurrent.futures
r=pathlib.Path(__file__).parent;urls={'fplcat-blog':'https://fplcat.com/blog/ai-agents-playing-fantasy-premier-league','forum-indexing-guide':'https://forumforagents.com/guides/who-indexes-a-new-mcp-server','forum-stats':'https://forumforagents.com/stats','forum-weekly':'https://forumforagents.com/weekly','gregbenza-arena':'https://gregbenza.ai/arena?day=2026-11-05','aiwithghost-legion':'https://aiwithghost.com/news/news-two-mcp-logs-matched-23-tools-five-days-later-every-name-had-changed/'}
def get(k,u):
 row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-public-external-audit/1.0'}),timeout=30)as x:b=x.read();row.update(status=x.status,final_url=x.url)
 except urllib.error.HTTPError as e:b=e.read();row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e);return row
 p=r/'raw'/(k+'.raw');p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:out=list(ex.map(lambda kv:get(*kv),urls.items()))
(r/'http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
