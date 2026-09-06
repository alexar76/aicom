"""The alerter's only job is to be believed, so its silence has to be as trustworthy as
its noise.

Every case here is a way an alerter earns a mute: paging on a single blip during a deploy,
repeating the same failure every ten minutes, never saying anything again after a recovery
it failed to notice, or going quiet because it died. A muted alerter is worse than none —
it looks alive.

The state machine is pure, so all of this runs without a network.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ecosystem_alert as alert  # noqa: E402


def C(name: str, ok: bool, detail: str = "", critical: bool = True) -> alert.Check:
    return alert.Check(name, ok, detail, critical)


def fresh_state() -> dict:
    return {"checks": {}, "last_heartbeat": "", "last_alert": ""}


NOW = 1_787_000_000.0  # a fixed clock: a test that depends on the wall clock is a flake


# ── flap protection ──────────────────────────────────────────────────────────────────────

def test_single_failure_does_not_page():
    """A deploy restarts the hub. One bad poll is not an incident."""
    state = fresh_state()
    broke, fixed, hb = alert.decide([C("hub_manifest", False, "timeout")], state,
                                    flap=2, heartbeat_hours=24, now=NOW)
    assert broke == [] and fixed == [] and hb is False
    assert state["checks"]["hub_manifest"]["failures"] == 1
    assert state["checks"]["hub_manifest"]["alerted"] is False


def test_second_consecutive_failure_pages():
    state = fresh_state()
    alert.decide([C("hub_manifest", False, "timeout")], state,
                 flap=2, heartbeat_hours=24, now=NOW)
    broke, _, _ = alert.decide([C("hub_manifest", False, "timeout")], state,
                               flap=2, heartbeat_hours=24, now=NOW + 600)
    assert broke == ["hub_manifest"]
    assert state["checks"]["hub_manifest"]["alerted"] is True


def test_a_recovery_resets_the_failure_run():
    """Alternating fail/ok must never accumulate its way to a page."""
    state = fresh_state()
    for i in range(6):
        checks = [C("signer_ready", i % 2 == 1, "flapping")]
        broke, _, _ = alert.decide(checks, state, flap=2, heartbeat_hours=24,
                                   now=NOW + i * 600)
        assert broke == []


def test_failure_is_announced_once_not_every_poll():
    state = fresh_state()
    sent = 0
    for i in range(10):
        broke, _, _ = alert.decide([C("signer_not_halted", False, "HALTED: ledger")],
                                   state, flap=2, heartbeat_hours=24, now=NOW + i * 600)
        sent += len(broke)
    assert sent == 1


# ── recovery ─────────────────────────────────────────────────────────────────────────────

def test_recovery_is_reported_immediately():
    state = fresh_state()
    for i in range(2):
        alert.decide([C("hub_manifest", False, "500")], state, flap=2,
                     heartbeat_hours=24, now=NOW + i * 600)
    broke, fixed, _ = alert.decide([C("hub_manifest", True, "200")], state, flap=2,
                                   heartbeat_hours=24, now=NOW + 1200)
    assert broke == [] and fixed == ["hub_manifest"]
    assert state["checks"]["hub_manifest"]["alerted"] is False


def test_recovery_is_reported_only_once():
    state = fresh_state()
    for i in range(2):
        alert.decide([C("hub_manifest", False)], state, flap=2, heartbeat_hours=24,
                     now=NOW + i * 600)
    alert.decide([C("hub_manifest", True)], state, flap=2, heartbeat_hours=24, now=NOW + 1200)
    _, fixed, _ = alert.decide([C("hub_manifest", True)], state, flap=2,
                               heartbeat_hours=24, now=NOW + 1800)
    assert fixed == []


def test_recovery_is_not_claimed_for_something_never_announced():
    """It failed once, below the flap threshold, then came back. Nobody was told it broke,
    so nobody may be told it recovered."""
    state = fresh_state()
    alert.decide([C("hub_manifest", False)], state, flap=2, heartbeat_hours=24, now=NOW)
    _, fixed, _ = alert.decide([C("hub_manifest", True)], state, flap=2,
                               heartbeat_hours=24, now=NOW + 600)
    assert fixed == []


# ── severity ─────────────────────────────────────────────────────────────────────────────

def test_non_critical_failures_never_page():
    state = fresh_state()
    for i in range(5):
        broke, _, _ = alert.decide([C("hub_stats_live", False, "502", critical=False)],
                                   state, flap=2, heartbeat_hours=24, now=NOW + i * 600)
        assert broke == []


def test_non_critical_failure_still_suppresses_nothing_else():
    """A warning must not block the heartbeat: the digest is how a warning gets seen."""
    state = fresh_state()
    checks = [C("hub_manifest", True), C("hub_stats_live", False, "502", critical=False)]
    _, _, hb = alert.decide(checks, state, flap=2, heartbeat_hours=24, now=NOW)
    assert hb is True


# ── heartbeat: silence must mean healthy, never dead ─────────────────────────────────────

def test_first_quiet_run_sends_a_heartbeat():
    state = fresh_state()
    _, _, hb = alert.decide([C("hub_manifest", True)], state, flap=2,
                            heartbeat_hours=24, now=NOW)
    assert hb is True
    assert state["last_heartbeat"]


def test_heartbeat_waits_out_its_interval():
    state = fresh_state()
    alert.decide([C("hub_manifest", True)], state, flap=2, heartbeat_hours=24, now=NOW)
    _, _, hb = alert.decide([C("hub_manifest", True)], state, flap=2,
                            heartbeat_hours=24, now=NOW + 3600)
    assert hb is False
    _, _, hb = alert.decide([C("hub_manifest", True)], state, flap=2,
                            heartbeat_hours=24, now=NOW + 24 * 3600 + 60)
    assert hb is True


def test_no_heartbeat_while_something_critical_is_down():
    """An 'all good' digest during an outage is the exact lie this file must not tell."""
    state = fresh_state()
    for i in range(3):
        _, _, hb = alert.decide([C("hub_manifest", False, "down")], state, flap=2,
                                heartbeat_hours=0, now=NOW + i * 600)
        assert hb is False


# ── bookkeeping ──────────────────────────────────────────────────────────────────────────

def test_checks_that_disappear_are_forgotten():
    """`--mode full` adds paywall checks. Switching back to quick must not leave them
    permanently 'alerted', or their recovery could never be reported."""
    state = fresh_state()
    for i in range(2):
        alert.decide([C("hub_manifest", True), C("priced_capability_gated[x]", False)],
                     state, flap=2, heartbeat_hours=24, now=NOW + i * 600)
    assert "priced_capability_gated[x]" in state["checks"]
    alert.decide([C("hub_manifest", True)], state, flap=2, heartbeat_hours=24,
                 now=NOW + 1200)
    assert "priced_capability_gated[x]" not in state["checks"]


def test_state_survives_a_round_trip(tmp_path):
    path = tmp_path / "sub" / "state.json"
    state = fresh_state()
    alert.decide([C("hub_manifest", False)], state, flap=2, heartbeat_hours=24, now=NOW)
    alert.save_state(str(path), state)
    again = alert.load_state(str(path))
    assert again["checks"]["hub_manifest"]["failures"] == 1


def test_unreadable_state_starts_clean_instead_of_crashing(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ this is not json", encoding="utf-8")
    state = alert.load_state(str(path))
    assert state == {"checks": {}, "last_heartbeat": "", "last_alert": ""}


# ── probe parsing ────────────────────────────────────────────────────────────────────────

def test_signer_halt_is_a_critical_check(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (
        200, {"ready": True, "ledger": {"halted": "clock went backwards"}}, ""))
    checks = {c.name: c for c in alert.probe_signer("http://127.0.0.1:9500")}
    assert checks["signer_not_halted"].ok is False
    assert checks["signer_not_halted"].critical is True
    assert "clock went backwards" in checks["signer_not_halted"].detail


def test_unreachable_signer_reports_one_failure_not_an_exception(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (0, None, "TimeoutError: timed out"))
    checks = alert.probe_signer("http://127.0.0.1:9500")
    assert [c.name for c in checks] == ["signer_reachable"]
    assert checks[0].ok is False


def test_an_empty_catalogue_is_a_failure(monkeypatch):
    """Every peer unreachable looks exactly like a hub with nothing to sell."""
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (
        200, {"total_capabilities": 0}, ""))
    checks = {c.name: c for c in alert.probe_hub("https://modelmarket.dev")}
    assert checks["hub_catalogue_not_empty"].ok is False


def test_stale_status_page_means_the_daily_canary_died(monkeypatch):
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 50 * 3600))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (
        200, {"checked_at": old, "checks": [{"name": "x", "ok": True, "critical": True}]}, ""))
    checks = {c.name: c for c in alert.probe_status_page("https://verify/status.json",
                                                        now=NOW)}
    assert checks["canary_status_fresh"].ok is False
    assert "STALE" in checks["canary_status_fresh"].detail


def test_a_failing_canary_is_surfaced_by_name(monkeypatch):
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 3600))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
        "checked_at": recent,
        "checks": [
            {"name": "priced_capability_gated[atlas]", "ok": False, "critical": True},
            {"name": "peer_alive[x]", "ok": False, "critical": False},
        ],
    }, ""))
    checks = {c.name: c for c in alert.probe_status_page("https://verify/status.json",
                                                        now=NOW)}
    assert checks["canary_verdict_ok"].ok is False
    assert "atlas" in checks["canary_verdict_ok"].detail
    # A non-critical canary check must not be the thing that pages someone.
    assert "peer_alive" not in checks["canary_verdict_ok"].detail


def test_missing_canary_is_reported_rather_than_skipped(monkeypatch):
    """`--mode full` delegates to payment_canary.py. If that file is not deployed next to
    this one, the run must say so — a probe that silently does nothing reads as green."""
    monkeypatch.setitem(sys.modules, "payment_canary", None)
    checks = alert.probe_paywall("https://modelmarket.dev", 5.0)
    assert len(checks) == 1 and checks[0].ok is False


# ── the message ──────────────────────────────────────────────────────────────────────────

def test_failure_message_names_the_check_and_the_evidence():
    checks = [C("signer_not_halted", False, "HALTED: ledger unavailable"),
              C("hub_manifest", True, "manifest served, 85 capabilities")]
    text = alert.format_message(checks, ["signer_not_halted"], [], False,
                                host="oracles", hub="https://modelmarket.dev",
                                when="2026-08-25 07:00 UTC")
    assert "signer_not_halted" in text
    assert "HALTED: ledger unavailable" in text
    assert "oracles" in text and "2026-08-25 07:00 UTC" in text
    assert "next:" in text  # actionable at 3am, not just informative


def test_recovery_message_says_recovered():
    text = alert.format_message([C("hub_manifest", True)], [], ["hub_manifest"], False,
                                host="h", hub="https://x", when="t")
    assert "recovered" in text.lower()
    assert "hub_manifest" in text


def test_heartbeat_message_carries_the_warnings_nobody_was_paged_for():
    checks = [C("hub_manifest", True), C("hub_stats_live", False, "502", critical=False)]
    text = alert.format_message(checks, [], [], True, host="h", hub="https://x", when="t")
    assert "1/2 checks ok" in text
    assert "hub_stats_live" in text


def test_message_fits_a_phone_screen():
    checks = [C(f"check_{i}", False, "x" * 300) for i in range(12)]
    text = alert.format_message(checks, [c.name for c in checks], [], False,
                                host="h", hub="https://x", when="t")
    assert len(text) < 4000  # Telegram's limit, and roughly one screen of scrolling


# ── delivery ─────────────────────────────────────────────────────────────────────────────

def test_a_failed_send_does_not_mark_the_failure_as_announced(monkeypatch, tmp_path):
    """If Telegram is unreachable, the next run must try again — the human was not told."""
    state = fresh_state()
    for i in range(2):
        broke, _, _ = alert.decide([C("hub_manifest", False, "down")], state, flap=2,
                                   heartbeat_hours=24, now=NOW + i * 600)
    assert broke == ["hub_manifest"]
    # main() reverts the flag on send failure; assert the shape it relies on.
    state["checks"]["hub_manifest"]["alerted"] = False
    broke2, _, _ = alert.decide([C("hub_manifest", False, "down")], state, flap=2,
                                heartbeat_hours=24, now=NOW + 1200)
    assert broke2 == ["hub_manifest"]


def test_send_never_raises_when_telegram_is_down(monkeypatch):
    def boom(*a, **k):
        raise OSError("network unreachable")
    monkeypatch.setattr(alert.urllib.request, "urlopen", boom)
    monkeypatch.setattr(alert.time, "sleep", lambda *_: None)
    ok, info = alert.send_telegram("123:abc", "42", "hello")
    assert ok is False
    assert "OSError" in info


def test_the_token_is_never_a_command_line_argument():
    """`ps` is world-readable on these hosts, so a token in argv is a token published."""
    src = (ROOT / "scripts" / "ecosystem_alert.py").read_text(encoding="utf-8")
    assert "--token" not in src
    assert "--chat" not in src


def test_dry_run_sends_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", True, "ok")])
    def forbidden(*a, **k):
        raise AssertionError("--dry-run must not send")
    monkeypatch.setattr(alert, "send_telegram", forbidden)
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
    state = tmp_path / "state.json"
    rc = alert.main(["--dry-run", "--state", str(state)])
    assert rc == 0
    assert not state.exists()  # a dry run must not move the state machine either


def test_a_real_run_sends_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", True, "ok")])
    sent = []
    monkeypatch.setattr(alert, "send_telegram",
                        lambda token, chat, text, **k: (sent.append(text) or (True, "1")))
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
    state = tmp_path / "state.json"
    rc = alert.main(["--state", str(state)])
    assert rc == 0
    assert len(sent) == 1 and "all critical checks green" in sent[0]
    assert json.loads(state.read_text())["last_heartbeat"]


def test_a_critical_failure_exits_non_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", False, "down")])
    monkeypatch.setattr(alert, "send_telegram", lambda *a, **k: (True, "1"))
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
    rc = alert.main(["--state", str(tmp_path / "s.json")])
    assert rc == 1


def test_missing_credentials_are_an_error_not_a_silent_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", False, "down")])
    monkeypatch.delenv("AICOM_ALERT_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AICOM_ALERT_TELEGRAM_CHAT", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    state = tmp_path / "s.json"
    # Two runs, because the first is below the flap threshold and sends nothing anyway.
    alert.main(["--state", str(state)])
    assert alert.main(["--state", str(state)]) == 2


def test_an_instance_without_the_signer_can_opt_out(monkeypatch):
    """The signer listens on loopback of one host. An alerter elsewhere must be able to
    stop probing it, or that check fails forever and poisons every message."""
    monkeypatch.setattr(alert, "probe_hub", lambda *a, **k: [C("hub_manifest", True)])
    monkeypatch.setattr(alert, "probe_status_page", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_settlement", lambda *a, **k: [])
    called = []
    monkeypatch.setattr(alert, "probe_signer",
                        lambda *a, **k: called.append(1) or [C("signer_reachable", True)])
    names = [c.name for c in alert.collect("quick", hub="https://x", signer="",
                                           status_url="https://y",
                                           settlement_url="https://z", timeout=5)]
    assert called == [] and "signer_reachable" not in names
    names = [c.name for c in alert.collect("quick", hub="https://x",
                                           signer="http://127.0.0.1:9500",
                                           status_url="https://y",
                                           settlement_url="https://z", timeout=5)]
    assert called == [1] and "signer_reachable" in names


# ── split-brain DNS: the failure a single-connection health check cannot see ──────────────

def test_one_bad_a_record_fails_the_check(monkeypatch):
    """modelmarket.dev really was in this state on 2026-08-25: two A records, one of them
    a stranger's host presenting a certificate for emberlinedesk.com. Every ordinary
    health check passed because the good address usually answered first."""
    # RFC 5737 placeholders — never commit live fleet IPs into the public tree.
    good, bad = "203.0.113.10", "203.0.113.40"
    monkeypatch.setattr(alert.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", (good, 443)),
        (2, 1, 6, "", (bad, 443)),
    ])
    monkeypatch.setattr(alert, "_tls_failure", lambda host, ip, t:
                        "" if ip == good else "cert for emberlinedesk.com")
    check = alert.probe_dns("https://modelmarket.dev")[0]
    assert check.name == "hub_dns_all_addresses_valid"
    assert check.ok is False and check.critical is True
    assert "1/2" in check.detail
    assert bad in check.detail
    assert "emberlinedesk.com" in check.detail  # names the impostor, not just "TLS failed"


def test_all_good_a_records_pass(monkeypatch):
    monkeypatch.setattr(alert.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("203.0.113.10", 443)), (2, 1, 6, "", ("203.0.113.10", 443))])
    monkeypatch.setattr(alert, "_tls_failure", lambda *a: "")
    check = alert.probe_dns("https://modelmarket.dev")[0]
    assert check.ok is True
    assert "1 address" in check.detail  # deduplicated


def test_dns_failure_is_reported_not_raised(monkeypatch):
    def boom(*a, **k):
        raise OSError("Name or service not known")
    monkeypatch.setattr(alert.socket, "getaddrinfo", boom)
    check = alert.probe_dns("https://modelmarket.dev")[0]
    assert check.name == "hub_dns_resolves" and check.ok is False


def test_the_hub_url_is_parsed_into_a_hostname(monkeypatch):
    seen = []
    monkeypatch.setattr(alert.socket, "getaddrinfo",
                        lambda host, *a, **k: seen.append(host) or [(2, 1, 6, "", ("1.2.3.4", 443))])
    monkeypatch.setattr(alert, "_tls_failure", lambda *a: "")
    alert.probe_dns("https://modelmarket.dev:443/ai-market/v2/manifest")
    assert seen == ["modelmarket.dev"]


def test_a_failed_heartbeat_is_not_recorded_as_delivered(monkeypatch, tmp_path):
    """The heartbeat stamp is set before the send. If a failed send kept it, the alerter
    would go quiet for a full interval *because* it could not reach anyone — the exact
    condition the heartbeat exists to expose. Found live: the bot had never been started,
    so Telegram answered "chat not found" while the state file recorded a heartbeat."""
    monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", True, "ok")])
    monkeypatch.setattr(alert, "send_telegram", lambda *a, **k: (False, "400 chat not found"))
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
    state = tmp_path / "state.json"
    assert alert.main(["--state", str(state)]) == 1
    assert json.loads(state.read_text())["last_heartbeat"] == "", \
        "a heartbeat nobody received was recorded as sent"
    # ...and the next run must try again rather than wait out the interval.
    sent = []
    monkeypatch.setattr(alert, "send_telegram",
                        lambda t, c, text, **k: (sent.append(text) or (True, "1")))
    assert alert.main(["--state", str(state)]) == 0
    assert len(sent) == 1


# ── the collector must be watched too ────────────────────────────────────────────────────

def test_a_dead_settlement_timer_pages(monkeypatch):
    """Automating a manual step without watching it just moves the silence: submission
    used to wait for a human, now it waits for a timer that can die just as quietly."""
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 5 * 3600))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (
        200, {"checked_at": old, "ok": True, "pending_usd_after": 0.0}, ""))
    checks = {c.name: c for c in alert.probe_settlement("https://v/settlement.json", now=NOW)}
    assert checks["settlement_sweep_fresh"].ok is False
    assert checks["settlement_sweep_fresh"].critical is True
    assert "STALE" in checks["settlement_sweep_fresh"].detail


def test_money_left_unsubmitted_pages(monkeypatch):
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 600))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
        "checked_at": recent, "ok": False, "pending_usd_after": 0.03,
        "errors": ["submit failed (exit 1): signer refused"]}, ""))
    checks = {c.name: c for c in alert.probe_settlement("https://v/settlement.json", now=NOW)}
    assert checks["settlement_sweep_fresh"].ok is True
    assert checks["settlement_nothing_stuck"].ok is False
    assert "0.030000" in checks["settlement_nothing_stuck"].detail
    assert "signer refused" in checks["settlement_nothing_stuck"].detail


def test_a_healthy_sweep_is_quiet(monkeypatch):
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 300))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (
        200, {"checked_at": recent, "ok": True, "pending_usd_after": 0.0}, ""))
    assert all(c.ok for c in alert.probe_settlement("https://v/settlement.json", now=NOW))


def test_a_hub_that_has_never_swept_does_not_page(monkeypatch):
    """Before the first sweep the file does not exist. That is a warning, not a 3am call —
    it is also the state of every hub in the ecosystem that does not collect at all."""
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (404, None, "HTTP 404"))
    checks = alert.probe_settlement("https://v/settlement.json", now=NOW)
    assert len(checks) == 1
    assert checks[0].ok is False and checks[0].critical is False


def test_uncollected_money_is_a_nudge_not_a_page(monkeypatch):
    """`expireChannel` is permissionless and pays the hub the same amount, so revenue
    parked in an expired channel cannot be lost — it is a chore, not an incident."""
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 300))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
        "checked_at": recent, "ok": True, "pending_usd_after": 0.0,
        "uncollected": {"expired_usd": 0.04, "expired_uncollected": 3,
                        "collectable_usd": 0.07}}, ""))
    checks = {c.name: c for c in alert.probe_settlement("https://v/settlement.json", now=NOW)}
    nudge = checks["settlement_nothing_expired_uncollected"]
    assert nudge.ok is False
    assert nudge.critical is False          # never a 3am call
    assert "0.040000" in nudge.detail and "expireChannel" in nudge.detail
    assert checks["settlement_nothing_stuck"].ok is True


def test_no_uncollected_money_means_no_extra_check(monkeypatch):
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 300))
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
        "checked_at": recent, "ok": True, "pending_usd_after": 0.0,
        "uncollected": {"expired_usd": 0.0, "collectable_usd": 0.01}}, ""))
    names = [c.name for c in alert.probe_settlement("https://v/settlement.json", now=NOW)]
    assert "settlement_nothing_expired_uncollected" not in names


# ── Federation: the partial freeze ──────────────────────────────────────────────
#
# A rejected key pin does not empty the catalogue, so hub_catalogue_not_empty stays
# green while a paid capability quietly disappears. Two hubs sat like that for five
# days with a bar on a dashboard as the only symptom.


def _peers_response(peers: list[dict]):
    return lambda *a, **k: (200, {"peers": peers}, "")


def _peer(name: str, *, status: str = "active", crawled_h_ago: float = 0.5) -> dict:
    stamp = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - crawled_h_ago * 3600)
    )
    return {"name": name, "url": f"https://{name}.example", "status": status,
            "last_crawl": stamp}


def _by_name(checks: list) -> dict:
    return {c.name: c for c in checks}


def test_a_healthy_federation_passes_both_federation_checks(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([_peer("atlas"), _peer("gaia")]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    assert checks["hub_federation_peers"].ok
    assert checks["hub_federation_pins_accepted"].ok
    assert checks["hub_federation_crawl_fresh"].ok


def test_a_rejected_key_pin_fails_and_names_the_peer(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([
        _peer("atlas", status="key_mismatch"), _peer("gaia"),
    ]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    rejected = checks["hub_federation_pins_accepted"]
    assert not rejected.ok
    # Naming the peer is the whole head start: the reason field was empty in the real
    # incident, so "one peer is rejected" would have sent someone hunting.
    assert "atlas" in rejected.detail
    assert "repin" in rejected.detail
    # A rejected pin leaves the catalogue non-empty, which is why this check exists.
    assert checks["hub_federation_peers"].ok


def test_a_peer_frozen_for_days_fails_the_freshness_check(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([
        _peer("gaia", crawled_h_ago=0.2),
        _peer("atlas", crawled_h_ago=5 * 24),
    ]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    stale = checks["hub_federation_crawl_fresh"]
    assert not stale.ok
    assert "atlas" in stale.detail


def test_a_recent_crawl_on_every_peer_is_fresh(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([
        _peer("gaia", crawled_h_ago=1), _peer("atlas", crawled_h_ago=20),
    ]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    assert checks["hub_federation_crawl_fresh"].ok


def test_the_stale_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("AICOM_ALERT_PEER_STALE_HOURS", "2")
    monkeypatch.setattr(alert, "_get", _peers_response([_peer("atlas", crawled_h_ago=6)]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    assert not checks["hub_federation_crawl_fresh"].ok


def test_no_parseable_crawl_stamp_is_a_finding_not_a_pass(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([
        {"name": "odd", "url": "https://odd.example", "status": "active",
         "last_crawl": "never"},
    ]))
    checks = _by_name(alert.probe_federation("https://hub.example"))
    assert not checks["hub_federation_crawl_fresh"].ok


def test_an_unreachable_peers_endpoint_is_one_failure_not_an_exception(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (0, None, "TimeoutError: timed out"))
    checks = alert.probe_federation("https://hub.example")
    assert len(checks) == 1 and not checks[0].ok
    assert checks[0].name == "hub_federation_peers"


def test_a_peer_list_of_the_wrong_shape_does_not_crash(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {"peers": "nope"}, ""))
    checks = alert.probe_federation("https://hub.example")
    assert len(checks) == 1 and not checks[0].ok


def test_federation_checks_are_part_of_a_normal_collect(monkeypatch):
    monkeypatch.setattr(alert, "probe_dns", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_hub", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_status_page", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_settlement", lambda *a, **k: [])
    monkeypatch.setattr(alert, "_get", _peers_response([_peer("atlas")]))
    names = {c.name for c in alert.collect(
        "quick", hub="https://hub.example", signer="", status_url="https://s.example",
        settlement_url="https://t.example", timeout=5.0,
    )}
    assert "hub_federation_pins_accepted" in names
    assert "hub_federation_crawl_fresh" in names


# ── Multi-hub federation watching ───────────────────────────────────────────
#
# Each hub keeps its own peer index. Signal Hunt sat with two peers un-recrawled
# for 21 days while the apex hub's index was perfectly fresh, and nothing watched
# it, so the freeze was found only by looking on purpose.


def test_federation_label_is_the_host():
    assert alert._federation_label("https://hunt.modelmarket.dev") == "hunt.modelmarket.dev"
    assert alert._federation_label("https://hunt.modelmarket.dev/") == "hunt.modelmarket.dev"
    assert alert._federation_label("hunt.modelmarket.dev") == "hunt.modelmarket.dev"
    assert alert._federation_label("http://108.165.32.182:9083") == "108.165.32.182:9083"


def test_primary_hub_check_names_are_unchanged(monkeypatch):
    """The state history is keyed on these names; renaming them would orphan it."""
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {"peers": [
        {"name": "GAIA", "status": "active", "last_crawl": "2026-09-01T10:00:00Z"},
    ]}, ""))
    names = {c.name for c in alert.probe_federation("https://hub.example")}
    assert names == {
        "hub_federation_peers",
        "hub_federation_pins_accepted",
        "hub_federation_crawl_fresh",
    }


def test_a_labelled_hub_gets_its_own_check_names(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {"peers": [
        {"name": "GAIA", "status": "active", "last_crawl": "2026-09-01T10:00:00Z"},
    ]}, ""))
    names = {c.name for c in alert.probe_federation(
        "https://hunt.example", label="hunt.example")}
    assert names == {
        "hub_federation_peers@hunt.example",
        "hub_federation_pins_accepted@hunt.example",
        "hub_federation_crawl_fresh@hunt.example",
    }


def test_a_labelled_hub_reports_its_own_frozen_peer(monkeypatch):
    """The 21-day freeze, as the check would have seen it."""
    monkeypatch.setattr(alert, "_get", _peers_response([
        _peer("AIMarket Hub", crawled_h_ago=21 * 24),
    ]))
    checks = {c.name: c for c in alert.probe_federation(
        "https://hunt.example", label="hunt.example")}
    frozen = checks["hub_federation_crawl_fresh@hunt.example"]
    assert not frozen.ok
    assert "AIMarket Hub" in frozen.detail
    # Named per hub, so a stale secondary cannot be mistaken for the apex going stale.
    assert "hub_federation_crawl_fresh" not in checks


def test_extra_hubs_parse_from_env(monkeypatch):
    monkeypatch.delenv("AICOM_ALERT_FEDERATION_HUBS", raising=False)
    assert alert.federation_hubs_from_env("https://modelmarket.dev") == []
    assert alert.federation_hubs_from_env(
        "https://modelmarket.dev", "https://hunt.modelmarket.dev, uni.modelmarket.dev",
    ) == ["https://hunt.modelmarket.dev", "https://uni.modelmarket.dev"]


def test_the_primary_hub_is_never_watched_twice(monkeypatch):
    """A duplicate would emit a second check with the same name and silently
    overwrite the first one's failure count."""
    assert alert.federation_hubs_from_env(
        "https://modelmarket.dev", "https://modelmarket.dev/, https://hunt.modelmarket.dev",
    ) == ["https://hunt.modelmarket.dev"]
    assert alert.federation_hubs_from_env(
        "https://modelmarket.dev", "https://hunt.modelmarket.dev, http://hunt.modelmarket.dev",
    ) == ["https://hunt.modelmarket.dev"]


