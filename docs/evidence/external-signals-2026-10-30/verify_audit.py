"""Verify local evidence integrity and report links without network access."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
SCOPES={
 "root":{"web_queries":36,"indexes":["http-index.json","http-followup-index.json","http-methods-index.json"],"summary":"summary.json"},
 "social":{"web_queries":36,"indexes":["http-index.json"],"summary":"complete-summary.json"},
 "regional":{"web_queries":80,"indexes":["http-index.json","http-extra-index.json","http-final-index.json"],"summary":"summary.json","native_search_queries":5},
 "technical":{"web_queries":24,"indexes":["verification-index.json"],"summary":"summary.json"},
}
parse_errors=[]
for f in ROOT.rglob("*.json"):
 try:json.loads(f.read_text())
 except Exception as e:parse_errors.append({"file":str(f.relative_to(ROOT)),"error":str(e)})
captures=[];branches={};missing=[]
for branch,scope in SCOPES.items():
 files=list((ROOT/branch).rglob("*"))
 hashes={}
 for f in files:
  if f.is_file():hashes.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(),[]).append(str(f.relative_to(ROOT)))
 rows=[]
 for name in scope["indexes"]:
  d=json.loads((ROOT/branch/name).read_text())
  rows.extend(d if isinstance(d,list) else d.get("records",d.get("reads",[])))
 statuses=Counter()
 for row in rows:
  status=row.get("status")
  if status is None:
   match=re.search(r"HTTP Error (\d+)",row.get("error",""))
   status=int(match.group(1)) if match else "transport-error"
  statuses[str(status)]+=1
  entry={"branch":branch,**row}
  if row.get("sha256"):
   entry["verified_body_files"]=hashes.get(row["sha256"],[])
   if not entry["verified_body_files"]:missing.append({"branch":branch,"name":row.get("key",row.get("label",row.get("name"))),"sha256":row["sha256"]})
  captures.append(entry)
 branches[branch]={**scope,"captured_gets":len(rows),"statuses":dict(statuses),"report":branch+"/report.ru.md","summary":branch+"/"+scope["summary"]}
reports=[REPO/"docs/growth/external-signals-2026-10-30.ru.md",*(ROOT/x/"report.ru.md" for x in SCOPES)]
missing_links=[]
for f in reports:
 for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)",f.read_text()):
  if target.startswith(("https://","http://","#","mailto:","codex:")):continue
  raw=target.split("#",1)[0].split(":",1)[0]
  if raw and not (f.parent/raw).exists():missing_links.append({"file":str(f.relative_to(REPO)),"target":target})
out={"observed_date":"2026-10-30","timezone":"Europe/Moscow","generated_at_utc":datetime.now(timezone.utc).isoformat(),"main_report":"../../growth/external-signals-2026-10-30.ru.md","web_queries":sum(x["web_queries"] for x in SCOPES.values()),"captured_gets":len(captures),"native_search_queries_included_in_gets":5,"branches":branches,"validation":{"json_parse_errors":parse_errors,"missing_capture_hashes":missing,"missing_local_report_links":missing_links,"hashed_captures_verified":sum(bool(x.get("verified_body_files")) for x in captures)},"captures":captures}
(ROOT/"audit-index.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:out[k] for k in ["web_queries","captured_gets","validation"]},ensure_ascii=False,indent=2))
if parse_errors or missing or missing_links:raise SystemExit(1)

