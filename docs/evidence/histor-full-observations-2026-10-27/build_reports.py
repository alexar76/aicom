"""Rebuild five-language reports from frozen complete captures; no network or package execution."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = ROOT / "output/histor-full-observations-2026-10-27"
sys.path.insert(0, str(ROOT / "histor"))

from histor.upgrade_brief import _validate_snapshot
from histor.upgrade_brief_i18n import MESSAGES

HUB = "https://modelmarket.dev/mcp"
WARDEN = "npm:@aimarket/warden"
ORACLE = "pypi:aimarket-oracle-gateway"
PACKAGER = "pypi:aimarket-mcp-packager"
LANGUAGES = ("en", "ru", "es", "fr", "zh")
CURRENT = {
    HUB: ("hub/baseline.json", "hub/recheck.json"),
    WARDEN: ("warden/current-baseline.json", "warden/current-recheck.json"),
    ORACLE: ("python-packages/snapshots/current-oracle-gateway-baseline.json", "python-packages/snapshots/current-oracle-gateway-recheck.json"),
    PACKAGER: ("python-packages/snapshots/current-packager-baseline.json", "python-packages/snapshots/current-packager-recheck.json"),
}
REPLAYS = {
    WARDEN: ("warden/replay-before.json", "warden/current-baseline.json"),
    ORACLE: ("python-packages/snapshots/upgrade-oracle-gateway-before.json", "python-packages/snapshots/upgrade-oracle-gateway-after.json"),
    PACKAGER: ("python-packages/snapshots/upgrade-packager-before.json", "python-packages/snapshots/upgrade-packager-after.json"),
}
TITLES = {
    "current": {
        "en": "Current full MCP observations — baseline and recheck",
        "ru": "Полные текущие наблюдения MCP — базовый снимок и перепроверка",
        "es": "Observaciones MCP actuales completas — referencia y comprobación",
        "fr": "Observations MCP actuelles complètes — référence et nouvelle vérification",
        "zh": "当前完整 MCP 观测 基线与复核",
    },
    "package-replays": {
        "en": "Controlled MCP package release comparisons",
        "ru": "Контролируемое сравнение выпусков MCP пакетов",
        "es": "Comparación controlada de versiones de paquetes MCP",
        "fr": "Comparaison contrôlée des versions de paquets MCP",
        "zh": "MCP 软件包版本的受控比较",
    },
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized(report):
    report = copy.deepcopy(report)
    for key in ("title", "language", "watchlistSha256"):
        report.pop(key, None)
    report["limits"] = [None for _ in report["limits"]]
    for dep in report["dependencies"]:
        for tool in dep["selectedTools"]:
            tool["retest"] = [None for _ in tool["retest"]]
        for flow in dep["workflows"]:
            flow.pop("description")
            for item in flow["retest"]:
                item["check"] = None
    return report


def run(watchlist, target, language):
    command = [sys.executable, "-S", "-B", "-m", "histor", "upgrade-brief", "--watchlist", str(watchlist),
               "--out-dir", str(target)]
    if language:
        command += ["--lang", language]
    previous = None
    for _ in range(2):
        result = subprocess.run(command, cwd=ROOT / "histor", capture_output=True, text=True, timeout=30, check=False)
        require(result.returncode == 0, result.stderr)
        output = {name: (target / name).read_bytes() for name in ("report.json", "report.md")}
        require(previous is None or output == previous, "report output is not repeatable")
        previous = output
    return read(target / "report.json")


def check_findings(track, report):
    rows = {dep["id"]: dep for dep in report["dependencies"]}
    if track == "current":
        require(report["summary"] == {"changed": 0, "unchanged": 4, "context_changed": 0, "unknown": 0}, "current summary differs")
        require(set(rows) == set(CURRENT), "current dependencies differ")
        for dep in rows.values():
            require(dep["status"] == "unchanged" and dep["comparability"] == "comparable"
                    and dep["fieldCoverage"] == "full" and not dep["limitations"], "current observation pair is incomplete")
            require(all(flow["status"] == "no_observed_change" and not flow["retest"] for flow in dep["workflows"]), "current workflow changed")
        for target, count in ((HUB, 13), (WARDEN, 9), (ORACLE, 36), (PACKAGER, 3)):
            require(rows[target]["toolSet"]["beforeCount"] == rows[target]["toolSet"]["afterCount"] == count, "current tool count differs")
    else:
        require(report["summary"] == {"changed": 1, "unchanged": 1, "context_changed": 0, "unknown": 1}, "replay summary differs")
        require(rows[WARDEN]["status"] == "changed" and rows[WARDEN]["comparability"] == "comparable"
                and rows[WARDEN]["fieldCoverage"] == "full", "WARDEN replay must be full and changed")
        tools = {tool["name"]: tool for tool in rows[WARDEN]["selectedTools"]}
        require(tools["approve_mcp_server"]["changes"] == ["inputSchema"], "WARDEN approve changes differ")
        require(tools["status_mcp_server"]["changes"] == ["inputSchema", "outputSchema"], "WARDEN status changes differ")
        require(all(tool["requiredAdded"] == [] and tool["requiredRemoved"] == [] for tool in tools.values()), "required arguments changed")
        require(rows[PACKAGER]["status"] == "unchanged" and rows[PACKAGER]["fieldCoverage"] == "full", "Packager definitions differ")
        require(rows[ORACLE]["status"] == "unknown" and rows[ORACLE]["fieldCoverage"] == "none"
                and rows[ORACLE]["sources"]["before"]["status"] == "failed", "Oracle failure must remain unknown")
        codes = {values[report["language"]]: key for key, values in MESSAGES.items() if key.startswith("check_")}
        expected_flows = {
            "warden-origin-review": [["status_mcp_server", "check_input"], ["status_mcp_server", "check_output"]],
            "warden-review-to-approval": [["approve_mcp_server", "check_input"], ["status_mcp_server", "check_input"], ["status_mcp_server", "check_output"]],
            "metis-oracle-catalog": [[None, "check_context"], ["list_oracle_capabilities", "check_observations_missing"]],
            "metis-package-capability": [],
        }
        actual_flows = {flow["id"]: [[item["tool"], codes[item["check"]]] for item in flow["retest"]]
                        for dep in rows.values() for flow in dep["workflows"]}
        require(actual_flows == expected_flows, "package replay checklist meanings differ")


def main():
    template = read(ROOT / "output/histor-upgrade-brief-real-2026-10-27/bundle/watchlist.json")
    labels_path = ROOT / "docs/evidence/histor-real-upgrade-i18n-2026-10-27/labels.json"
    labels = read(labels_path)
    capture_paths = {HERE / name for pairs in (CURRENT, REPLAYS) for pair in pairs.values() for name in pair}
    frozen = {path: digest(path) for path in capture_paths}
    frozen[labels_path] = digest(labels_path)
    summaries = {}
    for track, pairs in (("current", CURRENT), ("package-replays", REPLAYS)):
        bundle = OUTPUT / track / "bundle"
        deps = []
        for dep in template["dependencies"]:
            if dep["id"] not in pairs:
                continue
            dep = copy.deepcopy(dep)
            for side, source in zip(("before", "after"), pairs[dep["id"]], strict=True):
                src = HERE / source
                value = read(src)
                _validate_snapshot(value)
                require(value["targetId"] == dep["id"], "capture target differs")
                if value["status"] == "ok":
                    require(value.get("protocol") and value.get("launch") and value["extrasCoverage"] == "observed", "successful capture lacks full context")
                relative = "snapshots/" + src.parent.name + "-" + src.name
                target = bundle / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(src.read_bytes())
                dep[side] = relative
            deps.append(dep)
        first = None
        english = None
        for language in LANGUAGES:
            localized = copy.deepcopy(deps)
            for dep in localized:
                for flow in dep["workflows"]:
                    flow["description"] = labels[language]["workflows"][flow["id"]]
            watchlist = bundle / ("watchlist.json" if language == "en" else f"watchlist.{language}.json")
            save(watchlist, {"format": template["format"], "title": TITLES[track][language], "dependencies": localized})
            report = run(watchlist, OUTPUT / track / language, language)
            require(report["language"] == language, "report language differs")
            check_findings(track, report)
            technical = normalized(report)
            require(first is None or first == technical, "analysis changed with language")
            first = technical
            if language == "en":
                english = report
            priority = {"changed": 0, "context_changed": 1, "unknown": 2, "unchanged": 3}
            expected_checks = [(item["tool"] + ": " if item["tool"] else "") + item["check"]
                               for dep in sorted(report["dependencies"], key=lambda row: (priority[row["status"]], row["id"]))
                               for flow in dep["workflows"] for item in flow["retest"]]
            markdown = (OUTPUT / track / language / "report.md").read_text(encoding="utf-8")
            actual_checks = [html.unescape(re.sub(r"\\([\\`*_{}\[\]()#+.!|>-])", r"\1", line[6:]))
                             for line in markdown.splitlines() if line.startswith("- [ ] ")]
            require(actual_checks == expected_checks, "Markdown checklists differ from JSON")
            require(MESSAGES["summary_header"][language] in markdown, "localized summary missing")
            print(json.dumps({"track": track, "language": language, "summary": report["summary"], "checks": len(expected_checks), "verified": True}))
        default = run(bundle / "watchlist.json", OUTPUT / track, None)
        require(default == english and default["language"] == "en", "default is not English")
        for name in ("report.md", "report.json"):
            require((OUTPUT / track / name).read_bytes() == (OUTPUT / track / "en" / name).read_bytes(), "default differs from explicit English")
        summaries[track] = english["summary"]
    require(all(digest(path) == sha for path, sha in frozen.items()), "capture evidence was changed")
    reports = sorted(OUTPUT.glob("*/*/report.*")) + sorted(OUTPUT.glob("*/report.*"))
    save(HERE / "report-verification.json", {
        "date": "2026-10-27", "defaultLanguage": "en", "languages": LANGUAGES, "offlineCliRuns": 24,
        "summaries": summaries, "captureInputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha} for p, sha in sorted(frozen.items())],
        "captureCount": len(capture_paths), "successfulCaptures": sum(read(p)["status"] == "ok" for p in capture_paths),
        "repeatableOutput": True, "identicalTechnicalConclusionsAcrossLanguages": True,
        "markdownChecklistsMatchJson": True, "unchangedCaptureInputs": True, "defaultEqualsExplicitEnglish": True,
        "historicalObservationsBackfilled": False,
        "reports": [{"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for p in reports],
    })
    print("PASS: 24 offline report runs, current full pairs and controlled package replays kept separate")


if __name__ == "__main__":
    main()
