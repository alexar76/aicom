"""New native community search surfaces; public GET only, no login."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,hashlib
ROOT=Path(__file__).resolve().parent
tasks=[
("cursor-native-warden","https://forum.cursor.com/search.json?q=%40aimarket%2Fwarden"),
("n8n-native-modelmarket","https://community.n8n.io/search.json?q=modelmarket.dev"),
("lobsters-native-stories","https://lobste.rs/search?q=modelmarket.dev&what=stories&order=newest"),
]
def get(t):
 name,url=t;out={"name":name,"url":url,"method":"GET","at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  try:r=urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 public read-only research"}),timeout=25)
  except HTTPError as e:r=e
  with r:raw=r.read(1500000);out.update(status=r.status,final_url=r.url,content_type=r.headers.get("Content-Type"),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  f=name+(".json" if "json" in (out["content_type"] or "") else ".html")
  (ROOT/f).write_bytes(raw);out["body_file"]=f
 except Exception as e:out.update(error=str(e),status=None)
 return out
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
(ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(rows,ensure_ascii=False,indent=2))

