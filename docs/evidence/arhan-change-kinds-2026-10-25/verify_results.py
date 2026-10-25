#!/usr/bin/env python3
"""Independently recount the study's exported JSONL; never import analyze.py.

Run only after the Linux outputs have been downloaded:
    python3 verify_results.py --write

Without --write, JSON goes only to stdout. With --write, the only written file is
verification.json beside the evidence. This verifies aggregate consistency and
provenance, not a second raw-toolset classification: the latter requires the blobs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


MANIFEST_SHA = "a7bfc9e09ab9782157ad6c7a4bb136477609746a7e7e6f9c6695ea2012e926fc"
INPUT_SHA = {
    "servers.jsonl.gz": "7e96f47212faac4a25dcdeb13a2920c20d548ae0f5b2df823f604117cf5b8b0b",
    "changes.jsonl.gz": "8df3d75824a2505014422c63583f1b2d987c21509e218a662c4ece26e6147a6f",
    "toolsets.jsonl.gz": "9d5f8493910741c084a4e8315375d6bba918d5a0fad8d7bbc02f1e216773e2a2",
}
FLAGS = (
    "composition", "tool_description", "parameter_description", "input_schema",
    "output_schema", "schema_contract", "schema_order", "schema_annotation",
    "descriptions_only", "tool_descriptions_only",
)
KINDS = ("unchanged", "whitespace", "numeric", "text")
SUMMARY_FLAGS = {
    "tool_description": "summaryToolDescription",
    "input_schema": "summaryInputSchema",
    "output_schema": "summaryOutputSchema",
    "composition": "summaryComposition",
}


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def jsonl(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def recount(records):
    """Count independently with sets; primary bins and partitions are exhaustive."""
    primary = Counter()
    top_kinds, all_kinds = Counter(), Counter()
    flagged_events = Counter()
    flagged_servers = {flag: set() for flag in FLAGS}
    server_kinds = defaultdict(set)
    incomplete = set()
    for record in records:
        server = record["serverId"]
        primary[record["primary"]] += 1
        top_kinds[record["tool_description_kind"]] += 1
        all_kinds[record["description_kind"]] += 1
        server_kinds[server].add(record["tool_description_kind"])
        if record["primary"] == "unknown":
            incomplete.add(server)
        for flag in FLAGS:
            if record["flags"].get(flag, False):
                flagged_events[flag] += 1
                flagged_servers[flag].add(server)
    partitions = Counter()
    for server, kinds in server_kinds.items():
        if server in incomplete:
            name = "incomplete"
        elif "text" in kinds:
            name = "any_text_beyond_digits_whitespace"
        elif "numeric" in kinds:
            name = "numeric_and_optional_whitespace_only"
        elif "whitespace" in kinds:
            name = "whitespace_only"
        else:
            name = "no_tool_description_change"
        partitions[name] += 1
    return {
        "transitions": len(records), "servers": len(server_kinds),
        "primary": dict(sorted(primary.items())),
        "flagsTransitions": {flag: flagged_events[flag] for flag in FLAGS},
        "flagsServers": {flag: len(flagged_servers[flag]) for flag in FLAGS},
        "toolDescriptionKinds": dict(top_kinds), "descriptionKinds": dict(all_kinds),
        "serverToolDescriptionPartition": dict(partitions),
    }


def verify(directory):
    errors, checks = [], 0

    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    def equal(actual, expected, label):
        check(actual == expected, f"{label}: actual={actual!r}; expected={expected!r}")

    required = ("transitions.jsonl", "servers.jsonl", "summary.json", "execution.json")
    for name in required:
        check((directory / name).is_file(), f"Missing required output: {name}")
    if errors:
        return {"ok": False, "checks": checks, "errors": errors}
    transitions = jsonl(directory / "transitions.jsonl")
    net = jsonl(directory / "servers.jsonl")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    execution = json.loads((directory / "execution.json").read_text(encoding="utf-8"))
    output_hashes = {name: sha256(directory / name) for name in required}
    equal(output_hashes["transitions.jsonl"], summary["transitionFileSha256"], "Transition SHA-256")
    equal(summary["manifestSha256"], MANIFEST_SHA, "Pinned manifest SHA-256")
    equal(summary["inputSha256"], INPUT_SHA, "Pinned input SHA-256 claims")
    if (directory / "manifest.json").is_file():
        equal(sha256(directory / "manifest.json"), MANIFEST_SHA, "Downloaded manifest SHA-256")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        equal({name: manifest["files"][name]["sha256"] for name in INPUT_SHA}, INPUT_SHA,
              "Manifest input hashes")
    equal(summary["scriptSha256"], execution["sources"]["analyze.py"], "Executed analyzer SHA-256")
    for name, expected in execution["sources"].items():
        path = directory / name
        check(path.is_file(), f"Missing source needed to check provenance: {name}")
        if path.is_file():
            equal(sha256(path), expected, f"Local source SHA-256: {name}")
    equal(summary["schema"], "histor.change-kinds-study/v1", "Summary schema")
    equal(summary["snapshotCreatedAt"], "2026-10-20T15:39:49Z", "Snapshot timestamp")
    equal(summary["changesFrom"], "2026-09-24T10:53:44Z", "Snapshot start")
    equal(summary["changesUntil"], "2026-10-20T00:31:28Z", "Snapshot end")
    equal(summary["baseCutoff"], "2026-09-24T23:59:59Z", "Base cutoff")
    equal(summary["baseServers"], 10929, "Original base servers")
    equal(execution["host"], "admin-vps", "Execution host")
    equal(execution["imageMetadata"][1], "linux", "Execution OS")
    equal(execution["imageMetadata"][0], execution["image"], "Pinned image identity")
    check(execution["state"] not in ("prepared", "tests_passed"), "Execution not marked completed")

    ids = [row["id"] for row in transitions]
    equal(len(ids), 10543, "Base transition count")
    check(all(type(value) is int for value in ids), "Event IDs must be integers")
    equal(len(set(ids)), len(ids), "Unique event IDs")
    cohort = [row for row in transitions if row["cohort2036"]]
    description_events = [row for row in cohort if row["summaryToolDescription"]]
    cohort_ids = {row["serverId"] for row in cohort}
    equal(len(cohort), 7319, "Original cohort transition count")
    equal(len(cohort_ids), 2036, "Original cohort server count")
    equal(len(description_events), 5482, "Original description-event count")
    equal({row["serverId"] for row in description_events}, cohort_ids,
          "Every cohort server has a summary description event")
    equal({row["serverId"] for row in transitions if row["summaryToolDescription"]}, cohort_ids,
          "Cohort exactly reconstructed from base description events")
    for row in transitions:
        check(type(row["cohort2036"]) is bool, f"Invalid cohort boolean at {row['id']}")
        equal(row["cohort2036"], row["serverId"] in cohort_ids,
              f"Consistent cohort membership at {row['id']}")
    equal(sum(row["summaryFull"] for row in transitions), 10522, "Full transitions")
    equal(summary["baseFullTransitions"], 10522, "Summary full transitions")
    equal(len({row["serverId"] for row in transitions if row["summaryFull"]}), 4926,
          "Full-changed base servers")
    equal(summary["baseFullChangedServers"], 4926, "Summary full-changed servers")
    equal(summary["legacyWholeSnapshotNumericEvents"], 2719, "Legacy all-unit digit-only count")
    equal(sorted(summary["legacyWhitespaceEventIds"]), [7251, 7920, 11487, 15424, 17749, 21561],
          "Six legacy whitespace-only IDs")

    missing = set(summary["missingToolsets"])
    equal(len(missing), len(summary["missingToolsets"]), "Unique missing-digest list")
    wanted = {row[field] for row in transitions
              for field in ("fromToolSetDigest", "toToolSetDigest") if row[field]}
    equal(len(wanted), summary["requiredToolsets"], "Required raw-digest count")
    check(missing <= wanted, "Missing digest outside required inputs")
    equal(summary["verifiedToolsets"], len(wanted - missing), "Verified raw-digest count")
    mismatch = []

    def validate_row(row, is_event):
        label = f"event {row['id']}" if is_event else f"net {row['serverId']}"
        complete = all(row[field] and row[field] not in missing
                       for field in ("fromToolSetDigest", "toToolSetDigest"))
        equal(row["primary"] != "unknown", complete, f"Raw-pair availability: {label}")
        if not complete:
            equal(row["flags"], {}, f"Unknown flags: {label}")
            equal(row["tool_description_kind"], "unknown", f"Unknown top description: {label}")
            equal(row["description_kind"], "unknown", f"Unknown description: {label}")
            return
        flags = row["flags"]
        equal(set(flags), set(FLAGS), f"Flag names: {label}")
        check(all(type(value) is bool for value in flags.values()), f"Nonboolean flag: {label}")
        top_kind, all_kind = row["tool_description_kind"], row["description_kind"]
        check(top_kind in KINDS and all_kind in KINDS, f"Unknown complete kind: {label}")
        if top_kind not in KINDS or all_kind not in KINDS:
            return
        check(KINDS.index(top_kind) <= KINDS.index(all_kind), f"Description kind ordering: {label}")
        equal(flags["tool_description"], top_kind != "unchanged", f"Tool-description flag: {label}")
        any_description = flags["tool_description"] or flags["parameter_description"]
        equal(any_description, all_kind != "unchanged", f"Description-kind presence: {label}")
        other = any(flags[key] for key in (
            "composition", "schema_contract", "schema_order", "schema_annotation"))
        equal(flags["descriptions_only"], any_description and not other,
              f"Descriptions-only flag: {label}")
        equal(flags["tool_descriptions_only"], flags["tool_description"] and not any(
            flags[key] for key in ("composition", "input_schema", "output_schema")),
            f"Tool-descriptions-only flag: {label}")
        priorities = (
            (flags["composition"], "composition"),
            (flags["schema_contract"], "schema_contract"),
            (all_kind == "text", "description_text"),
            (all_kind == "numeric", "description_numeric"),
            (flags["schema_order"], "schema_order"),
            (flags["schema_annotation"], "schema_annotation"),
            (all_kind == "whitespace", "description_whitespace"),
        )
        expected = next((kind for condition, kind in priorities if condition), "unchanged")
        equal(row["primary"], expected, f"Primary precedence: {label}")
        if "added" in row and "removed" in row:
            equal(flags["composition"], bool(row["added"] or row["removed"]), f"Composition lists: {label}")
        if is_event:
            for flag, summary_flag in SUMMARY_FLAGS.items():
                if flags[flag] != row[summary_flag]:
                    mismatch.append({"id": row["id"], "field": flag,
                                     "raw": flags[flag], "summary": row[summary_flag]})

    for row in transitions:
        validate_row(row, True)
    equal(mismatch, summary["rawSummaryFlagMismatches"], "Reported raw/summary mismatches")
    equal(len(mismatch), 0, "Raw/summary flags agree on complete events")

    net_ids = [row["serverId"] for row in net]
    equal(len(net_ids), 2036, "First/last record count")
    equal(len(set(net_ids)), len(net_ids), "Unique first/last server IDs")
    equal(set(net_ids), cohort_ids, "First/last cohort IDs")
    by_server = defaultdict(list)
    for row in cohort:
        by_server[row["serverId"]].append(row)
    chain_known = chain_unknown = chain_gaps = chain_servers = 0
    for row in net:
        validate_row(row, False)
        sequence = sorted(by_server[row["serverId"]], key=lambda item: (item["observedAt"], item["id"]))
        first, last = sequence[0], sequence[-1]
        equal(row["events"], len(sequence), f"Net event count: {row['serverId']}")
        for field, expected in (
            ("firstAt", first["observedAt"]), ("lastAt", last["observedAt"]),
            ("fromToolSetDigest", first["fromToolSetDigest"]),
            ("toToolSetDigest", last["toToolSetDigest"]),
        ):
            equal(row[field], expected, f"Net {field}: {row['serverId']}")
        pairs = list(zip(sequence, sequence[1:]))
        known = [(a, b) for a, b in pairs if a["toToolSetDigest"] and b["fromToolSetDigest"]]
        gaps = sum(a["toToolSetDigest"] != b["fromToolSetDigest"] for a, b in known)
        equal(row["knownAdjacentPairs"], len(known), f"Known chain pairs: {row['serverId']}")
        equal(row["unknownAdjacentPairs"], len(pairs) - len(known), f"Unknown chain pairs: {row['serverId']}")
        equal(row["chainGaps"], gaps, f"Chain gaps: {row['serverId']}")
        chain_known += len(known)
        chain_unknown += len(pairs) - len(known)
        chain_gaps += gaps
        chain_servers += bool(gaps)
    equal(chain_known, 5277, "Known cohort chain pairs")
    equal(chain_unknown, 6, "Unknown cohort chain pairs")
    equal(chain_gaps, 0, "Cohort chain gaps")
    equal(summary["knownAdjacentPairs"], chain_known, "Summary known chain pairs")
    equal(summary["unknownAdjacentPairs"], chain_unknown, "Summary unknown chain pairs")
    equal(summary["serverChainsWithGaps"], chain_servers, "Summary chain-gap servers")
    equal(sum(not row["summaryFull"] for row in cohort), 12, "Cohort names-only events")
    equal(sum(row["primary"] == "unknown" for row in cohort), 12, "Cohort unknown raw pairs")

    scopes = {
        "cohort2036": cohort, "toolDescriptionEvents2036": description_events,
        "baseAllEvents": transitions, "firstToLast2036": net,
    }
    aggregates = {}
    for name, records in scopes.items():
        actual = recount(records)
        aggregates[name] = actual
        equal(actual, summary[name], f"Recounted aggregate: {name}")
        equal(sum(actual["primary"].values()), len(records), f"Primary partition sum: {name}")
        equal(sum(actual["serverToolDescriptionPartition"].values()), actual["servers"],
              f"Server partition sum: {name}")
        unknown_servers = len({row["serverId"] for row in records if row["primary"] == "unknown"})
        equal(actual["serverToolDescriptionPartition"].get("incomplete", 0), unknown_servers,
              f"Unknown server partition precedence: {name}")
    return {
        "schema": "histor.change-kinds-independent-verification/v1",
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "ok": not errors, "checks": checks, "errors": errors,
        "outputSha256": output_hashes, "aggregates": aggregates,
        "rawSummaryFlagMismatches": mismatch,
        "chainCounts": {"known": chain_known, "unknown": chain_unknown, "gaps": chain_gaps},
        "limits": [
            "Raw field classification is not rerun without toolset blobs.",
            "Input-file hashes are checked against pinned manifest claims; input gzip bytes are not read here.",
            "Null adjacent pairs do not establish continuity of unobserved definitions.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write", action="store_true", help="Write only verification.json in the evidence directory")
    args = parser.parse_args()
    result = verify(args.directory)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        (args.directory / "verification.json").write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["ok"] else 1)
