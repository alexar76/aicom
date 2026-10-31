from fetch import fetch,ROOT
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import json
registry=json.loads((ROOT/"warden-registry.raw").read_text())
already={"0.8.2","0.15.0","0.22.2"}
versions=[v for v in registry["versions"] if v not in already]
tasks={("warden-dependent-"+v):"https://deps.dev/_/s/npm/p/%40aimarket%2Fwarden/v/"+quote(v,safe="")+"/dependents" for v in versions}
tasks.update({("forks-"+repo):"https://api.github.com/repos/alexar76/"+repo+"/forks?per_page=100&sort=newest" for repo in ["warden","histor","aimarket-hub","argus","attested-memory","aicom"]})
(ROOT/"version-and-fork-scope.json").write_text(json.dumps({"versions_queried":versions,"versions_not_requeried_already_read":sorted(already),"forks_queried":["warden","histor","aimarket-hub","argus","attested-memory","aicom"]},indent=2)+"\n")
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,tasks.items()))
(ROOT/"http-version-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
for r in rows:
 data=None
 if r.get("status")==200:
  data=json.loads((ROOT/r["file"]).read_text())
  if r["key"].startswith("warden"):
   print(r["key"],r["status"],data.get("totalCount"),data.get("directSample"))
  else: print(r["key"],r["status"],[(x.get("full_name"),x.get("pushed_at")) for x in data])
 else:print(r["key"],r.get("status"),r.get("error"))