def test_collect_emits_one_federation_block_per_hub(monkeypatch):
    monkeypatch.setattr(alert, "probe_dns", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_hub", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_signer", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_status_page", lambda *a, **k: [])
    monkeypatch.setattr(alert, "probe_settlement", lambda *a, **k: [])
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {"peers": [
        {"name": "GAIA", "status": "active", "last_crawl": "2026-09-01T10:00:00Z"},
    ]}, ""))
    checks = alert.collect(
        "quick", hub="https://modelmarket.dev", signer="", status_url="",
        settlement_url="", timeout=5.0,
        federation_hubs=["https://hunt.modelmarket.dev"],
    )
    names = {c.name for c in checks}
    assert "hub_federation_peers" in names
    assert "hub_federation_peers@hunt.modelmarket.dev" in names
    assert len(names) == len(checks)  # no duplicate state keys


# ── Discovery, and naming an independent node ───────────────────────────────
#
# A hand-kept watch list has the failure mode it is meant to fix: two hubs kept their
# own peer indexes, both went 21 days without re-crawling a peer, and nobody knew
# because nobody had listed them. An earlier version of this file patched that with a
# completeness check plus an "ignore" list for hubs judged not ours to watch. The
# federation is open — hubs join without asking — so "ours" is not a property this
# alerter can read, and the hub that got classified as somebody else's had a rejected
# key pin at that very moment. Nothing is classified now, and nothing is silenced.


