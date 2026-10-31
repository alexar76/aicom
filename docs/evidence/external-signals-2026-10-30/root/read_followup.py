from read_public import get,ROOT
from concurrent.futures import ThreadPoolExecutor
import json
tasks=[
("aer-open-data","https://agenteconomy.report/s/data/"),
("aer-method","https://agenteconomy.report/s/"),
("a2a-page","https://a2aregistry.org/agents/841eea85-51d4-450c-b35a-086534dc08f6/"),
("agenstry-method","https://agenstry.com/docs/conformance"),
]
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
(ROOT/"http-followup-index.json").write_text(json.dumps({"records":[{k:v for k,v in r.items() if k!="data"} for r in rows]},ensure_ascii=False,indent=2)+"\n")
print(json.dumps([{"key":r["key"],"status":r.get("status"),"bytes":r.get("bytes")} for r in rows]))

