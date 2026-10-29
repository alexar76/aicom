"""Join captured public historical version pairs to the fixed snapshot cohort."""
from collections import Counter, defaultdict
from pathlib import Path
import gzip
import json

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
SNAP = ROOT / "artifacts/histor-zenodo-2026-10-20"

def rows(path):
    with gzip.open(path, "rt") as stream:
        yield from (json.loads(line) for line in stream)

servers = {r["id"]: r for r in rows(SNAP / "servers.jsonl.gz")}
versions = {r["id"]: r for r in rows(HERE / "live-version-pairs.jsonl.gz")}
registry_same = set(json.loads((HERE / "same-ids-independent.json").read_text()))
registry_names = {r["name"] for r in rows(ROOT.parent / "PromoMaterials/outreach/acs38-same-version-2026-10-28/registry-all-2026-10-28.jsonl.gz")}
counts = Counter()
times = defaultdict(list)
mismatches = []
missing_ids = []
null_registry = Counter()
changes = list(rows(SNAP / "changes.jsonl.gz"))
first_change = {}
for c in changes:
    first_change[c["serverId"]] = min(first_change.get(c["serverId"], c["id"]), c["id"])
for c in changes:
    s = servers[c["serverId"]]
    if not s["endpoint"].startswith("https://"):
        continue
    counts["remoteChanges"] += 1
    v = versions[c["id"]]
    if v["target_id"] != c["serverId"] or v["observed_at"] != c["observedAt"]:
        mismatches.append(c["id"])
    times[(c["serverId"], c["observedAt"])].append(c["id"])
    before, after = v.get("from_server_version"), v.get("to_server_version")
    null_registry["fromMissing"] += v.get("from_registry_version") is None
    null_registry["toMissing"] += v.get("to_registry_version") is None
    if not before or not after:
        missing_ids.append(c["id"])
        continue
    counts["serverVersionsKnown"] += 1
    same = before == after
    counts["serverVersionUnchanged"] += same
    summary = json.loads(c["summaryJson"])
    if same and summary.get("detail") == "full":
        counts["unchangedServerVersionFullDetail"] += 1
        mods = summary.get("modified") or []
        if mods and not summary.get("added") and not summary.get("removed") and all(set(m["fields"]) == {"description"} for m in mods):
            counts["unchangedServerVersionDescriptionOnly"] += 1
    # Registry-judged cohort excludes names absent from export plus one without first pin.
    if s["name"] in registry_names and (s.get("firstPinned") or c["id"] != first_change[c["serverId"]]):
        counts["bothCriteriaJudged"] += 1
        counts["bothCriteriaMet"] += same and c["id"] in registry_same

result = {"counts": dict(counts), "identityMismatches": mismatches,
          "missingServerVersionIds": missing_ids,
          "duplicateChangeTimes": [{"targetId": k[0], "observedAt": k[1], "ids": ids,
                                    "pairs": [versions[i] for i in ids]}
                                   for k, ids in times.items() if len(ids) > 1],
          "historicalRegistryFields": dict(null_registry)}
(HERE / "live-version-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "missingServerVersionIds"}, indent=2))
