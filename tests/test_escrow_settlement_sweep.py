"""The sweep decides *when* to broadcast, never *what* — so its verdict is what matters.

A collector that reports success while leaving money unsubmitted is the failure mode worth
testing: it converts an outage into a documented all-clear, exactly like a monitor that
passes on a broken system. Everything here runs without docker and without a network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import escrow_settlement_sweep as sweep  # noqa: E402


NOW = 1_787_000_000.0

EMPTY_STATUS = {"db_path": "data/escrow_bridge.db", "by_status": {}, "unsubmitted_units": 0,
                "unsubmitted_usd": 0.0}
OWED_STATUS = {"db_path": "data/escrow_bridge.db",
               "by_status": {"stored": {"count": 2, "units": 30000}},
               "unsubmitted_units": 30000, "unsubmitted_usd": 0.03}


# ── reading the CLI ──────────────────────────────────────────────────────────────────────

def test_json_is_found_behind_log_noise():
    """The hub logs warnings before the payload; a naive json.loads would read that as
    'the bridge is broken', which is the opposite of the truth."""
    out = ("WARNING migrations: SKIP 019 (already present)\n"
           "Supply-chain admission is off\n"
           '{"unsubmitted_units": 10000}\n')
    assert sweep._extract_json(out) == {"unsubmitted_units": 10000}


def test_missing_json_is_an_error_not_an_empty_result():
    with pytest.raises(ValueError):
        sweep._extract_json("Traceback (most recent call last): boom")


def test_pending_units_reads_the_published_field():
    assert sweep.pending_units(OWED_STATUS) == 30000
    assert sweep.pending_units(EMPTY_STATUS) == 0
    assert sweep.pending_units(None) == 0
    assert sweep.pending_units({"unsubmitted_units": None}) == 0
    assert sweep.pending_units({"unsubmitted_units": "not a number"}) == 0


# ── the verdict ──────────────────────────────────────────────────────────────────────────

def test_an_empty_queue_is_a_success():
    r = sweep.summarize(EMPTY_STATUS, None, EMPTY_STATUS, dry_run=False, errors=[], now=NOW)
    assert r["ok"] is True
    assert r["submitted"] == 0 and r["pending_units_after"] == 0


def test_a_full_sweep_is_a_success():
    result = {"scanned": 3, "outcomes": {"submitted": 3}}
    r = sweep.summarize(OWED_STATUS, result, EMPTY_STATUS, dry_run=False, errors=[], now=NOW)
    assert r["ok"] is True
    assert r["submitted"] == 3 and r["pending_units_before"] == 30000


def test_money_left_unsubmitted_is_NOT_a_success():
    """The whole point. Two of three went out, one stayed — that is not 'ok'."""
    result = {"scanned": 3, "outcomes": {"submitted": 2, "rejected": 1}}
    after = {"unsubmitted_units": 10000}
    r = sweep.summarize(OWED_STATUS, result, after, dry_run=False, errors=[], now=NOW)
    assert r["ok"] is False
    assert r["failed"] == 1
    assert r["pending_usd_after"] == 0.01


def test_a_dry_run_is_ok_even_with_a_full_queue():
    """`plan` never intended to send, so a non-empty queue afterwards is not a fault."""
    result = {"dry_run": True, "scanned": 2, "outcomes": {"planned": 2}}
    r = sweep.summarize(OWED_STATUS, result, OWED_STATUS, dry_run=True, errors=[], now=NOW)
    assert r["ok"] is True and r["mode"] == "plan"


def test_any_error_fails_the_sweep_even_if_the_queue_is_empty():
    r = sweep.summarize(EMPTY_STATUS, None, EMPTY_STATUS, dry_run=False,
                        errors=["status failed (exit 1): signer unreachable"], now=NOW)
    assert r["ok"] is False


def test_confirmed_counts_as_submitted_and_skipped_is_not_a_failure():
    result = {"scanned": 4, "outcomes": {"confirmed": 1, "submitted": 1, "skipped": 2}}
    r = sweep.summarize(OWED_STATUS, result, EMPTY_STATUS, dry_run=False, errors=[], now=NOW)
    assert r["submitted"] == 2
    assert r["failed"] == 0 and r["ok"] is True


# ── orchestration ────────────────────────────────────────────────────────────────────────

def test_nothing_owed_means_no_submit_call(monkeypatch):
    """A timer running every 15 minutes must not poke the signer for no reason."""
    calls = []
    def fake(*args, **kw):
        calls.append(args)
        if args[0] == "confirm":
            return 0, {"outcomes": {}}, ""
        return 0, EMPTY_STATUS, ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=False)
    assert [a[0] for a in calls] == ["status", "confirm", "status", "status"]
    assert r["ok"] is True


def test_money_owed_triggers_submit_yes(monkeypatch):
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        if args[0] == "status":
            n = sum(1 for s in seen if s[0] == "status")
            if n <= 2:
                return 0, OWED_STATUS, ""
            return 0, EMPTY_STATUS, ""
        if args[0] == "confirm":
            return 0, {"outcomes": {}}, ""
        return 0, {"scanned": 2, "outcomes": {"submitted": 2}}, ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=False)
    assert ["submit", "--yes", "--limit", "5"] in seen
    assert r["submitted"] == 2 and r["ok"] is True


def test_dry_run_never_calls_submit(monkeypatch):
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        return 0, (OWED_STATUS if args[0] == "status" else {"scanned": 1, "outcomes": {}}), ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    sweep.sweep(dry_run=True)
    assert ["plan"] in seen
    assert not any("submit" in s for s in seen)


def test_an_unreadable_status_stops_before_submitting(monkeypatch):
    """If the bridge cannot even be read, broadcasting blind is the wrong move."""
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        return 1, None, "docker: no such container"
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=False)
    assert seen == [["status"]]
    assert r["ok"] is False and "status failed" in r["errors"][0]


def test_a_timeout_is_reported_not_raised(monkeypatch):
    import subprocess
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=240)
    monkeypatch.setattr(sweep.subprocess, "run", boom)
    code, parsed, err = sweep.run_cli("status")
    assert code == 124 and parsed is None and "timed out" in err


# ── publishing ───────────────────────────────────────────────────────────────────────────

def test_the_report_is_published_atomically(monkeypatch, tmp_path):
    monkeypatch.setattr(sweep, "sweep", lambda **k: {"mode": "submit", "ok": True,
                                                     "scanned": 0, "submitted": 0,
                                                     "failed": 0, "errors": [],
                                                     "pending_usd_after": 0.0})
    out = tmp_path / "pub" / "settlement.json"
    assert sweep.main(["--publish", str(out)]) == 0
    assert json.loads(out.read_text())["ok"] is True
    assert not (tmp_path / "pub" / "settlement.json.tmp").exists()


def test_a_publish_failure_is_distinguishable_from_a_settlement_failure(monkeypatch, tmp_path):
    """Exit 2, not 1: the sweep may have collected perfectly and only the report is lost."""
    monkeypatch.setattr(sweep, "sweep", lambda **k: {"mode": "submit", "ok": True,
                                                     "scanned": 0, "submitted": 0,
                                                     "failed": 0, "errors": [],
                                                     "pending_usd_after": 0.0})
    target = tmp_path / "file"
    target.write_text("x")
    assert sweep.main(["--publish", str(target / "nested" / "settlement.json")]) == 2


def test_a_failed_sweep_exits_non_zero(monkeypatch):
    monkeypatch.setattr(sweep, "sweep", lambda **k: {"mode": "submit", "ok": False,
                                                     "scanned": 1, "submitted": 0,
                                                     "failed": 1, "errors": ["boom"],
                                                     "pending_usd_after": 0.01})
    assert sweep.main([]) == 1


# ── the real payload shape ───────────────────────────────────────────────────────────────

# Copied from a live `status --json` on modelmarket.dev, 2026-08-25. The first version of
# `pending_units` read `unsubmitted_units` from the root, where it does not exist, so it
# returned 0 for everything — an empty queue forever, reported as success.
LIVE_STATUS = {
    "config": {"enabled": True, "network": "base", "hub_address_set": True,
               "contract": "0x12Db8FAC81E5999D2f2087B79e38951571562CF2",
               "strategy": "external", "may_broadcast": True, "blocked_reason": "",
               "signer_url_set": True, "private_key_set": False,
               "max_usd_per_pass": 5.0, "max_usd_per_day": 25.0},
    "signer": "external",
    "store": {"db_path": "data/escrow_bridge.db",
              "by_status": {"abandoned": {"count": 1, "units": 10000},
                            "confirmed": {"count": 1, "units": 10000}},
              "unsubmitted_units": 0, "unsubmitted_usd": 0.0},
    "queue": [],
}


def test_pending_units_reads_the_nested_field():
    owed = json.loads(json.dumps(LIVE_STATUS))
    owed["store"]["unsubmitted_units"] = 30000
    assert sweep.pending_units(owed) == 30000
    assert sweep.pending_units(LIVE_STATUS) == 0


def test_by_status_is_taken_from_the_store():
    r = sweep.summarize(LIVE_STATUS, None, LIVE_STATUS, dry_run=False, errors=[], now=NOW)
    assert r["by_status"] == LIVE_STATUS["store"]["by_status"]


def test_owed_money_in_the_real_shape_triggers_a_submit(monkeypatch):
    owed = json.loads(json.dumps(LIVE_STATUS))
    owed["store"]["unsubmitted_units"] = 30000
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        if args[0] == "status":
            n = sum(1 for s in seen if s[0] == "status")
            if n <= 2:
                return 0, owed, ""
            return 0, LIVE_STATUS, ""
        if args[0] == "confirm":
            return 0, {"outcomes": {}}, ""
        return 0, {"scanned": 3, "outcomes": {"submitted": 3}}, ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=False)
    assert ["submit", "--yes", "--limit", "5"] in seen, "the sweep read the queue as empty again"
    assert r["ok"] is True and r["submitted"] == 3


# ── a bridge that cannot broadcast ───────────────────────────────────────────────────────

def test_a_bridge_that_may_not_broadcast_is_an_error_not_an_empty_queue(monkeypatch):
    blocked = json.loads(json.dumps(LIVE_STATUS))
    blocked["config"]["may_broadcast"] = False
    blocked["config"]["strategy"] = "plan"
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        return 0, blocked, ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=False)
    assert seen == [["status"]], "it must not try to submit through a blocked bridge"
    assert r["ok"] is False
    assert "may_broadcast=false" in r["errors"][0]


def test_a_disabled_bridge_names_the_switch(monkeypatch):
    off = json.loads(json.dumps(LIVE_STATUS))
    off["config"]["enabled"] = False
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, off, ""))
    r = sweep.sweep(dry_run=False)
    assert "AIMARKET_ESCROW_BRIDGE_ENABLED" in r["errors"][0]


def test_an_explicit_block_reason_wins(monkeypatch):
    blocked = json.loads(json.dumps(LIVE_STATUS))
    blocked["config"]["blocked_reason"] = "daily cap reached"
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, blocked, ""))
    assert "daily cap reached" in sweep.sweep(dry_run=False)["errors"][0]


def test_a_dry_run_still_reports_on_a_blocked_bridge(monkeypatch):
    """`--dry-run` is a diagnostic: it should show the plan even when broadcasting is off."""
    blocked = json.loads(json.dumps(LIVE_STATUS))
    blocked["config"]["may_broadcast"] = False
    seen = []
    def fake(*args, **kw):
        seen.append(list(args))
        return 0, (blocked if args[0] == "status" else {"scanned": 0, "outcomes": {}}), ""
    monkeypatch.setattr(sweep, "run_cli", fake)
    r = sweep.sweep(dry_run=True)
    assert ["plan"] in seen and r["ok"] is True


# ── money already on chain, waiting for gas ──────────────────────────────────────────────

def test_the_hardcoded_selector_still_matches_the_signature():
    """The sweep runs on a host with no eth libraries, so the selector is a constant.
    This is the test that catches it drifting."""
    eth_utils = pytest.importorskip("eth_utils")
    assert sweep.GET_CHANNEL_SELECTOR == "0x" + eth_utils.keccak(
        text="getChannel(bytes32)").hex()[:8]


def _chan(**kw):
    base = {"depositor": "0xdead", "hub": "0xbeef", "balance_units": 990000,
            "used_units": 10000, "expires_at": 1_787_000_000, "status": 0,
            "channel_id": "0x" + "11" * 32}
    base.update(kw)
    return base


def test_a_settled_channel_is_not_collectable():
    assert sweep.collectable([_chan(status=1)], now=NOW)["collectable_usd"] == 0.0


def test_an_open_channel_with_earnings_is_collectable():
    r = sweep.collectable([_chan()], now=NOW)
    assert r["open_with_earnings"] == 1 and r["collectable_usd"] == 0.01


def test_expiry_is_reported_separately_from_merely_open():
    """Past expiry anyone may call expireChannel, so that subset is actionable by us
    without the depositor's cooperation."""
    fresh = _chan(expires_at=int(NOW) + 3600)
    stale = _chan(expires_at=int(NOW) - 3600, channel_id="0x" + "22" * 32)
    r = sweep.collectable([fresh, stale], now=NOW)
    assert r["open_with_earnings"] == 2
    assert r["expired_uncollected"] == 1
    assert r["collectable_usd"] == 0.02 and r["expired_usd"] == 0.01


