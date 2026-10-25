#!/usr/bin/env python3
"""Read-only reconstruction of the 2026-10-20 article's cohort and digit count.

Usage: python3 cohort_readonly.py SNAPSHOT_DIR
Reads only manifest.json, servers.jsonl.gz and changes.jsonl.gz; writes JSON to stdout.
The old 2,719 heuristic uses saved word-diff operations, not whole-string normalization.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import re


FIRST_DAY_END = "2026-09-24T23:59:59Z"
OLD_DIGIT_EDIT = re.compile(r"^[\s\d.,:\-/]*$")


def rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            yield json.loads(line)


def reproduce(snapshot: Path) -> dict:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    base = {
        row["id"]
        for row in rows(snapshot / "servers.jsonl.gz")
        if row["transport"] != "stdio"
        and not row["delisted"]
        and row["toolSetDigest"] is not None
        and row["firstPinned"] is not None
        and row["firstPinned"] <= FIRST_DAY_END
    }
    changed_full = set()
    description_cohort = set()
    base_events = []
    old_digits_only = 0
    total_events = 0
    for row in rows(snapshot / "changes.jsonl.gz"):
        total_events += 1
        summary = json.loads(row["summaryJson"])
        modified = summary.get("modified") or []
        fields = {field for tool in modified for field in (tool.get("fields") or {})}
        added_removed = bool(summary.get("added") or summary.get("removed"))
        # Reproduce the original count exactly: descriptions alone, with actual
        # changed digits; six whitespace-only events otherwise also match.
        if fields == {"description"} and not added_removed:
            edits = [
                value
                for tool in modified
                for operation, value in tool["fields"]["description"]
                if operation in ("+", "-")
            ]
            if all(OLD_DIGIT_EDIT.fullmatch(value) for value in edits) and any(
                char.isdigit() for value in edits for char in value
            ):
                old_digits_only += 1
        if row["serverId"] not in base:
            continue
        if summary.get("detail") == "full":
            changed_full.add(row["serverId"])
        has_description = "description" in fields
        if has_description:
            description_cohort.add(row["serverId"])
        base_events.append({
            "id": row["id"], "serverId": row["serverId"],
            "observedAt": row["observedAt"], "detail": summary.get("detail"),
            "hasDescription": has_description,
            "from": row.get("fromToolSetDigest"), "to": row.get("toToolSetDigest"),
        })

    selected = [row for row in base_events if row["serverId"] in description_cohort]
    per_server = defaultdict(list)
    for row in selected:
        per_server[row["serverId"]].append(row)
    digests = {row[side] for row in selected for side in ("from", "to") if row[side]}
    gaps = []
    comparisons = 0
    null_comparisons = 0
    for server_id, events in sorted(per_server.items()):
        events.sort(key=lambda row: (row["observedAt"], int(row["id"])))
        for previous, current in zip(events, events[1:]):
            comparisons += 1
            null_comparisons += previous["to"] is None or current["from"] is None
            if previous["to"] != current["from"]:
                gaps.append({
                    "serverId": server_id,
                    "previousEventId": previous["id"], "nextEventId": current["id"],
                    "previousObservedAt": previous["observedAt"],
                    "nextObservedAt": current["observedAt"],
                    "previousTo": previous["to"], "nextFrom": current["from"],
                })

    return {
        "snapshotCreatedAt": manifest["createdAt"],
        "changesFrom": manifest["changesFrom"], "changesUntil": manifest["changesUntil"],
        "baseCutoff": FIRST_DAY_END,
        "baseline": {
            "allSnapshotEvents": total_events,
            "baseRemoteServers": len(base),
            "changedFullRemoteServers": len(changed_full),
            "descriptionCohortServers": len(description_cohort),
            "descriptionCohortDescriptionEvents": sum(row["hasDescription"] for row in selected),
            "descriptionCohortEvents": len(selected),
            "oldDigitsOnlyDescriptionEventsAllUnits": old_digits_only,
        },
        "cohortDetails": {
            "detail": dict(sorted(Counter(str(row["detail"]) for row in selected).items())),
            "nullFrom": sum(row["from"] is None for row in selected),
            "nullTo": sum(row["to"] is None for row in selected),
            "bothNull": sum(row["from"] is None and row["to"] is None for row in selected),
            "emptyStringFrom": sum(row["from"] == "" for row in selected),
            "emptyStringTo": sum(row["to"] == "" for row in selected),
            "bothDigestsPresent": sum(bool(row["from"]) and bool(row["to"]) for row in selected),
            "uniqueRequiredToolsetDigests": len(digests),
            "chronologicalOrdering": "observedAt ascending, numeric event id ascending",
            "chainComparisons": comparisons,
            "chainComparisonsWithNull": null_comparisons,
            "chainComparisonsBothNonNull": comparisons - null_comparisons,
            "chainGaps": len(gaps),
            "chainGapServers": len({gap["serverId"] for gap in gaps}),
            "chainGapExamples": gaps[:10],
        },
        "inputFiles": {
            name: manifest["files"][name]
            for name in ("servers.jsonl.gz", "changes.jsonl.gz", "toolsets.jsonl.gz")
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.snapshot), ensure_ascii=False, indent=2))
