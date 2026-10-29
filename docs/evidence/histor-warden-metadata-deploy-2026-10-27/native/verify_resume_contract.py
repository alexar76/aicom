"""Check continuation completion races offline; no API calls or native operations."""

import copy
import json
import runpy
from pathlib import Path

root = Path(__file__).resolve().parent
module = runpy.run_path(str(root / "run-native-release-resume.py"), run_name="offline_review")
check = module["continue_existing_crawl"]
cycle = "2026-10-27T16:56:37Z"
old = {"id": 100, "cycle": cycle, "finishedAt": None, "errorPresent": False}
before = {"running": True, "run": old, "classifierBudget": 0, "packageBudget": 8000,
          "attemptedCount": 0, "packageAttempts": 0, "planHash": None}


def forbidden(*args, **kwargs):
    raise AssertionError("Offline completion cases must never request an API operation")


check.__globals__["inside"] = forbidden
results = []
for finished in (False, True):
    after = {"running": not finished, "run": {"id": 101, "cycle": cycle,
             "finishedAt": "2026-10-27T17:10:00Z" if finished else None,
             "errorPresent": False, "resumedFrom": 100, "classified": 0},
             "reference": {**old, "finishedAt": "2026-10-27T17:09:00Z", "errorPresent": True,
                           "interrupted": True},
             "resume": None if finished else {"runs": [100]},
             "ancestry": {"run_id": 100, "cycle_started_at": cycle, "runs": [100], "classified": 0},
             **{key: before[key] for key in ("classifierBudget", "packageBudget", "attemptedCount", "packageAttempts", "planHash")}}
    check.__globals__["crawl_snapshot"] = lambda reference_id, value=after: copy.deepcopy(value)
    result = check(copy.deepcopy(before))
    assert result["sameCycle"] and result["completed"] is finished
    results.append({"case": "resumed-completed" if finished else "resumed-active", "passed": True})

completed_original = {"reference": {**old, "finishedAt": "2026-10-27T17:09:00Z", "errorPresent": False}}
check.__globals__["crawl_snapshot"] = lambda reference_id: copy.deepcopy(completed_original)
result = check(copy.deepcopy(before))
assert result["previousCycleCompleted"] and result["fallbackPost"] is False
results.append({"case": "original-completed-during-restart", "passed": True})
proof = {"cases": results, "apiCalls": 0, "nativeOperations": 0, "passed": True}
(root / "resume-contract-validation.json").write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof, indent=2))