def test_a_channel_with_no_earnings_is_not_reported():
    """An open channel the buyer funded but never spent owes us nothing."""
    assert sweep.collectable([_chan(used_units=0)], now=NOW)["open_with_earnings"] == 0


def test_a_flaky_rpc_does_not_fail_the_sweep(monkeypatch):
    """Submission is the job. A public endpoint having a bad minute must not turn a
    successful collection into a red run — the alerter would page for the wrong reason."""
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, LIVE_STATUS, ""))
    monkeypatch.setattr(sweep, "read_escrow_channels",
                        lambda escrow: ([], ["0xabc…: RuntimeError"]))
    r = sweep.sweep(dry_run=False)
    assert r["ok"] is True
    assert r["uncollected"]["read_errors"] == ["0xabc…: RuntimeError"]


# ── collecting through the signer ────────────────────────────────────────────────────────

def test_the_expire_selector_matches_the_signature():
    eth_utils = pytest.importorskip("eth_utils")
    assert sweep.EXPIRE_SELECTOR == "0x" + eth_utils.keccak(
        text="expireChannel(bytes32)").hex()[:8]


def test_only_expired_channels_with_earnings_are_asked_for(monkeypatch):
    asked = []
    monkeypatch.setattr(sweep, "signer_endpoint", lambda: ("http://signer/sign", "tok"))
    monkeypatch.setattr(sweep, "ask_signer_to_expire",
                        lambda u, t, e, cid, **k: (asked.append(cid) or (True, "0xhash")))
    channels = [
        _chan(channel_id="0x" + "01" * 32, expires_at=int(NOW) - 10),          # yes
        _chan(channel_id="0x" + "02" * 32, expires_at=int(NOW) + 10),          # not expired
        _chan(channel_id="0x" + "03" * 32, expires_at=int(NOW) - 10, used_units=0),  # owes 0
        _chan(channel_id="0x" + "04" * 32, expires_at=int(NOW) - 10, status=1),      # closed
    ]
    result = sweep.collect_expired(channels, escrow="0xesc", now=NOW)
    assert asked == ["0x" + "01" * 32]
    assert result["attempted"] == 1 and result["collected"] == 1