def _federation_map(mapping):
    """_get stub: url prefix -> peer list, for the primary hub and each probed peer."""
    def _stub(url, timeout=0, *a, **k):
        for prefix, peers in mapping.items():
            if url.startswith(prefix.rstrip("/")):
                return 200, {"peers": peers}, ""
        return 404, None, "not found"
    return _stub


def test_discovery_finds_hubs_and_skips_satellites(monkeypatch):
    monkeypatch.setattr(alert, "_get", _federation_map({
        "https://apex.example": [
            {"url": "https://hunt.example", "name": "Signal Hunt"},
            {"url": "https://atlas.example", "name": "ATLAS"},
        ],
        "https://hunt.example": [{"url": "https://apex.example", "name": "Apex"}],
        "https://atlas.example": [],          # a satellite keeps no peer index
    }))
    assert alert.discover_federation_hubs("https://apex.example") == ["https://hunt.example"]


def test_discovery_survives_an_unreadable_primary(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (0, None, "timed out"))
    assert alert.discover_federation_hubs("https://apex.example") == []


def test_a_discovered_hub_is_watched_in_full_mode(monkeypatch):
    for probe in ("probe_dns", "probe_hub", "probe_signer", "probe_status_page",
                  "probe_settlement", "probe_paywall"):
        monkeypatch.setattr(alert, probe, lambda *a, **k: [])
    monkeypatch.setattr(alert, "discover_federation_hubs",
                        lambda *a, **k: ["https://stranger.example/hub"])
    monkeypatch.setattr(alert, "_get", _federation_map({
        "https://": [{"url": "https://x.example", "name": "X",
                      "status": "active", "last_crawl": "2026-09-01T10:00:00Z"}],
    }))
    quick = {c.name for c in alert.collect("quick", hub="https://apex.example", signer="",
                                           status_url="", settlement_url="", timeout=5.0,
                                           federation_hubs=[])}
    full = {c.name for c in alert.collect("full", hub="https://apex.example", signer="",
                                          status_url="", settlement_url="", timeout=5.0,
                                          federation_hubs=[])}
    # Discovery costs a request per peer, so it is the hourly mode that does it.
    assert not any("stranger.example" in n for n in quick)
    assert "hub_federation_crawl_fresh@stranger.example" in full


