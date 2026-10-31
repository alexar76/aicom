"""Public GET captures for deeper external-use audit."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import hashlib,json
ROOT=Path(__file__).resolve().parent
TASKS=[
("usetested-review","https://usetested.com/v1/review?service=modelmarket.dev"),
("usetested-services","https://usetested.com/services"),
("agent402-modelmarket","https://agent402.tools/api/index?seller=modelmarket.dev"),
("agent402-leaderboard","https://agent402.tools/api/leaderboard"),
("agent402-router-guide","https://agent402.tools/guides/smart-order-router"),
("hub-live-stats","https://modelmarket.dev/ai-market/v2/stats/live"),
]
def get(task):
 key,url=task;row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public research audit; GET only)"}),timeout=25) as r:
   raw=r.read();row.update(status=r.status,final_url=r.url,content_type=r.headers.get("Content-Type"),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  filename=key+(".json" if "json" in (row["content_type"] or "") else ".html")
  (ROOT/filename).write_bytes(raw);row["body_file"]=filename
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=="__main__":
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,TASKS))
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(rows,ensure_ascii=False,indent=2))