def test_a_refusal_is_recorded_not_raised(monkeypatch):
    """The signer refusing is the normal case — daily limit, not ours, already in flight."""
    monkeypatch.setattr(sweep, "signer_endpoint", lambda: ("http://signer/sign", "tok"))
    monkeypatch.setattr(sweep, "ask_signer_to_expire",
                        lambda *a, **k: (False, "0xabc…: cap_gas_only_24h"))
    result = sweep.collect_expired([_chan(expires_at=int(NOW) - 10)], escrow="0xesc", now=NOW)
    assert result["collected"] == 0
    assert result["refusals"] == ["0xabc…: cap_gas_only_24h"]


def test_nothing_due_means_the_signer_is_not_contacted(monkeypatch):
    def boom():
        raise AssertionError("must not read the signer token with nothing to collect")
    monkeypatch.setattr(sweep, "signer_endpoint", boom)
    assert sweep.collect_expired([_chan(expires_at=int(NOW) + 3600)],
                                 escrow="0xesc", now=NOW)["attempted"] == 0


def test_a_missing_token_is_reported_rather_than_guessed(monkeypatch):
    monkeypatch.setattr(sweep, "signer_endpoint", lambda: ("", ""))
    result = sweep.collect_expired([_chan(expires_at=int(NOW) - 10)], escrow="0xesc", now=NOW)
    assert result["collected"] == 0 and "no signer url/token" in result["refusals"][0]