def test_a_discovered_hub_already_configured_is_not_probed_twice(monkeypatch):
    for probe in ("probe_dns", "probe_hub", "probe_signer", "probe_status_page",
                  "probe_settlement", "probe_paywall"):
        monkeypatch.setattr(alert, probe, lambda *a, **k: [])
    monkeypatch.setattr(alert, "discover_federation_hubs",
                        lambda *a, **k: ["https://hunt.example"])
    monkeypatch.setattr(alert, "_get", _federation_map({
        "https://": [{"url": "https://x.example", "name": "X",
                      "status": "active", "last_crawl": "2026-09-01T10:00:00Z"}],
    }))
    checks = alert.collect("full", hub="https://apex.example", signer="", status_url="",
                           settlement_url="", timeout=5.0,
                           federation_hubs=["https://hunt.example"])
    names = [c.name for c in checks]
    assert len(names) == len(set(names))
    assert names.count("hub_federation_peers@hunt.example") == 1


# An independent node of an open federation is a standard hub on someone else's server.
# It is watched like any other; the alias is so a page says which one it is.

def test_an_alias_names_the_hub_on_the_page():
    assert alert._split_hub_entry("independent=https://independentai.network/hub") == (
        "independent", "https://independentai.network/hub")
    assert alert._split_hub_entry("independent=independentai.network/hub") == (
        "independent", "https://independentai.network/hub")


