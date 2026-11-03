"""Recompute every number in README.md from the three CSV files. Standard library only.

usage: python3 scripts/summarize.py results/ > results/summary.json
"""
import collections
import csv
import gzip
import json
import pathlib
import sys

MODERN = "2026-07-28"  # MCP revisions from this one on carry metadata per request; earlier ones open with initialize


def rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as f:
        yield from csv.DictReader(f)


def pick(folder, stem):
    for name in (stem + ".csv", stem + ".csv.gz"):
        if (folder / name).exists():
            return folder / name
    raise SystemExit(f"missing {stem}.csv in {folder}")


folder = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results")

protocols = list(rows(pick(folder, "remote-protocols")))
by_version = collections.Counter(r["protocol_version"] or "(none)" for r in protocols)
modern = sum(n for v, n in by_version.items() if v >= MODERN)
legacy = sum(n for v, n in by_version.items() if v != "(none)" and v < MODERN)

changes = list(rows(pick(folder, "same-version-changes")))
same = sum(1 for r in changes if r["same_version"] == "t")

lost = list(rows(pick(folder, "unread-since-2026-10-30")))
back = [r for r in lost if r["first_ok_after_fix"]]
failed = collections.Counter(r["failed_status"] or "(no failed read recorded)" for r in lost)
detail = collections.Counter((r["failed_detail"] or "").split(";")[0] for r in lost if r["failed_status"] == "protocol")
# The reader's own refusals before the 2026-11-01 fix: no fallback to initialize where the specification wants one.
STRICT = ("HTTP error did not match our request id", "modern discovery did not advertise the requested version",
          "malformed JSON-RPC error response", "no mutually supported modern protocol version")
strict = sum(n for d, n in detail.items() if d in STRICT)
auth = sum(1 for r in lost if r["failed_status"] in ("http-401", "http-403"))
before_1029 = sum(1 for r in protocols if r["last_ok_at"] < "2026-10-29")

json.dump({
    "remoteServersReadOk": len(protocols),
    "modern": modern,
    "legacy": legacy,
    "byProtocolVersion": dict(by_version.most_common()),
    "changesWithBothServerVersions": len(changes),
    "sameServerVersion": same,
    "sameServerVersionShare": round(100 * same / len(changes), 1),
    "serversOnSameVersionChanges": len({r["server_id"] for r in changes if r["same_version"] == "t"}),
    "lastOkBefore2026-10-29": before_1029,
    "unreadSince2026-10-30": len(lost),
    "unreadStrictHandshake": strict,
    "unreadHttp401or403": auth,
    "unreadByFailedStatus": dict(failed.most_common()),
    "unreadProtocolDetail": dict(detail.most_common()),
    "readAgainByAsOf": len(back),
    "readAgainByProtocol": dict(collections.Counter(r["protocol_after_fix"] for r in back).most_common()),
}, sys.stdout, indent=1)
print()
