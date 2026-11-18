"""scripts/esim-price-history: what the recorder writes from two catalogue snapshots, and what report computes."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("esim_price_history", ROOT / "scripts/esim-price-history/esim_price_history.py")
eph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eph)


def plan(pid, cost, data=1 << 30, days=7, name=None):
    return {"id": pid, "name": name or pid, "countries": ["JP"], "kind": "country", "data_bytes": data, "days": days, "cost_usd": cost}


def write_snapshot(path: Path, at: str, plans: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "at": at, "plans": plans}))


def run(state: Path, snap: Path) -> int:
    return eph.main(["record", "--state-dir", str(state), "--snapshot", str(snap), "--no-poke"])


def lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_first_read_is_a_baseline_with_a_daily_copy(tmp_path):
    snap, state = tmp_path / "snap.json", tmp_path / "state"
    write_snapshot(snap, "2026-11-18T10:00:00.000Z", [plan("A", 1.0), plan("B", 2.0)])
    assert run(state, snap) == 0
    (read,) = lines(state / "reads.jsonl")
    assert read["baseline"] is True and read["plans"] == 2 and read["prev_at"] is None and read["poke"] == "skipped"
    assert not (state / "changes.jsonl").exists()
    assert json.loads(gzip.decompress((state / "daily/2026-11-18.json.gz").read_bytes()))["at"] == "2026-11-18T10:00:00.000Z"


def test_second_read_records_price_terms_added_and_removed(tmp_path):
    snap, state = tmp_path / "snap.json", tmp_path / "state"
    write_snapshot(snap, "2026-11-18T10:00:00.000Z", [plan("A", 1.0), plan("B", 2.0), plan("C", 3.0), plan("D", 4.0)])
    run(state, snap)
    write_snapshot(snap, "2026-11-18T10:15:00.000Z", [plan("A", 1.1), plan("B", 2.0, days=30), plan("D", 4.0), plan("E", 5.0)])
    run(state, snap)
    events = {c["id"]: c for c in lines(state / "changes.jsonl")}
    assert events["A"]["event"] == "price" and events["A"]["cost_before"] == 1.0 and events["A"]["cost_after"] == 1.1
    assert events["B"]["event"] == "terms" and events["B"]["days_before"] == 7 and events["B"]["days"] == 30
    assert events["C"]["event"] == "removed" and events["E"]["event"] == "added"
    assert "D" not in events
    read = lines(state / "reads.jsonl")[-1]
    assert (read["price_changes"], read["terms"], read["added"], read["removed"]) == (1, 1, 1, 1)
    assert read["prev_at"] == "2026-11-18T10:00:00.000Z"


def test_unchanged_snapshot_and_older_snapshot_write_nothing(tmp_path):
    snap, state = tmp_path / "snap.json", tmp_path / "state"
    write_snapshot(snap, "2026-11-18T10:15:00.000Z", [plan("A", 1.0)])
    run(state, snap)
    run(state, snap)  # the node has not read its wholesaler again
    write_snapshot(snap, "2026-11-18T10:00:00.000Z", [plan("A", 9.0)])
    run(state, snap)  # older than the last read
    assert len(lines(state / "reads.jsonl")) == 1
    assert not (state / "changes.jsonl").exists()


def test_report_rates_and_window_estimate(tmp_path):
    snap, state = tmp_path / "snap.json", tmp_path / "state"
    plans = [plan(f"P{i}", 2.0) for i in range(100)]
    write_snapshot(snap, "2026-11-18T00:00:00.000Z", plans)
    run(state, snap)
    plans[0] = plan("P0", 2.5)  # +25 %
    write_snapshot(snap, "2026-11-18T12:00:00.000Z", plans)
    run(state, snap)
    plans[0] = plan("P0", 2.0)  # -20 %, 12 hours after the first change
    write_snapshot(snap, "2026-11-19T00:00:00.000Z", plans)
    run(state, snap)
    s = eph.summarize(state, 600)
    assert s["intervals"] == 2 and s["hours"] == 24.0 and s["median_interval_minutes"] == 720.0
    assert s["price_changes"] == 2 and s["plans_with_price_change"] == 1 and (s["rises"], s["falls"]) == (1, 1)
    assert s["max_rise_pct"] == 25.0 and s["shortest_gap_between_changes_minutes"] == 720.0
    # 2 changes over 100 plans x 24 h = 20 per 1,000 plans per day
    assert s["price_changes_per_1000_plans_per_day"] == 20.0
    assert 0.013 < s["chance_a_plan_changes_within_window_pct"] < 0.0145


def test_report_before_two_reads(tmp_path):
    assert eph.summarize(tmp_path / "missing", 600) == {"reads": 0, "note": "no two reads to compare yet"}