def test_a_bare_url_falls_back_to_its_host():
    assert alert._split_hub_entry("https://hunt.modelmarket.dev") == (
        "hunt.modelmarket.dev", "https://hunt.modelmarket.dev")
    assert alert._split_hub_entry("http://108.165.32.182:9083") == (
        "108.165.32.182:9083", "http://108.165.32.182:9083")


def test_an_aliased_hub_reports_under_its_alias(monkeypatch):
    monkeypatch.setattr(alert, "_get", _peers_response([
        _peer("AIMarket Hub", crawled_h_ago=21 * 24),
    ]))
    checks = {c.name: c for c in alert.probe_federation(
        "https://independentai.network/hub", label="independent")}
    frozen = checks["hub_federation_crawl_fresh@independent"]
    assert not frozen.ok and "AIMarket Hub" in frozen.detail


def test_aliases_are_deduped_by_host_not_by_label():
    """Two aliases for one hub would be probed twice under two names."""
    assert alert.federation_hubs_from_env(
        "https://apex.example",
        "independent=https://independentai.network/hub, "
        "indie=https://independentai.network/hub",
    ) == ["independent=https://independentai.network/hub"]


def test_nothing_can_be_silenced():
    """There is no ignore list any more — the concept is gone from the module."""
    assert not hasattr(alert, "probe_federation_watchlist")
    assert "FEDERATION_HUBS_IGNORE" not in Path(alert.__file__).read_text()


