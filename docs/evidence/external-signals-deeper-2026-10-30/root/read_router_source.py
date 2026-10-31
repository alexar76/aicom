from fetch import get,ROOT
import json
rows=[get(("agent402-current-commit","https://api.github.com/repos/MikeyPetrillo/Agent402/commits?per_page=1"))]
r=rows[0]
if r.get("status")==200:
 d=json.loads((ROOT/r["body_file"]).read_text());sha=d[0]["sha"]
 for name,rel in [("dispatch","src/dispatch-eligibility.js"),("index","src/x402-index.js"),("execute","src/tools/route-execute.js")]:
  rows.append(get(("agent402-source-"+name,"https://raw.githubusercontent.com/MikeyPetrillo/Agent402/"+sha+"/"+rel)))
 (ROOT/"agent402-source-pin.json").write_text(json.dumps({"sha":sha,"commit_url":d[0]["html_url"],"date":d[0]["commit"]["committer"]["date"]},indent=2)+"\n")
(ROOT/"http-source-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps([{k:r.get(k) for k in ["key","url","status","bytes"]} for r in rows],indent=2))

