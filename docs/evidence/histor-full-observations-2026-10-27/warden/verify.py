"""Verify complete WARDEN captures and reproduce replay/stability comparisons offline."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "histor"))


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from histor.subject import tool_set_digest
    from histor.upgrade_brief import build_report

    labels = ("replay-before", "current-baseline", "current-recheck")
    captures = {label: read(HERE / f"{label}.json") for label in labels}
    for label, snapshot in captures.items():
        provenance = read(HERE / f"{label}-provenance.json")
        wire = read(HERE / f"{label}-wire.json")
        assert provenance["sha256"] == digest(HERE / f"{label}.json")
        assert wire["toolCalls"] == 0 and wire["processExitCode"] == 0
        assert set(wire["methods"]) <= {"server/discover", "initialize", "notifications/initialized", "tools/list"}
        assert snapshot["status"] == "ok" and snapshot["extrasCoverage"] == "observed"
        assert snapshot["protocol"] == "2025-03-26" and len(snapshot["tools"]) == 9
        assert provenance["stateDirectoryWasEmptyAfterCapture"] and provenance["networkDeniedBySandbox"]
    flows = [{"id": "warden-origin-review", "description": "Review server origin and reported versions", "tools": ["status_mcp_server"]},
             {"id": "warden-review-to-approval", "description": "Preserve reviewed hashes and revision during approval", "tools": ["status_mcp_server", "approve_mcp_server"]}]
    comparisons = []
    for name, before, after in (("replay", "replay-before.json", "current-baseline.json"),
                                ("stability", "current-baseline.json", "current-recheck.json")):
        watchlist = {"format": "histor.upgrade-watchlist/v1", "title": "WARDEN complete local source observations",
                     "dependencies": [{"id": "npm:@aimarket/warden", "before": before, "after": after,
                                       "tools": ["status_mcp_server", "approve_mcp_server"], "workflows": flows}]}
        save(f"watchlist-{name}.json", watchlist)
        report = build_report(HERE / f"watchlist-{name}.json")
        row = report["dependencies"][0]
        save(f"comparison-{name}.json", report)
        assert row["comparability"] == "comparable" and row["fieldCoverage"] == "full"
        assert row["status"] == ("changed" if name == "replay" else "unchanged")
        comparisons.append({"comparison": name, "status": row["status"], "comparability": row["comparability"],
                            "fieldCoverage": row["fieldCoverage"],
                            "protocols": [source["protocol"] for source in row["sources"].values()],
                            "selectedTools": [{key: tool.get(key) for key in ("name", "status", "changes", "requiredAdded", "inputSchemaPaths", "outputSchemaPaths")}
                                              for tool in row["selectedTools"]]})
    assert captures["current-baseline"]["tools"] == captures["current-recheck"]["tools"]
    change = read(ROOT / "docs/evidence/histor-real-upgrade-2026-10-27/raw/change-warden.json")
    matches = []
    for label, side in (("replay-before", "from_toolset"), ("current-baseline", "to_toolset")):
        actual, _ = tool_set_digest(captures[label]["tools"])
        assert actual == change[side]
        matches.append({"capture": label, "fullCaptureMtlCoreDigest": actual, "originalRecordedDigest": change[side],
                        "matchesHistoricalCoreDigest": True})
    save("verification.json", {"comparisons": comparisons, "historicalCoreDigestChecks": matches,
                              "currentToolsIdenticalOnRecheck": True, "historicalOriginalMetadataRecovered": False,
                              "replayedSourceNotPublishedPackage": True, "allCapturesToolsCalls": 0,
                              "allCapturesNetworkDenied": True})
    paths = [HERE / "capture.py", HERE / "verify.py", ROOT / "histor/histor/toolcost_cli.py",
             ROOT / "histor/histor/mcpclient.py", ROOT / "histor/histor/upgrade_brief.py", HERE / "build-provenance.json"]
    paths += [HERE / f"{label}{suffix}.json" for label in labels for suffix in ("", "-provenance", "-wire")]
    save("source-integrity.json", {"files": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)} for path in paths]})
    print("PASS: three complete captures, changed source replay, unchanged current recheck, two matching historical core digests")


if __name__ == "__main__":
    main()
