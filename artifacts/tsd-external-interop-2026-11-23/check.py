#!/usr/bin/env python3
"""Compare pinned external MCP digest readers against the local spec vectors.

Arguments are the vectors JSON, extracted CrawlCheck wheel directory,
CrawlCheck dist/tsd.js and addon-declaration lib/tool-set-digest.js.
Writes machine-readable results to stdout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def validate_side(expected, actual):
    if "error" in expected:
        return [] if actual.get("error") == expected["error"] else ["error"]
    fields = []
    if "digest" not in actual or expected["digest"] != actual["digest"]:
        fields.append("digest")
    if expected.get("canonical") != actual.get("canonical"):
        fields.append("canonical")
    if "hex" in expected:
        canonical = actual.get("canonical")
        actual_hex = actual.get("hex")
        if actual_hex is None and canonical is not None:
            actual_hex = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if expected["hex"] != actual_hex:
            fields.append("hex")
    return fields


def summarize(results, document):
    failures = []
    for vector in document["vectors"]:
        actual = results[vector["id"]]
        if "parser_error" in actual:
            failures.append({"id": vector["id"], "parser_error": actual["parser_error"],
                             "expected_errors": {side: vector[side].get("error") for side in ("contract", "extras")}})
            continue
        problems = {}
        for side in ("contract", "extras"):
            fields = validate_side(vector[side], actual.get(side, {}))
            if fields:
                problems[side] = {
                    "fields": fields,
                    "expected": {k:v for k,v in vector[side].items() if k in ("digest", "error")},
                    "actual": {k:v for k,v in actual.get(side, {}).items() if k in ("digest", "error")},
                }
        if problems:
            failures.append({"id": vector["id"], "sides": problems})

    pairs = {"pass": 0, "fail": [], "unavailable": []}
    for group in ("equal", "differ"):
        for pair in document[group]:
            kind = pair["digest"]
            a, b = (results[key].get(kind, {}).get("digest") for key in pair["ids"])
            if a is None or b is None:
                pairs["unavailable"].append({"group": group, **pair})
            elif (a == b) != (group == "equal"):
                pairs["fail"].append({"group": group, **pair})
            else:
                pairs["pass"] += 1
    return {"passed": len(document["vectors"]) - len(failures), "failed": failures, "pairs": pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vectors", type=Path)
    parser.add_argument("crawlcheck_wheel", type=Path)
    parser.add_argument("crawlcheck_js", type=Path)
    parser.add_argument("addon_js", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.crawlcheck_wheel.resolve()))
    from crawlcheck.tsd import tool_set_digest

    raw = args.vectors.read_bytes()
    doc = json.loads(raw)
    node = Path(__file__).with_name("readers.mjs")
    result = subprocess.check_output(
        ["node", str(node), str(args.vectors), str(args.crawlcheck_js.resolve()), str(args.addon_js.resolve())],
        text=True,
    )
    readers = json.loads(result)
    readers["crawlcheck-python"] = {}
    for vector in doc["vectors"]:
        try:
            readers["crawlcheck-python"][vector["id"]] = tool_set_digest(json.loads(vector["tools"]))
        except (ValueError, RecursionError) as error:
            readers["crawlcheck-python"][vector["id"]] = {"parser_error": type(error).__name__}
    report = {
        "vectors_sha256": hashlib.sha256(raw).hexdigest(),
        "vectors": len(doc["vectors"]),
        "equal_pairs": len(doc["equal"]),
        "differ_pairs": len(doc["differ"]),
        "readers": {name: summarize(rows, doc) for name, rows in readers.items()},
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
