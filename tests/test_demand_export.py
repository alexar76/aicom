"""The demand funnel exporter (scripts/demand_export.py): outsiders only, callers never named."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import demand_export as ex

START = ex._start_ts()
OWN = set(ex.DEFAULT_OWN_IPS)


def line(ip="198.51.100.7", when="06/Oct/2026:10:00:00 -0400", method="POST", path="/x402/x402-check",
         status=402, ua="node"):
    return f'{ip} - - [{when}] "{method} {path} HTTP/2.0" {status} 120 "-" "{ua}"\n'


def fresh():
    return {"x402": {"salt": "s"}, "mcp": {}}


def test_a_log_line_is_parsed_in_utc():
    hit = ex.parse_log_line(line(when="05/Oct/2026:10:00:01 -0400"))
    assert hit["at"] == START + 1 and hit["path"] == "/x402/x402-check" and hit["status"] == 402
    assert ex.parse_log_line("garbage") is None


def test_outsiders_are_counted_per_route_and_ours_are_not():
    state = fresh()
    hits = [line(), line(status=200), line(ip="203.0.113.9", status=402), line(status=400),
            line(status=502), line(ip="127.0.0.1", status=200),            # ours
            line(when="04/Oct/2026:10:00:00 -0400", status=200),               # before the test
            line(method="GET", path="/x402/openapi.json", ua="x402scan/1.0"),
            line(path="/x402/a/b"), line(method="GET", path="/x402/x402-check")]
    for raw in hits:
        ex.fold_x402(state["x402"], ex.parse_log_line(raw), OWN, START)
    row = state["x402"]["routes"]["x402-check"]
    assert (row["quoted"], row["paid"], row["refused"], row["failed"]) == (2, 1, 1, 1)
    assert len(row["callers"]) == 2 and "198.51.100.7" not in json.dumps(state)
    assert state["x402"]["discovery"] == {"x402scan": 1}
    assert set(state["x402"]["routes"]) == {"x402-check"}


def test_the_log_is_read_incrementally_and_through_a_rotation(tmp_path):
    log = tmp_path / "access.log"
    log.write_text(line() + line(status=200))
    state = fresh()
    assert ex.read_log(state, str(log), OWN, START) == 2
    assert ex.read_log(state, str(log), OWN, START) == 0               # nothing new
    with open(log, "a") as fh:
        fh.write(line(status=402))
    ex.read_log(state, str(log), OWN, START)
    log.rename(tmp_path / "access.log.1")                              # logrotate
    with open(tmp_path / "access.log.1", "a") as fh:
        fh.write(line(status=200))                                     # written before the reopen
    log.write_text(line(ip="203.0.113.9"))
    ex.read_log(state, str(log), OWN, START)
    row = state["x402"]["routes"]["x402-check"]
    assert (row["quoted"], row["paid"]) == (3, 2) and len(row["callers"]) == 2


def test_mcp_totals_survive_hub_restarts_and_start_at_the_baseline():
    page = ('aimarket_hub_mcp_requests_total{client="claude",method="initialize",tool=""} 4\n'
            'aimarket_hub_mcp_requests_total{client="other",method="tools/call",tool="x402_check"} 1\n'
            'aimarket_hub_mcp_requests_total{client="claude",method="tools/list",tool=""} 3\n')
    raw = ex.mcp_requests(page)
    assert raw == {"initialize": {"claude": 4}, "tools/call:x402_check": {"other": 1}, "tools/list": {"claude": 3}}
    state: dict = {}
    ex.fold_mcp(state, raw)
    assert state["total"] == {}                                        # baseline
    ex.fold_mcp(state, {"initialize": {"claude": 6, "cursor": 1}, "tools/call:x402_check": {"other": 1}})
    assert state["total"] == {"initialize": {"claude": 2, "cursor": 1}}
    ex.fold_mcp(state, {"initialize": {"claude": 1}})                  # the hub restarted
    assert state["total"]["initialize"]["claude"] == 3


def test_invocations_are_published_with_hashed_callers(monkeypatch):
    rows = [["2026-10-06T10:00:00Z", "gaia.weather.read@v1", "ok", "sandbox:mcpx-1234"],
            ["2026-10-06T11:00:00Z", "x402.authorization.check@v1", None, "account:acct_x"]]

    def fake_run(cmd, input, capture_output, text, timeout, check):
        assert cmd[:4] == ["docker", "exec", "-i", "hub"] and "invocation_stats" in input
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(rows), stderr="")

    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    got = ex.invocations("hub")
    assert [r["caller"] for r in got] == ["sandbox", "account"] and got[1]["outcome"] == ""
    assert "mcpx-1234" not in json.dumps(got)


def test_the_public_document_names_no_caller():
    state = fresh()
    ex.fold_x402(state["x402"], ex.parse_log_line(line()), OWN, START)
    state["mcp"] = {"total": {"tools/call:x402_check": {"claude": 2}}}
    doc = ex.public(state, [], START + 60)
    assert doc["x402"]["routes"]["x402-check"] == {"quoted": 1, "paid": 0, "refused": 0, "failed": 0, "callers": 1}
    assert doc["tools_call"] == {"x402_check": {"claude": 2}}
    assert "salt" not in json.dumps(doc) and "cursor" not in json.dumps(doc)