def test_collect_is_off_unless_asked(monkeypatch):
    """A sweep that collects by accident is a sweep that spends gas by accident."""
    owed = json.loads(json.dumps(LIVE_STATUS))
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, owed, ""))
    monkeypatch.setattr(sweep, "read_escrow_channels",
                        lambda escrow: ([_chan(expires_at=1)], []))
    def boom(*a, **k):
        raise AssertionError("collect ran without --collect")
    monkeypatch.setattr(sweep, "collect_expired", boom)
    report = sweep.sweep(dry_run=False)
    assert report["uncollected"]["expired_uncollected"] == 1
    assert "collect" not in report["uncollected"]


def test_a_dry_run_never_collects(monkeypatch):
    owed = json.loads(json.dumps(LIVE_STATUS))
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, owed, ""))
    monkeypatch.setattr(sweep, "read_escrow_channels",
                        lambda escrow: ([_chan(expires_at=1)], []))
    def boom(*a, **k):
        raise AssertionError("collect ran under --dry-run")
    monkeypatch.setattr(sweep, "collect_expired", boom)
    sweep.sweep(dry_run=True, collect=True)


def test_the_report_shows_the_state_after_collecting(monkeypatch):
    """The numbers a human reads must be post-collection, or a successful sweep still
    looks like money left on the table."""
    owed = json.loads(json.dumps(LIVE_STATUS))
    monkeypatch.setattr(sweep, "run_cli", lambda *a, **k: (0, owed, ""))
    calls = {"n": 0}
    def channels(escrow):
        calls["n"] += 1
        return ([_chan(expires_at=1)] if calls["n"] == 1 else [_chan(expires_at=1, status=3)],
                [])
    monkeypatch.setattr(sweep, "read_escrow_channels", channels)
    monkeypatch.setattr(sweep, "collect_expired", lambda *a, **k: {
        "attempted": 1, "collected": 1, "tx_hashes": ["0xdeadbeef"], "refusals": []})
    report = sweep.sweep(dry_run=False, collect=True)
    assert report["uncollected"]["collect"]["collected"] == 1
    assert report["uncollected"]["expired_uncollected"] == 0
    assert report["uncollected"]["expired_usd"] == 0.0
