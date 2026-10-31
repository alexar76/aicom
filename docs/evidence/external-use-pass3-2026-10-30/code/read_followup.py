from fetch import fetch,ROOT
from concurrent.futures import ThreadPoolExecutor
import json
tasks={
"fork-ayesha-commits":"https://api.github.com/repos/ayeshanazneen1/aicom/commits?per_page=30",
"fork-adity-commits":"https://api.github.com/repos/adity982/aicom/commits?per_page=30",
"fork-benjamin-commits":"https://api.github.com/repos/BenjaminAyivoh1/aicom/commits?per_page=30",
"alias-argus3":"https://registry.npmjs.org/argus-3/latest",
"alias-arguswarden":"https://registry.npmjs.org/argus-warden/latest",
"rust-reverse-deps":"https://crates.io/api/v1/crates/aimarket-agent/reverse_dependencies?page=1&per_page=100",
}
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,tasks.items()))
(ROOT/"http-followup-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
for r in rows:
 print(r["key"],r.get("status"))
 if r.get("status")==200:
  d=json.loads((ROOT/r["file"]).read_text())
  if r["key"].startswith("fork"):print([(x.get("author",{}).get("login") if x.get("author") else None,x.get("sha"),x.get("commit",{}).get("message","")[:100]) for x in d][:30])
  elif r["key"].startswith("alias"):print({k:d.get(k) for k in ["name","version","repository","maintainers"]})
  else:print(d)

