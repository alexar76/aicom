"""Offline inputs behind the WARDEN article's renderer comparison.

This calls the real gateway function; it is not a live server survey or benchmark.
Run with aimarket-hub's Python environment from any working directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "aimarket-hub"))

from aimarket_hub import mcp_gateway as gateway  # noqa: E402
from aimarket_hub import sandbox_trials as trials  # noqa: E402


def definition(spec, price, quota, enabled=True):
    with (
        patch.object(trials, "sandbox_enabled", return_value=enabled),
        patch.object(trials, "max_per_visitor", return_value=quota),
    ):
        return gateway._direct_tool_definition(
            spec, SimpleNamespace(price_per_call_usd=price)
        )


inputs = [
    ("Baseline", 0.001, 5, True),
    ("Price edit", 0.05, 5, True),
    ("Allowance edit", 0.001, 9, True),
    ("Paid to free", 0.0, 5, True),
    ("Trial switched off", 0.001, 5, False),
]
spec = gateway._DIRECT_BY_NAME["weather_now"]
baseline = definition(spec, 0.001, 5)
cases = []
for label, price, quota, enabled in inputs:
    current = definition(spec, price, quota, enabled)
    cases.append({
        "case": label,
        "price_usd": price,
        "trial_quota": quota,
        "trial_enabled": enabled,
        "equal_to_baseline": current == baseline,
        "definition": current,
    })
assert [r["equal_to_baseline"] for r in cases] == [True, True, True, False, False]

invariants = []
for direct in gateway.DIRECT_TOOLS:
    a = definition(direct, 0.001, 5)
    b = definition(direct, 0.05, 5)
    c = definition(direct, 0.001, 9)
    assert a == b == c, direct["name"]
    invariants.append({"tool": direct["name"], "positive_price_and_quota_invariant": True})

sources = [
    "aimarket-hub/aimarket_hub/mcp_gateway.py",
    "aimarket-hub/tests/test_mcp_stranger_path.py",
    "argus/src/mcp/host.ts",
    "argus/src/channels/http.ts",
    "argus/src/cli/commands/warden.ts",
]
result = {
    "mode": "offline renderer fixture, not a production measurement",
    "comparison": "full Python dictionary equality; no diagnostic hash substitutes for a pin",
    "tool": spec["name"],
    "cases": cases,
    "all_direct_tools": invariants,
    "sources": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}
                for p in sources],
}
(HERE / "fixture-results.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"cases": len(cases), "direct_tools": len(invariants),
                  "equal_to_baseline": [r["equal_to_baseline"] for r in cases]}))
