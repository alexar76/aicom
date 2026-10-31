from read_public import get,ROOT
from concurrent.futures import ThreadPoolExecutor
import json
sha="ef124a40d592bf149fab93fb632a4aaf688a04fa"
tasks=[("enterprise-"+key,"https://raw.githubusercontent.com/th3artfuldodger/enterprise-factory/"+sha+"/"+path) for key,path in [
("pytest-runner","scripts/run_factory_pytest.sh"),
("fetch-satellites","scripts/ci_fetch_factory_test_deps.sh"),
("install-satellites","scripts/ci_install_factory_test_deps.sh")]]
tasks.append(("russian-digest-candidate","https://ai-academy.ink/post/ai-digest-2026-07-31/"))
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
(ROOT/"http-source-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps([{"name":r["name"],"status":r.get("status"),"bytes":r.get("bytes")} for r in rows],indent=2))

