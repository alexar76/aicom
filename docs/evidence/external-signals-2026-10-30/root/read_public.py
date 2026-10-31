"""Public GET-only audit captures. No credentials, writes or paid invocations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib, json
ROOT=Path(__file__).resolve().parent
TASKS=[
("agent-economy","https://agenteconomy.report/s/modelmarket.dev.json"),
("x402-volume","https://x402-list.com/api/v1/services/aimarket/volume"),
("x402-buyers","https://x402-list.com/api/v1/services/aimarket/buyers"),
("a2a-registry","https://a2aregistry.org/api/agents/841eea85-51d4-450c-b35a-086534dc08f6"),
("agenstry","https://agenstry.com/agents/modelmarket.dev"),
("openalex","https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760"),
("datacite-version","https://api.datacite.org/dois/10.5281/zenodo.23512760"),
("datacite-concept","https://api.datacite.org/dois/10.5281/zenodo.23512759"),
("hf-dataset","https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions"),
("hf-discussions","https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions/discussions"),
("hubwiz","https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/"),
("radyz","https://radyz.cz/rychle-zpravy/histor-otevrel-dataset-zmen-nastroju-mcp-nikoli-seznam-skodlivych-serveru/"),
("independentai","https://independentai.network/"),
("karatum","https://karatum.com/"),
("emberline","https://emberline.app/"),
]
def get(task):
 key,url=task
 row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public evidence audit; read-only)"}),timeout=25) as r:
   raw=r.read();row.update(status=r.status,final_url=r.url,content_type=r.headers.get("Content-Type"),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  ext=".json" if "json" in (row["content_type"] or "") else ".html"
  filename=key+ext;(ROOT/filename).write_bytes(raw);row["body_file"]=filename
  try: row["data"]=json.loads(raw)
  except (ValueError,UnicodeError):pass
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=="__main__":
 ROOT.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(get,TASKS))
 (ROOT/"http-index.json").write_text(json.dumps({"records":[{k:v for k,v in r.items() if k!="data"} for r in rows]},ensure_ascii=False,indent=2)+"\n")
 print(json.dumps([{"key":r["key"],"status":r.get("status"),"bytes":r.get("bytes"),"data_keys":list(r.get("data",{}))[:12] if isinstance(r.get("data"),dict) else None} for r in rows],ensure_ascii=False))