# ── the credit rail: a seller that cannot be paid ────────────────────────────────────────
# Publishing capabilities and opening accounts work with a lesser credential than
# crediting one, so a wrong Hub admin token looks healthy until the first payment.
# These pin that the canary reads the verdict, and that every way of not knowing
# is reported as a failure rather than as silence.


def _seller(rail):
    import json as _json

    class Response:
        status = 200
        def read(self):
            return _json.dumps({"status": "ok", "credit_rail": rail}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    return Response()


def _patch_get(monkeypatch, response):
    def fake(url, timeout, headers=None):
        if isinstance(response, Exception):
            return 0, None, type(response).__name__
        return 200, response, ""
    monkeypatch.setattr(alert, "_get", fake)


def test_credit_rail_passes_when_the_seller_can_credit(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok", "credit_rail": {
        "enabled": True, "hub_credit_admin": "ok", "detail": "hub answered 400",
        "checked_at": "2026-09-02T06:40:00Z"}})
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    by_name = {c.name: c for c in checks}
    assert any(name.startswith("credit_rail_can_credit") for name in by_name)
    assert all(c.ok for c in checks)


def test_credit_rail_pages_when_the_hub_refuses_the_token(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok", "credit_rail": {
        "enabled": True, "hub_credit_admin": "denied",
        "detail": "hub refused the admin token",
        "checked_at": "2026-09-02T06:40:00Z"}})
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    failed = [c for c in checks if not c.ok]
    assert len(failed) == 1
    assert failed[0].critical is True
    assert "denied" in failed[0].detail


