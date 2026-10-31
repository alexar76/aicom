from fetch import fetch,ROOT
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import json
queries=[
('"AWR-PROOF" -user:alexar76',"commit-awr-reasons"),
('"TOOL_DEF_CROSS_TOOL" -user:alexar76',"commit-cross-tool"),
('"TOOL_DEF_SECRET_HARVEST" -user:alexar76',"commit-secret-harvest"),
('"attestedmemory.net" -user:alexar76',"commit-attested-origin"),
]
tasks=[(key,"https://api.github.com/search/commits?"+urlencode({"q":q,"per_page":100,"sort":"committer-date","order":"desc"})) for q,key in queries]
with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(fetch,tasks))
(ROOT/"http-followup-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
(ROOT/"followup-queries.json").write_text(json.dumps([{"query":q,"key":key} for q,key in queries],indent=2)+"\n")
for r in rows:
 if r.get("status")==200:
  d=json.loads((ROOT/r["file"]).read_text());print(r["key"],d.get("total_count"),[(x.get("repository",{}).get("full_name"),x.get("html_url"),x.get("commit",{}).get("message","")[:250]) for x in d.get("items",[])[:20]])
 else:print(r)

