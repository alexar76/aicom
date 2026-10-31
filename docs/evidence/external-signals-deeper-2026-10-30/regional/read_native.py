"""Read-only native regional indexes and bookmark comments."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json,hashlib
ROOT=Path(__file__).resolve().parent
TARGETS=[
("hatena-qiita-histor","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://qiita.com/qwezzy721/items/b71aaeaae84fcb360fe6"})),
("hatena-qiita-cost","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://qiita.com/qwezzy721/items/4dfe9dc2fbe9d69b1fb7"})),
("hatena-histor","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://histor.modelmarket.dev/"})),
("hatena-warden","https://b.hatena.ne.jp/entry/jsonlite/?"+urlencode({"url":"https://github.com/alexar76/warden"})),
("qiita-histor","https://qiita.com/api/v2/items?"+urlencode({"query":"HISTOR","per_page":"100"})),
("qiita-warden","https://qiita.com/api/v2/items?"+urlencode({"query":"WARDEN MCP","per_page":"100"})),
("qiita-12915","https://qiita.com/api/v2/items?"+urlencode({"query":"12915","per_page":"100"})),
("zenn-histor","https://zenn.dev/search?"+urlencode({"q":"HISTOR"})),
("zenn-modelmarket","https://zenn.dev/api/search?"+urlencode({"q":"modelmarket.dev","source":"articles","order":"latest"})),
("habr-modelmarket","https://habr.com/kek/v2.0/search/?"+urlencode({"q":'"modelmarket.dev"',"target_type":"posts","order":"relevance"})),
("habr-alexar76","https://habr.com/kek/v2.0/search/?"+urlencode({"q":'"alexar76"',"target_type":"posts","order":"relevance"})),
]
def get(task):
 key,url=task; row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public read-only research)","Accept":"application/json,text/html"}),timeout=25) as r:
   raw=r.read();row.update(status=r.status,final_url=r.url,content_type=r.headers.get("Content-Type"),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  name=key+(".json" if "json" in (row["content_type"] or "") else ".html");(ROOT/name).write_bytes(raw);row["body_file"]=name
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=="__main__":
 ROOT.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,TARGETS))
 (ROOT/"native-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(rows,ensure_ascii=False))

