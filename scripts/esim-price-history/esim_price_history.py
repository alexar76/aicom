#!/usr/bin/env python3
"""Wholesale eSIM price history from an esim-rails node's catalogue snapshot.

The node rewrites /data/catalog-snapshot.json ({"version": 1, "at", "plans"}) after every successful read of its
wholesaler's catalogue, and reads again when its copy is older than 15 minutes and someone asks for a quote. This
recorder asks the node for one quote on localhost (so the catalogue stays fresh), then compares the snapshot with the
previous one and appends what changed:

  reads.jsonl    one line per new catalogue read, also when nothing changed (needed for rates)
  changes.jsonl  one line per plan whose wholesale cost, data or days changed, or that appeared or disappeared
  daily/         the first snapshot of each UTC day, gzipped, for audit
  last.json      the previous read (cost, data, days per plan id)

  record  [--state-dir D] [--snapshot F] [--node-url U] [--no-poke] [--no-daily]
  report  [--state-dir D] [--window-seconds 600] [--json]

Standard library only; reads no secrets. The resolution is the node's catalogue age (15 minutes): two changes of one
plan between reads count as one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import gzip
import json
import math
import os
import statistics
import sys
import tempfile
import urllib.request
from pathlib import Path

STATE_DIR = Path("/var/lib/aicom/esim-price-history")
SNAPSHOT = Path("/opt/esim-node-data/catalog-snapshot.json")
NODE_URL = "http://127.0.0.1:9493/quote"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def poke(url: str) -> str:
    """One quote request, so the node reads its wholesaler again when its copy is older than 15 minutes."""
    body = json.dumps({"country": "JP", "limit": 1}).encode()
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read(4096)
            return "ok" if response.status == 200 else f"http {response.status}"
    except Exception as exc:  # the snapshot is still read; the read line says why the poke failed
        return f"error: {type(exc).__name__}: {exc}"[:200]


def load_snapshot(path: Path) -> tuple[str, list[dict], bytes]:
    raw = path.read_bytes()
    doc = json.loads(raw)
    if doc.get("version") != 1 or not isinstance(doc.get("plans"), list) or not doc["plans"]:
        raise ValueError(f"{path}: not a version 1 catalogue snapshot with plans")
    parse_time(doc["at"])
    return doc["at"], doc["plans"], raw


def terms(plan: dict) -> list:
    return [plan.get("cost_usd"), plan.get("data_bytes"), plan.get("days"), plan.get("name")]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def append_lines(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")


def diff(prev_at: str, prev: dict[str, list], at: str, plans: list[dict]) -> list[dict]:
    now = {str(p["id"]): terms(p) for p in plans if p.get("id") is not None}
    rows = []
    for pid in sorted(set(prev) | set(now)):
        before, after = prev.get(pid), now.get(pid)
        base = {"at": at, "prev_at": prev_at, "id": pid}
        if before is None:
            rows.append({**base, "event": "added", "cost_after": after[0], "data_bytes": after[1], "days": after[2], "name": after[3]})
        elif after is None:
            rows.append({**base, "event": "removed", "cost_before": before[0], "data_bytes": before[1], "days": before[2], "name": before[3]})
        elif before[0] != after[0]:
            rows.append({**base, "event": "price", "cost_before": before[0], "cost_after": after[0],
                         "data_bytes": after[1], "days": after[2], "name": after[3]})
        elif before[1:3] != after[1:3]:
            rows.append({**base, "event": "terms", "cost_after": after[0], "data_before": before[1], "data_bytes": after[1],
                         "days_before": before[2], "days": after[2], "name": after[3]})
    return rows


def record(args: argparse.Namespace) -> int:
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    with (state / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        poke_result = "skipped" if args.no_poke else poke(args.node_url)
        at, plans, raw = load_snapshot(Path(args.snapshot))
        last_path = state / "last.json"
        last = json.loads(last_path.read_text()) if last_path.exists() else None
        if last and last["at"] == at:
            return 0  # the node has not read its wholesaler since the last run
        if last and parse_time(at) < parse_time(last["at"]):
            print(f"snapshot {at} is older than the last read {last['at']}; ignored", file=sys.stderr)
            return 0
        changes = diff(last["at"], last["plans"], at, plans) if last else []
        count = lambda kind: sum(1 for c in changes if c["event"] == kind)  # noqa: E731
        read = {"at": at, "prev_at": last["at"] if last else None, "recorded_at": utc_now(), "plans": len(plans),
                "price_changes": count("price"), "added": count("added"), "removed": count("removed"),
                "terms": count("terms"), "poke": poke_result}
        if not last:
            read["baseline"] = True
        append_lines(state / "changes.jsonl", changes)
        append_lines(state / "reads.jsonl", [read])
        if not args.no_daily:
            daily = state / "daily" / f"{at[:10]}.json.gz"
            if not daily.exists():
                atomic_write(daily, gzip.compress(raw, mtime=0))
        plan_terms = {str(p["id"]): terms(p) for p in plans if p.get("id") is not None}
        atomic_write(last_path, json.dumps({"at": at, "plans": plan_terms}, separators=(",", ":")).encode())
    return 0


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def summarize(state: Path, window_seconds: int) -> dict:
    reads = read_jsonl(state / "reads.jsonl")
    changes = read_jsonl(state / "changes.jsonl")
    compared = [r for r in reads if r.get("prev_at")]
    if not compared:
        return {"reads": len(reads), "note": "no two reads to compare yet"}
    intervals = [(parse_time(r["at"]) - parse_time(r["prev_at"])).total_seconds() for r in compared]
    plan_seconds = sum(r["plans"] * s for r, s in zip(compared, intervals))
    prices = [c for c in changes if c["event"] == "price"]
    pct = [100 * (c["cost_after"] - c["cost_before"]) / c["cost_before"] for c in prices if c.get("cost_before")]
    per_plan: dict[str, list[str]] = {}
    for c in prices:
        per_plan.setdefault(c["id"], []).append(c["at"])
    gaps = [(parse_time(b) - parse_time(a)).total_seconds() for ats in per_plan.values() for a, b in zip(ats, ats[1:])]
    rate = len(prices) / plan_seconds if plan_seconds else 0.0  # price changes per plan-second
    first, last = parse_time(compared[0]["prev_at"]), parse_time(compared[-1]["at"])
    return {
        "from": compared[0]["prev_at"], "to": compared[-1]["at"], "hours": round((last - first).total_seconds() / 3600, 2),
        "reads": len(reads), "intervals": len(compared),
        "median_interval_minutes": round(statistics.median(intervals) / 60, 1),
        "plans_latest": reads[-1]["plans"],
        "price_changes": len(prices), "plans_with_price_change": len(per_plan),
        "rises": sum(1 for p in pct if p > 0), "falls": sum(1 for p in pct if p < 0),
        "median_abs_change_pct": round(statistics.median(abs(p) for p in pct), 2) if pct else None,
        "p90_abs_change_pct": round(percentile([abs(p) for p in pct], 0.9), 2) if pct else None,
        "max_rise_pct": round(max(pct), 2) if pct else None,
        "added": sum(1 for c in changes if c["event"] == "added"),
        "removed": sum(1 for c in changes if c["event"] == "removed"),
        "terms": sum(1 for c in changes if c["event"] == "terms"),
        "shortest_gap_between_changes_minutes": round(min(gaps) / 60, 1) if gaps else None,
        "price_changes_per_1000_plans_per_day": round(rate * 1000 * 86400, 3),
        "window_seconds": window_seconds,
        # Poisson estimate from the observed rate; the read interval bounds what can be seen.
        "chance_a_plan_changes_within_window_pct": round(100 * (1 - math.exp(-rate * window_seconds)), 4),
        "pokes_failed": sum(1 for r in reads if str(r.get("poke", "")).startswith(("error", "http"))),
    }


def report(args: argparse.Namespace) -> int:
    summary = summarize(Path(args.state_dir), args.window_seconds)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for key, value in summary.items():
            print(f"{key:44} {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="compare the node's catalogue snapshot with the last read and append changes")
    rec.add_argument("--state-dir", default=str(STATE_DIR))
    rec.add_argument("--snapshot", default=str(SNAPSHOT))
    rec.add_argument("--node-url", default=NODE_URL)
    rec.add_argument("--no-poke", action="store_true", help="do not ask the node for a quote first")
    rec.add_argument("--no-daily", action="store_true", help="do not keep the first snapshot of each day")
    rec.set_defaults(func=record)
    rep = sub.add_parser("report", help="rates and sizes of wholesale price changes so far")
    rep.add_argument("--state-dir", default=str(STATE_DIR))
    rep.add_argument("--window-seconds", type=int, default=600, help="quote window to estimate against (default 600)")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=report)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
