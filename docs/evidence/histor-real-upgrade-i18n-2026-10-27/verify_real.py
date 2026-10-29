"""Reproduce five localized reports from frozen public HISTOR evidence, without network access."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ORIGINAL = ROOT / "docs/evidence/histor-real-upgrade-2026-10-27"
SOURCE_BUNDLE = ROOT / "output/histor-upgrade-brief-real-2026-10-27/bundle"
DEFAULT_OUTPUT = ROOT / "output/histor-upgrade-brief-real-i18n-2026-10-27"
LANGUAGES = ("en", "ru", "es", "fr", "zh")
sys.path.insert(0, str(ROOT / "histor"))

from histor.subject import tool_set_digest
from histor.upgrade_brief_i18n import MESSAGES


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalized(value: dict[str, Any]) -> dict[str, Any]:
    """Ignore localized prose while retaining checklist order, associations and evidence."""
    result = copy.deepcopy(value)
    for field in ("language", "title", "watchlistSha256"):
        result.pop(field, None)
    result["limits"] = [None for _ in result["limits"]]
    for dep in result["dependencies"]:
        for tool in dep["selectedTools"]:
            tool["retest"] = [None for _ in tool["retest"]]
        for flow in dep["workflows"]:
            flow.pop("description")
            for item in flow["retest"]:
                item["check"] = None
    return result


def verify_provenance() -> tuple[dict[str, Any], dict[Path, str]]:
    """Recheck original raw hashes, five content addresses and all six projected snapshots."""
    integrity = read(ORIGINAL / "input-integrity.json")
    tracked = [ORIGINAL / item["file"] for item in integrity["files"]]
    for item, path in zip(integrity["files"], tracked, strict=True):
        require(digest(path) == item["sha256"], "frozen raw evidence hash changed: " + item["file"])
    watchlist = read(SOURCE_BUNDLE / "watchlist.json")
    deps = {dep["id"]: dep for dep in watchlist["dependencies"]}
    projected = read(ORIGINAL / "projection-provenance.json")["observations"]
    require(len(projected) == 6, "expected six provenance records")
    content_addresses = 0
    for origin in projected:
        dep = deps[origin["dependency"]]
        snapshot_path = SOURCE_BUNDLE / dep[origin["side"]]
        snapshot = read(snapshot_path)
        detail = read(ORIGINAL / origin["sourceDetail"])
        tools = None
        if origin.get("sourceTools"):
            tools = read(ORIGINAL / origin["sourceTools"])
            if isinstance(tools, dict):
                tools = tools["tools"]
            actual, _ = tool_set_digest(tools)
            require(actual == origin["toolSetDigest"], "toolset content address differs")
            content_addresses += 1
        if origin.get("sourcePointer") == "server.packageSignals.legacy":
            legacy = detail["server"]["packageSignals"]["legacy"]
            require(legacy["status"] == "ok" and legacy["supplied"] == {"pins": ["mcp<2"]}, "alternate profile changed")
            require(legacy["toolSetDigest"] == origin["toolSetDigest"], "alternate profile digest differs")
            row = {"from": legacy["observedAt"], "status": "ok", "packageVersion": legacy["version"],
                   "launch": {"conditions": legacy["conditions"], "supplied": legacy["supplied"]}}
        else:
            matches = [row for row in detail["timeline"] if row["from"] == origin["timelineFrom"]
                       and row["until"] == origin["timelineUntil"] and row["count"] == origin["timelineCount"]]
            require(len(matches) == 1, "snapshot timeline origin is ambiguous")
            row = matches[0]
            if tools is not None:
                name = "hub" if origin["dependency"].startswith("https://") else "warden"
                change = read(ORIGINAL / f"raw/change-{name}.json")
                field = "from_toolset" if origin["side"] == "before" else "to_toolset"
                require(change["id"] == origin["eventId"] and change[field] == origin["toolSetDigest"], "change record differs")
                require(row["toolSetDigest"] == origin["toolSetDigest"], "timeline toolset differs")
            else:
                require(row["status"] != "ok" and row.get("toolSetDigest") is None, "failed source became successful")
        expected_snapshot = {
            "format": "histor.upgrade-observation/v1", "targetId": origin["dependency"],
            "status": "ok" if row["status"] == "ok" and tools is not None else "failed",
            "observedAt": row["from"], "packageVersion": row.get("packageVersion"),
            "serverName": row.get("serverName"), "serverVersion": row.get("serverVersion"),
            "protocol": row.get("protocolVersion"), "launch": row.get("launch"), "extrasCoverage": "unknown",
        }
        if tools is not None:
            expected_snapshot["tools"] = tools
        require(snapshot == expected_snapshot, "snapshot projection differs from frozen source: " + str(snapshot_path))
        tracked.append(snapshot_path)
    require(content_addresses == 5, "expected five verified content addresses")
    tracked += [SOURCE_BUNDLE / "watchlist.json", ORIGINAL / "report.json", ORIGINAL / "input-integrity.json",
                ORIGINAL / "projection-provenance.json", HERE / "expected.json", HERE / "labels.json"]
    return watchlist, {path: digest(path) for path in tracked}


def findings(report: dict[str, Any], language: str) -> dict[str, Any]:
    check_codes = {values[language]: key for key, values in MESSAGES.items() if key.startswith("check_")}
    return {
        "summary": report["summary"],
        "dependencies": {
            dep["id"]: {
                "fieldCoverage": dep["fieldCoverage"], "observedChanges": dep["observedChanges"],
                "toolCount": dep.get("toolSet", {}).get("beforeCount"),
                "tools": {tool["name"]: tool["changes"] for tool in dep["selectedTools"]},
                "workflows": {flow["id"]: [[item["tool"], check_codes[item["check"]]] for item in flow["retest"]]
                              for flow in dep["workflows"]},
            }
            for dep in report["dependencies"]
        },
    }


def run_report(watchlist: Path, target: Path, language: str | None) -> dict[str, Any]:
    command = [sys.executable, "-S", "-B", "-m", "histor", "upgrade-brief", "--watchlist", str(watchlist),
               "--out-dir", str(target)]
    if language is not None:
        command += ["--lang", language]
    previous = None
    for _ in range(2):
        process = subprocess.run(command, cwd=ROOT / "histor", capture_output=True, text=True, timeout=30, check=False)
        require(process.returncode == 0, process.stderr)
        output = {name: (target / name).read_bytes() for name in ("report.md", "report.json")}
        require(previous is None or output == previous, "repeated report output differs")
        previous = output
    return read(target / "report.json")


def verify(output: Path) -> None:
    require(output.is_relative_to(ROOT / "output") and output != ROOT / "output"
            and not output.is_relative_to(SOURCE_BUNDLE.parent),
            "choose a separate directory inside the workspace output folder")
    watchlist, hashes = verify_provenance()
    labels = read(HERE / "labels.json")
    expected = read(HERE / "expected.json")
    reference = normalized(read(ORIGINAL / "report.json"))
    bundle = output / "bundle"
    for path in sorted((SOURCE_BUNDLE / "snapshots").glob("*.json")):
        target = bundle / "snapshots" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    manifests = {}
    for language in LANGUAGES:
        localized = copy.deepcopy(watchlist)
        localized["title"] = labels[language]["title"]
        for dep in localized["dependencies"]:
            for flow in dep["workflows"]:
                flow["description"] = labels[language]["workflows"][flow["id"]]
        path = bundle / ("watchlist.json" if language == "en" else f"watchlist.{language}.json")
        save(path, localized)
        manifests[language] = path
    generated_inputs = list(bundle.glob("watchlist*.json")) + list((bundle / "snapshots").glob("*.json"))
    hashes.update({path: digest(path) for path in generated_inputs})
    reports = {}
    for language in LANGUAGES:
        report = run_report(manifests[language], output / language, language)
        require(report["language"] == language, "report language differs")
        require(normalized(report) == reference, "analysis, evidence or checklist associations changed with locale")
        require(findings(report, language) == expected, "real findings or checklist meanings differ from expected")
        require(report["title"] == labels[language]["title"], "localized title differs")
        require(report["watchlistSha256"] == "sha256:" + digest(manifests[language]), "watchlist hash differs")
        for dep in report["dependencies"]:
            require(dep["status"] == dep["comparability"] == "unknown", "incomplete evidence became comparable")
            for source in dep["sources"].values():
                if source.get("path"):
                    require(source["sha256"] == "sha256:" + digest(bundle / source["path"]), "snapshot hash differs")
            for flow in dep["workflows"]:
                require(flow["status"] == "unknown", "uncertain workflow became ready")
                require(flow["description"] == labels[language]["workflows"][flow["id"]], "workflow description differs")
        text = (output / language / "report.md").read_text(encoding="utf-8")
        require(MESSAGES["summary_header"][language] in text, "localized summary header missing")
        require(MESSAGES["status_unknown_changes"][language] in text, "core-only change uncertainty missing")
        markdown_checks = [html.unescape(re.sub(r"\\([\\`*_{}\[\]()#+.!|>-])", r"\1", line[6:]))
                           for line in text.splitlines() if line.startswith("- [ ] ")]
        json_checks = [(item["tool"] + ": " if item["tool"] else "") + item["check"]
                       for dep in report["dependencies"] for flow in dep["workflows"] for item in flow["retest"]]
        require(markdown_checks == json_checks and len(markdown_checks) == 21,
                "Markdown checklist differs from JSON in text, tool association or order")
        reports[language] = report
        print(f"PASS {language}: 4 dependencies, 6 workflows, 21 equivalent checks; all comparison limits retained")
    default = run_report(manifests["en"], output, None)
    require(default == reports["en"], "omitting --lang does not produce English")
    for name in ("report.md", "report.json"):
        require((output / name).read_bytes() == (output / "en" / name).read_bytes(), "default bytes differ from explicit English")
    require(all(digest(path) == value for path, value in hashes.items()), "source or generated bundle inputs changed")
    result = {
        "date": "2026-10-27", "source": "Frozen public HISTOR responses collected earlier on 2026-10-27; no fresh scan",
        "defaultLanguage": "en", "languages": list(LANGUAGES), "cliRuns": 12,
        "dependencies": 4, "workflows": 6, "checklistItemsPerLocale": 21,
        "summary": default["summary"], "identicalAnalysisAndChecklistMeanings": True,
        "markdownChecklistsMatchJson": True,
        "repeatableOutput": True, "unchangedInputs": True, "defaultEqualsExplicitEnglish": True,
        "rawFilesVerified": 21, "contentAddressesVerified": 5, "snapshotProjectionsVerified": 6,
        "signaturesVerified": False,
        "inputs": [{"path": str(path.relative_to(ROOT)), "sha256": value} for path, value in hashes.items()],
        "reports": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
                    for path in sorted(output.glob("*/report.*")) + sorted(output.glob("report.*"))],
    }
    save(HERE / "verification.json", result)
    print("PASS default en: 12 offline runs, 21 raw hashes, 5 content addresses, 6 source projections, unchanged inputs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        verify(args.out_dir.resolve())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
