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


def test_the_operator_funnel_counts_other_peoples_hubs_only(monkeypatch):
    raw = {
        "peers": [["https://hub.stranger.org", "active"], ["https://knock.example.net", "pending"],
                  ["https://hunt.modelmarket.dev", "active"], ["http://108.165.32.182:9083", "pending"],
                  ["https://hub.attestedmemory.net", "active"]],
        "inbound": ["https://hub.stranger.org", "http://localhost:9083", "https://hub.test",
                    "https://modelmarket.dev", "https://new.operator.io"],
        "assays": {"https://hub.stranger.org": "pass", "https://knock.example.net": "fail",
                   "https://charon.independentai.network": "pass"},
    }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(raw), stderr="")

    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    assert ex.hubs("hub") == {"crawled_us": 2, "pending": 1, "admitted": 1,
                              "assay_verdicts": {"pass": 1, "fail": 1}}
    doc = ex.public(fresh(), [], START, ex.hubs("hub"))
    assert doc["hubs"]["admitted"] == 1
    assert "stranger" not in json.dumps(doc)  # counts, never names


def test_the_tools_pages_count_people_apart_from_crawlers_and_checks_per_tool(tmp_path):
    browser = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/131 Safari/537.36"
    state = fresh()
    state["tools"] = {"since": "2026-10-06T00:00:00Z", "since_ts": START}
    log = tmp_path / "access.log"
    log.write_text("".join([
        line(method="GET", path="/tools/", status=200, ua=browser),
        line(method="GET", path="/tools/ru/mcp-diff", status=200, ua=browser),
        line(ip="203.0.113.9", method="GET", path="/tools/ru/mcp-diff?x=1", status=200, ua=browser),
        line(method="GET", path="/tools/x402-check", status=200, ua="Mozilla/5.0 (compatible; Googlebot/2.1)"),
        line(method="GET", path="/tools/nope", status=404, ua=browser),          # not a page
        line(method="GET", path="/tools/assets/tools.js", status=200, ua=browser),  # not a page
        line(ip="127.0.0.1", method="GET", path="/tools/", status=200, ua=browser),  # ours
        line(path="/tools/api/mcp-diff", status=200), line(path="/tools/api/mcp-diff", status=429),
        line(ip="203.0.113.9", path="/tools/api/mcp-diff", status=400),
        line(path="/tools/api/warden-scan", status=502),
        line(when="04/Oct/2026:10:00:00 -0400", path="/tools/api/mcp-diff", status=200),  # before since
        line(),                                                                  # x402 still counted
    ]))
    ex.read_log(state, str(log), OWN, START)
    doc = ex.public(state, [], START + 60)
    pages, checks = doc["tools"]["pages"], doc["tools"]["checks"]
    assert set(pages) == {"index", "mcp-diff", "x402-check"}
    assert pages["mcp-diff"] == {"people": 2, "crawlers": 0, "visitors": 2, "langs": {"ru": 2}}
    assert pages["index"]["people"] == 1 and pages["x402-check"] == {"people": 0, "crawlers": 1, "visitors": 0, "langs": {}}
    assert checks["mcp-diff"] == {"answered": 1, "refused": 1, "limited": 1, "failed": 0, "callers": 2}
    assert checks["warden-scan"]["failed"] == 1
    assert doc["x402"]["routes"]["x402-check"]["quoted"] == 1
    assert "198.51.100.7" not in json.dumps(state) and "visitors\": [" not in json.dumps(doc)


def test_the_tools_section_starts_when_it_is_first_known_and_is_not_back_filled(tmp_path):
    log = tmp_path / "access.log"
    log.write_text(line(path="/tools/api/mcp-diff", status=200))
    state = fresh()
    ex.read_log(state, str(log), OWN, START)          # an exporter that does not know the pages yet
    assert "tools" not in state
    out = tmp_path / "demand.json"
    st = tmp_path / "state.json"
    st.write_text(json.dumps(state))
    with open(log, "a") as fh:
        fh.write(line(path="/tools/api/mcp-diff", status=200, when="06/Oct/2099:10:00:00 -0400"))
    ex.main(["--out", str(out), "--log", str(log), "--state", str(st), "--metrics", "http://127.0.0.1:9/x",
             "--hub-container", "no-such-container"])
    doc = json.loads(out.read_text())
    assert doc["tools"]["since"] and doc["tools"]["checks"]["mcp-diff"]["answered"] == 1


def test_gateway_mcp_counters_are_typed_and_published_under_tools():
    raw = ex.gateway_mcp_counters({"started": "x", "counters": {
        "weather:initialize": {"claude": 2, "bad": "7"}, "weather:tools/call:weather_now:ok": {"claude": 1},
        "junk": "not a dict"}})
    assert raw == {"weather:initialize": {"claude": 2}, "weather:tools/call:weather_now:ok": {"claude": 1}}
    state = {"x402": {"salt": "s"}, "mcp": {}, "tools": {"since": "2026-10-20T00:00:00Z"}, "tools_mcp": {}}
    ex.fold_mcp(state["tools_mcp"], raw)                                   # baseline
    ex.fold_mcp(state["tools_mcp"], {"weather:initialize": {"claude": 5}, "weather:tools/call:weather_now:ok": {"claude": 1}})
    ex.fold_mcp(state["tools_mcp"], {"weather:initialize": {"claude": 1}})  # the gateway restarted
    doc = ex.public(state, [], 0.0, {})
    assert doc["tools"]["mcp"] == {"weather:initialize": {"claude": 4}}
    assert ex.gateway_mcp_counters(["nope"]) == {}
