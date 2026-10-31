from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import hashlib,json
ROOT=Path(__file__).resolve().parent
def get(name,url):
 r={"name":name,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public read-only audit)"}),timeout=25) as response:
   raw=response.read(2000001);r.update(status=response.status,final_url=response.url,content_type=response.headers.get("Content-Type"),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  file=name+(".json" if "json" in (r["content_type"] or "") else ".html");(ROOT/file).write_bytes(raw);r["body_file"]=file
 except HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 return r
if __name__=="__main__":
 rows=[get("aefact-readers","https://aefact.site/readers")]
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(rows,ensure_ascii=False,indent=2))

