from fetch import get,ROOT
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import json
tasks=[("machina-discovery","https://mach402.dev/.well-known/ai-market.json"),("agentexec-discovery","https://agent-exec.448c.org/.well-known/ai-market.json"),("hub-peers","https://modelmarket.dev/ai-market/v2/federation/peers")]
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
for r in list(rows):
 if r.get("status")==200 and r["key"].endswith("discovery"):
  d=json.loads((ROOT/r["body_file"]).read_text());u=d.get("manifest_url")
  if isinstance(u,str) and urlparse(u).hostname in {"mach402.dev","agent-exec.448c.org"}:
   rows.append(get((r["key"].replace("discovery","manifest"),u)))
(ROOT/"http-peer-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps([{k:r.get(k) for k in ["key","url","status","bytes"]} for r in rows],indent=2))