def test_credit_rail_unreachable_hub_is_not_critical_but_is_not_a_pass(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok", "credit_rail": {
        "enabled": True, "hub_credit_admin": "unreachable",
        "detail": "hub unreachable: ConnectError",
        "checked_at": "2026-09-02T06:40:00Z"}})
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    rail = next(c for c in checks if c.name.startswith("credit_rail_can_credit"))
    assert rail.ok is False
    # A network blip must not page; only a refusal is a decision.
    assert rail.critical is False


def test_an_old_build_that_publishes_no_verdict_is_a_failure_not_silence(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok"})
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    assert [c.name for c in checks if not c.ok] == ["credit_rail_published[seller.example/aegis]"]


def test_a_seller_with_selling_switched_off_is_quiet(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok", "credit_rail": {
        "enabled": False, "hub_credit_admin": "unconfigured"}})
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    assert all(c.ok for c in checks)
    assert all(not c.critical for c in checks)


def test_no_sellers_configured_adds_no_checks():
    assert alert.probe_credit_rail([]) == []
    assert alert.probe_credit_rail(["", "  "]) == []


def test_an_unreachable_seller_is_reported(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda url, timeout, headers=None: (0, None, "ConnectError"))
    checks = alert.probe_credit_rail(["https://seller.example/aegis"])
    assert len(checks) == 1
    assert checks[0].ok is False
    assert "ConnectError" in checks[0].detail


def test_two_sellers_on_one_domain_get_distinct_check_names(monkeypatch):
    _patch_get(monkeypatch, {"status": "ok", "credit_rail": {
        "enabled": True, "hub_credit_admin": "ok", "checked_at": "2026-09-02T06:40:00Z"}})
    checks = alert.probe_credit_rail(
        ["https://independentai.network/aegis", "https://independentai.network/kova"])
    names = [c.name for c in checks]
    assert len(set(names)) == len(names)
    assert "credit_rail_can_credit[independentai.network/aegis]" in names
    assert "credit_rail_can_credit[independentai.network/kova]" in names
