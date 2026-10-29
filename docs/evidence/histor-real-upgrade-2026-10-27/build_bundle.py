"""Build a local watchlist from saved public HISTOR responses; no network or tool calls.

Every projected observation cites a timeline row or an explicit alternate-profile capture. Missing protocol, launch,
package version and historical extras stay unknown. Live package self-tests are
context only and are never substituted for HISTOR observations.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "histor"))

from histor.subject import tool_set_digest
from histor.upgrade_brief import build_report
from histor.upgrade_brief_cli import main as brief_main

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUTPUT = ROOT / "output/histor-upgrade-brief-real-2026-10-27"
BUNDLE = OUTPUT / "bundle"


def read(path: Path):
    return json.loads(path.read_text())


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


def observation(target: str, row: dict, tools: list | None) -> dict:
    # 'from' belongs to the first captured row of a collapsed timeline interval. Using
    # 'until' could incorrectly attach the first row's serverVersion to a later capture.
    value = {"format": "histor.upgrade-observation/v1", "targetId": target,
             "status": "ok" if row["status"] == "ok" and tools is not None else "failed",
             "observedAt": row["from"], "packageVersion": row.get("packageVersion"),
             "serverName": row.get("serverName"), "serverVersion": row.get("serverVersion"),
             "protocol": row.get("protocolVersion"), "launch": row.get("launch"),
             "extrasCoverage": "unknown"}
    if tools is not None:
        value["tools"] = tools
    return value


def main() -> None:
    dependencies = []
    provenance = []
    selection = {
        "hub": {"tools": ["market_search", "market_invoke"], "workflows": [
            {"id": "hub-search-relevance", "description": "Выбрать подходящую capability по поиску Hub и сохранить relevance и note",
             "tools": ["market_search"]},
            {"id": "hub-search-to-invoke", "description": "Передать точные product_id, capability_id и source_hub из поиска в вызов",
             "tools": ["market_search", "market_invoke"]}]},
        "warden": {"tools": ["status_mcp_server", "approve_mcp_server"], "workflows": [
            {"id": "warden-origin-review", "description": "Показать оператору server_info и блок origin перед пересмотром approval",
             "tools": ["status_mcp_server"]},
            {"id": "warden-review-to-approval", "description": "Сохранить reviewed hashes и previousRevision при передаче review в approval",
             "tools": ["status_mcp_server", "approve_mcp_server"]}]},
    }
    for name, personal in selection.items():
        detail = read(RAW / f"server-{name}.json")
        change = read(RAW / f"change-{name}.json")
        server = detail["server"]
        paths = {}
        for side, field in (("before", "from_toolset"), ("after", "to_toolset")):
            tools = read(RAW / f"toolset-{name}-{side}.json")
            if isinstance(tools, dict):
                tools = tools["tools"]
            digest, _ = tool_set_digest(tools)
            assert digest == change[field], f"{name} {side}: content-address mismatch"
            rows = [row for row in detail["timeline"] if row["status"] == "ok" and row["toolSetDigest"] == digest]
            assert rows, f"{name} {side}: no matching observation"
            # Prefer the latest separately retained observation of the matching contract.
            row = max(rows, key=lambda item: item["from"])
            paths[side] = f"snapshots/{name}-{side}.json"
            save(BUNDLE / paths[side], observation(server["endpoint"], row, tools))
            provenance.append({"dependency": server["endpoint"], "side": side, "toolSetDigest": digest,
                "sourceDetail": f"raw/server-{name}.json", "sourceTools": f"raw/toolset-{name}-{side}.json",
                "timelineFrom": row["from"], "timelineUntil": row["until"], "timelineCount": row["count"],
                "eventId": change["id"], "eventObservedAt": change["observed_at"],
                "historicalExtrasCompared": False, "protocolGuessed": False, "launchGuessed": False})
        dependencies.append({"id": server["endpoint"], **paths, **personal})

    for name, tool, flow_id, description in (
        ("oracle-gateway", "list_oracle_capabilities", "metis-oracle-catalog", "Получить каталог oracle capabilities через Metis перед выбором платного оракула"),
        ("packager", "package_capability", "metis-package-capability", "Получить manifest и интерактивную Docker connection string из capability specification"),
    ):
        detail = read(RAW / f"server-{name}.json")
        server = detail["server"]
        if name == "packager":
            legacy = server["packageSignals"]["legacy"]
            assert legacy["status"] == "ok" and legacy["supplied"] == {"pins": ["mcp<2"]}
            tools = read(RAW / "toolset-packager-pinned-baseline.json")
            if isinstance(tools, dict):
                tools = tools["tools"]
            actual, _ = tool_set_digest(tools)
            assert actual == legacy["toolSetDigest"]
            row = {"from": legacy["observedAt"], "status": "ok", "packageVersion": legacy["version"],
                   "launch": {"conditions": legacy["conditions"], "supplied": legacy["supplied"]}}
            before = "snapshots/packager-pinned-baseline.json"
            save(BUNDLE / before, observation(server["endpoint"], row, tools))
            (BUNDLE / "snapshots/packager-last-failed.json").unlink(missing_ok=True)
            dependencies.append({"id": server["endpoint"], "before": before, "after": None, "tools": [tool],
                "workflows": [{"id": flow_id, "description": description, "tools": [tool]}]})
            provenance.append({"dependency": server["endpoint"], "side": "before", "sourceDetail": f"raw/server-{name}.json",
                "sourcePointer": "server.packageSignals.legacy", "observedAt": legacy["observedAt"],
                "sourceTools": "raw/toolset-packager-pinned-baseline.json", "toolSetDigest": actual,
                "packageVersion": legacy["version"], "alternateProfile": legacy["supplied"],
                "currentProfileNotAssumedEquivalent": True, "successfulPairAvailable": False})
            continue
        row = max(detail["timeline"], key=lambda item: item["from"])
        assert row["status"] != "ok" and row.get("toolSetDigest") is None
        after = f"snapshots/{name}-last-failed.json"
        save(BUNDLE / after, observation(server["endpoint"], row, None))
        dependencies.append({"id": server["endpoint"], "before": None, "after": after, "tools": [tool],
            "workflows": [{"id": flow_id, "description": description, "tools": [tool]}]})
        provenance.append({"dependency": server["endpoint"], "side": "after", "sourceDetail": f"raw/server-{name}.json",
            "timelineFrom": row["from"], "timelineUntil": row["until"], "timelineCount": row["count"],
            "observedStatus": row["status"], "cardPackageVersion": server.get("packageVersion"),
            "cardVersionNotSubstitutedForObservation": True, "successfulPairAvailable": False})

    watchlist = BUNDLE / "watchlist.json"
    save(watchlist, {"format": "histor.upgrade-watchlist/v1", "title": "MCP экосистемы alexar76 — реальные наблюдения HISTOR", "dependencies": dependencies})
    save(HERE / "projection-provenance.json", {"format": "histor.real-upgrade-projection/v1", "observations": provenance,
        "limits": ["Only saved public HISTOR responses are projected into observations",
                   "Current extras are not copied onto historical core toolsets",
                   "Self-reported serverVersion is never substituted for packageVersion",
                   "No production configuration, tool calls, payment or package execution"]})
    assert brief_main(["--watchlist", str(watchlist), "--out-dir", str(OUTPUT)]) == 0
    report = build_report(watchlist)
    assert len(report["dependencies"]) == 4
    assert sum(row["observedChanges"] is True for row in report["dependencies"]) == 2
    assert all(row["status"] == "unknown" for row in report["dependencies"]), "Do not certify incomplete historical context"
    for name in ("report.json", "report.md"):
        (HERE / name).write_bytes((OUTPUT / name).read_bytes())
    raw_hashes = [{"file": str(path.relative_to(HERE)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for path in sorted(RAW.glob("*.json"))]
    save(HERE / "input-integrity.json", {"files": raw_hashes, "toolsetContentAddressesVerified": 5,
        "signedManifestVerified": False, "reportSummary": report["summary"]})
    print(json.dumps({"dependencies": 4, "realCoreComparisons": 2, "incompleteHistoryCases": 2,
                      "toolsetContentAddressesVerified": 5, "summary": report["summary"]}))


if __name__ == "__main__":
    main()
