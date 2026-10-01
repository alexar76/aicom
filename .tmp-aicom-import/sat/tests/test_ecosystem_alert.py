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
import re
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


@pytest.fixture(autouse=True)
def _neutral_environment(monkeypatch):
    """The mechanics tests run with every domain in scope and English wording; the tests
    for scope and for the Russian page set their own. E-mail stays off unless a test wires
    it, and no POST ever leaves the machine."""
    monkeypatch.setenv("AICOM_ALERT_SCOPE", "*")
    monkeypatch.setenv("AICOM_ALERT_LANG", "en")
    for var in ("AICOM_ALERT_EMAIL_TO", "AICOM_ALERT_SMTP_HOST", "AICOM_ALERT_SMTP_USER",
                "AICOM_ALERT_SMTP_PASSWORD", "AICOM_ALERT_SMTP_PORT", "AICOM_ALERT_EMAIL_FROM"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(alert, "_post", lambda *a, **k: (0, None, "offline in tests"))


# ── flap protection ──────────────────────────────────────────────────────────────────────

def test_single_failure_does_not_page():
    """A deploy restarts the hub. One bad poll is not an incident."""
    state = fresh_state()
    state["last_heartbeat"] = alert._iso(NOW - 3600)  # the digest is not what is under test
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


def test_the_digest_keeps_coming_while_something_critical_is_down():
    """It used to be withheld during an outage, so an incident that stayed open made the
    alerter go quiet for its whole length — eight days, once, in which silence meant
    "still broken" and "dead" alike. The digest now comes on its clock regardless; what it
    must never do is call an outage green."""
    state = fresh_state()
    sent = []
    for i in range(4):
        checks = [C("hub_manifest", False, "down")]
        broke, fixed, hb = alert.decide(checks, state, flap=2, heartbeat_hours=0,
                                        now=NOW + i * 600)
        if hb:
            sent.append(alert.format_message(checks, broke, fixed, hb, host="h",
                                             hub="https://x", when="t", state=state,
                                             now=NOW + i * 600))
    assert sent, "no digest during an outage"
    for text in sent:
        assert "all good" not in text
        assert "is not serving its catalogue" in text and "open for" in text


def test_a_run_that_pages_does_not_also_send_the_digest():
    state = fresh_state()
    alert.decide([C("hub_manifest", False)], state, flap=2, heartbeat_hours=0, now=NOW)
    broke, _, hb = alert.decide([C("hub_manifest", False)], state, flap=2,
                                heartbeat_hours=0, now=NOW + 600)
    assert broke == ["hub_manifest"] and hb is False


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
    assert "The escrow signer halted itself" in text          # what, in words
    assert "Impact: it stopped on purpose" in text               # why it matters
    assert "Evidence: HALTED: ledger unavailable" in text        # the proof
    assert "oracles" in text and "2026-08-25 07:00 UTC" in text
    assert "--dry-run" in text  # actionable at 3am, not just informative


def test_recovery_message_says_recovered():
    text = alert.format_message([C("hub_manifest", True)], [], ["hub_manifest"], False,
                                host="h", hub="https://x", when="t")
    assert "recovered" in text.lower()
    assert "Hub x is serving its catalogue again" in text


def test_heartbeat_message_carries_the_warnings_nobody_was_paged_for():
    checks = [C("hub_manifest", True), C("hub_stats_live", False, "502", critical=False)]
    text = alert.format_message(checks, [], [], True, host="h", hub="https://x", when="t")
    assert "1 of 2 checks OK" in text
    assert "Live stats of hub x are not answering" in text


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
    assert len(sent) == 1 and "daily digest — all good" in sent[0]
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


def _peer(name: str, *, status: str = "active", crawled_h_ago: float = 0.5,
          url: str = "") -> dict:
    stamp = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - crawled_h_ago * 3600)
    )
    return {"name": name, "url": url or f"https://{name}.example", "status": status,
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
# key pin at that very moment. The alerter still classifies nothing; since 2026-09-24 the
# owner declares the scope (a list of domains), and what it leaves out is named in the
# digest rather than dropped.


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


def test_nothing_is_silenced_silently():
    """There is no ignore list — the concept is gone from the module. What the owner's
    scope leaves out is not hidden: every digest names it."""
    assert not hasattr(alert, "probe_federation_watchlist")
    assert "FEDERATION_HUBS_IGNORE" not in Path(alert.__file__).read_text()
    scope = alert.Scope(("modelmarket.dev",))
    assert not scope.allows("https://independentai.network/hub")
    text = alert.format_message([C("hub_manifest", True)], [], [], True, host="h",
                                hub="https://modelmarket.dev", when="t", lang="ru",
                                state=fresh_state(), scope=scope, now=NOW)
    assert "independentai.network" in text and "Не наблюдаю" in text


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


class TestTlsExpiryIsWatchedBeforeItBecomesAnOutage:
    """`probe_dns` refuses an expired certificate — on the day the outage starts.

    Renewal runs 30 days before expiry, so a certificate with under three weeks left has
    already missed an attempt and will miss the next one for the same reason. That is the
    window where a message is still useful. Found worth adding on 2026-09-07, when
    `my-vps` — thirteen lineages including modelmarket.dev and both hubs — turned out to
    have no deploy hook at all, meaning a renewed certificate might never have been loaded
    and nothing would have said so until it expired.
    """

    def _probe(self, monkeypatch, days_left, *, raises=None):
        import datetime as real_datetime

        not_after = (real_datetime.datetime.utcnow()
                     + real_datetime.timedelta(days=days_left))

        class FakeTLS:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def getpeercert(self):
                return {"notAfter": not_after.strftime("%b %d %H:%M:%S %Y GMT")}

        class FakeCtx:
            def wrap_socket(self, raw, server_hostname=None):
                if raises:
                    raise raises
                return FakeTLS()

        class FakeSock:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(alert.socket, "create_connection",
                            lambda *a, **k: FakeSock())
        monkeypatch.setattr(alert.ssl, "create_default_context", lambda: FakeCtx())
        return alert.probe_tls_expiry(["example.test"])[0]

    def test_a_healthy_certificate_is_quiet(self, monkeypatch):
        check = self._probe(monkeypatch, 60)
        assert check.ok and "60d left" in check.detail

    def test_a_certificate_that_missed_its_renewal_window_is_flagged(self, monkeypatch):
        check = self._probe(monkeypatch, 12)
        assert not check.ok
        assert "12d" in check.detail and "not running" in check.detail

    def test_the_boundary_belongs_to_the_healthy_side(self, monkeypatch):
        assert self._probe(monkeypatch, 21).ok
        assert not self._probe(monkeypatch, 20).ok

    def test_it_never_pages_anyone(self, monkeypatch):
        """A certificate with 20 days left is a note, not an incident."""
        assert self._probe(monkeypatch, 5).critical is False
        assert self._probe(monkeypatch, 90).critical is False

    def test_unreachable_is_not_reported_as_expiring(self, monkeypatch):
        """"Could not measure" and "about to expire" are different claims — and the first
        one is `probe_dns`'s to shout about, not this probe's."""
        check = self._probe(monkeypatch, 60, raises=OSError("connection refused"))
        assert check.ok and "not measured" in check.detail

    def test_the_watched_list_covers_the_estate_and_can_be_overridden(self, monkeypatch):
        monkeypatch.delenv("AICOM_ALERT_TLS_NAMES", raising=False)
        names = alert.tls_names_from_env("https://modelmarket.dev")
        for expected in ("modelmarket.dev", "uni.modelmarket.dev", "hub.modelmarket.dev",
                         "magic-ai-factory.com"):
            assert expected in names, expected
        # Other ecosystems renew their own certificates (the owner's scope, 2026-09-24).
        for foreign in ("hub.attestedmemory.net", "memory.attestedmemory.net",
                        "independentai.network"):
            assert foreign not in names, foreign

        monkeypatch.setenv("AICOM_ALERT_TLS_NAMES", "one.test, two.test")
        assert alert.tls_names_from_env("https://modelmarket.dev") == ["one.test", "two.test"]

        # Empty switches the check off rather than falling back to the defaults, so an
        # operator who does not want it does not have to fight it.
        monkeypatch.setenv("AICOM_ALERT_TLS_NAMES", "")
        assert alert.tls_names_from_env("https://modelmarket.dev") == []

    def test_the_hub_being_watched_is_always_included(self, monkeypatch):
        monkeypatch.delenv("AICOM_ALERT_TLS_NAMES", raising=False)
        names = alert.tls_names_from_env("https://some-other-hub.example/hub")
        assert "some-other-hub.example" in names


class TestTlsExpiryIsWatchedBeforeItBecomesAnOutage:
    """`probe_dns` refuses an expired certificate — on the day the outage starts.

    Renewal runs 30 days before expiry, so a certificate with under three weeks left has
    already missed an attempt and will miss the next one for the same reason. That is the
    window where a message is still useful. Found worth adding on 2026-09-07, when
    `my-vps` — thirteen lineages including modelmarket.dev and both hubs — turned out to
    have no deploy hook at all, meaning a renewed certificate might never have been loaded
    into nginx and nothing would have said so until it expired.
    """

    def _probe(self, monkeypatch, days_left, *, raises=None):
        import datetime as real_datetime

        # A minute of slack, because the probe truncates the remainder: without it the
        # microseconds spent reaching the assertion turn "60 days" into 59. Truncation is
        # the safe direction for the probe — it under-reports the time left — so the test
        # accommodates it rather than the other way round.
        not_after = (real_datetime.datetime.utcnow()
                     + real_datetime.timedelta(days=days_left, minutes=1))

        class FakeTLS:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def getpeercert(self):
                return {"notAfter": not_after.strftime("%b %d %H:%M:%S %Y GMT")}

        class FakeCtx:
            def wrap_socket(self, raw, server_hostname=None):
                if raises:
                    raise raises
                return FakeTLS()

        class FakeSock:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(alert.socket, "create_connection", lambda *a, **k: FakeSock())
        monkeypatch.setattr(alert.ssl, "create_default_context", lambda: FakeCtx())
        return alert.probe_tls_expiry(["example.test"])[0]

    def test_a_healthy_certificate_is_quiet(self, monkeypatch):
        check = self._probe(monkeypatch, 60)
        assert check.ok and "60d left" in check.detail

    def test_a_certificate_that_missed_its_renewal_window_is_flagged(self, monkeypatch):
        check = self._probe(monkeypatch, 12)
        assert not check.ok
        assert "12d" in check.detail and "not running" in check.detail

    def test_the_boundary_belongs_to_the_healthy_side(self, monkeypatch):
        assert self._probe(monkeypatch, 21).ok
        assert not self._probe(monkeypatch, 20).ok

    def test_it_never_pages_anyone(self, monkeypatch):
        """A certificate with 20 days left is a note, not an incident."""
        assert self._probe(monkeypatch, 5).critical is False
        assert self._probe(monkeypatch, 90).critical is False

    def test_unreachable_is_not_reported_as_expiring(self, monkeypatch):
        """"Could not measure" and "about to expire" are different claims — and the first
        is `probe_dns`'s to shout about, not this probe's."""
        check = self._probe(monkeypatch, 60, raises=OSError("connection refused"))
        assert check.ok and "not measured" in check.detail

    def test_the_watched_list_covers_the_estate_and_can_be_overridden(self, monkeypatch):
        monkeypatch.delenv("AICOM_ALERT_TLS_NAMES", raising=False)
        names = alert.tls_names_from_env("https://modelmarket.dev")
        for expected in ("modelmarket.dev", "uni.modelmarket.dev", "hub.modelmarket.dev",
                         "magic-ai-factory.com"):
            assert expected in names, expected
        # Other ecosystems renew their own certificates (the owner's scope, 2026-09-24).
        for foreign in ("hub.attestedmemory.net", "memory.attestedmemory.net",
                        "independentai.network"):
            assert foreign not in names, foreign

        monkeypatch.setenv("AICOM_ALERT_TLS_NAMES", "one.test, two.test")
        assert alert.tls_names_from_env("https://modelmarket.dev") == ["one.test", "two.test"]

        # Empty switches the check off rather than falling back to the defaults, so an
        # operator who does not want it does not have to fight it.
        monkeypatch.setenv("AICOM_ALERT_TLS_NAMES", "")
        assert alert.tls_names_from_env("https://modelmarket.dev") == []

    def test_the_hub_being_watched_is_always_included(self, monkeypatch):
        monkeypatch.delenv("AICOM_ALERT_TLS_NAMES", raising=False)
        names = alert.tls_names_from_env("https://some-other-hub.example/hub")
        assert "some-other-hub.example" in names


# ── scope: the alexar76 ecosystem, as the owner declared it on 2026-09-24 ─────────────────


class TestScope:
    def test_the_default_is_the_alexar76_ecosystem(self, monkeypatch):
        monkeypatch.delenv("AICOM_ALERT_SCOPE", raising=False)
        scope = alert.Scope.from_env()
        for ours in ("https://modelmarket.dev", "https://uni.modelmarket.dev/sat/khronos",
                     "hub.modelmarket.dev", "https://magic-ai-factory.com", "local",
                     "http://127.0.0.1:9500"):
            assert scope.allows(ours), ours
        for theirs in ("https://independentai.network/hub", "https://charon.independentai.network",
                       "https://hub.attestedmemory.net", "https://emberlinedesk.com",
                       "https://pingblip.com", "http://108.165.32.182:9083",
                       "https://notmodelmarket.dev"):
            assert not scope.allows(theirs), theirs
        assert "independentai.network" in scope.excluded
        assert "notmodelmarket.dev" in scope.excluded  # a suffix is not a subdomain

    def test_star_watches_everything_and_a_list_overrides(self, monkeypatch):
        monkeypatch.setenv("AICOM_ALERT_SCOPE", "*")
        assert alert.Scope.from_env().allows("https://anything.example")
        monkeypatch.setenv("AICOM_ALERT_SCOPE", "Example.org, .other.test")
        scope = alert.Scope.from_env()
        assert scope.allows("https://a.example.org") and scope.allows("https://other.test")
        assert not scope.allows("https://modelmarket.dev")

    def test_a_foreign_peer_does_not_turn_our_hub_red(self, monkeypatch):
        """Our hub not re-crawling somebody else's node is that node's operator's business."""
        monkeypatch.setattr(alert, "_get", _peers_response([
            _peer("GAIA", crawled_h_ago=1, url="https://iot.modelmarket.dev"),
            _peer("Attested Hub", crawled_h_ago=21 * 24, url="https://hub.attestedmemory.net",
                  status="key_mismatch"),
        ]))
        scope = alert.Scope(("modelmarket.dev",))
        checks = {c.name: c for c in alert.probe_federation(
            "https://modelmarket.dev", scope=scope)}
        assert checks["hub_federation_crawl_fresh"].ok
        assert checks["hub_federation_pins_accepted"].ok
        assert "1 outside the watched scope" in checks["hub_federation_peers"].detail
        assert "hub.attestedmemory.net" in scope.excluded

    def test_our_own_frozen_peer_still_fails_under_the_scope(self, monkeypatch):
        monkeypatch.setattr(alert, "_get", _peers_response([
            _peer("KHRONOS", crawled_h_ago=198, url="https://uni.modelmarket.dev/sat/khronos"),
        ]))
        checks = {c.name: c for c in alert.probe_federation(
            "https://uni.modelmarket.dev", label="uni.modelmarket.dev",
            scope=alert.Scope(("modelmarket.dev",)))}
        assert not checks["hub_federation_crawl_fresh@uni.modelmarket.dev"].ok

    def test_collect_neither_probes_nor_discovers_other_ecosystems(self, monkeypatch):
        for probe in ("probe_dns", "probe_hub", "probe_signer", "probe_status_page",
                      "probe_settlement", "probe_paywall", "probe_tls_expiry"):
            monkeypatch.setattr(alert, probe, lambda *a, **k: [])
        probed: list[str] = []
        monkeypatch.setattr(alert, "probe_hub_identity",
                            lambda hub, *a, **k: probed.append(hub) or [])
        monkeypatch.setattr(alert, "_get", _federation_map({
            "https://modelmarket.dev": [
                {"url": "https://hunt.modelmarket.dev", "name": "Hunt"},
                {"url": "https://hub.attestedmemory.net", "name": "Attested"},
            ],
            "https://hunt.modelmarket.dev": [{"url": "https://modelmarket.dev", "name": "Apex",
                                              "last_crawl": "2026-09-01T10:00:00Z"}],
            "https://hub.attestedmemory.net": [{"url": "https://x", "name": "X"}],
            "https://independentai.network/hub": [{"url": "https://x", "name": "X"}],
        }))
        scope = alert.Scope(("modelmarket.dev",))
        names = {c.name for c in alert.collect(
            "full", hub="https://modelmarket.dev", signer="", status_url="", settlement_url="",
            timeout=5.0, federation_hubs=["independent=https://independentai.network/hub"],
            scope=scope)}
        assert "hub_federation_peers@hunt.modelmarket.dev" in names
        assert not any("independent" in n or "attestedmemory" in n for n in names)
        assert "https://hub.attestedmemory.net" not in probed
        assert "https://hunt.modelmarket.dev" in probed

    def test_foreign_canary_failures_do_not_count(self, monkeypatch):
        monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
            "checked_at": alert._iso(NOW - 3600),
            "checks": [
                {"name": "priced_capability_gated[https://independentai.network/hub]",
                 "ok": False, "critical": True},
                {"name": "peer_alive[https://hub.attestedmemory.net]", "ok": False,
                 "critical": True},
            ]}, ""))
        scope = alert.Scope(("modelmarket.dev",))
        checks = {c.name: c for c in alert.probe_status_page("https://v/s.json", now=NOW,
                                                             scope=scope)}
        assert checks["canary_verdict_ok"].ok
        # ...while one of ours still does.
        monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, {
            "checked_at": alert._iso(NOW - 3600),
            "checks": [{"name": "peer_alive[https://iot.modelmarket.dev]", "ok": False,
                        "critical": True}]}, ""))
        checks = {c.name: c for c in alert.probe_status_page("https://v/s.json", now=NOW,
                                                             scope=scope)}
        assert not checks["canary_verdict_ok"].ok

    def test_the_paywall_is_judged_over_our_providers_only(self, monkeypatch):
        import payment_canary
        monkeypatch.setattr(payment_canary, "observe", lambda hub, timeout, **k: {
            "manifest": {"name": "m", "payment_configured": True, "payment_testnet": False,
                         "_priced_providers": ["local", "https://iot.modelmarket.dev",
                                               "https://independentai.network/hub"]},
            "probes": [
                {"status": 402, "body": {}, "capability_id": "a", "source_hub": "local"},
                {"status": 402, "body": {}, "capability_id": "b",
                 "source_hub": "https://iot.modelmarket.dev"},
                {"status": 200, "body": {}, "capability_id": "c",
                 "source_hub": "https://independentai.network/hub"},
            ],
            "mcp_info": {"service": "aimarket-hub-mcp", "trial": "per-caller"},
            "peers": [{"url": "https://hub.attestedmemory.net", "alive": False, "sells": True}],
        })
        checks = {c.name: c for c in alert.probe_paywall(
            "https://modelmarket.dev", 5.0, scope=alert.Scope(("modelmarket.dev",)))}
        assert checks["every_priced_provider_probed"].ok
        assert not any("independentai" in n or "attestedmemory" in n for n in checks)
        assert all(c.ok for c in checks.values() if c.critical)


# ── a redeploy must not be able to undo a fix unnoticed ─────────────────────────────────


def _identity_stub(monkeypatch, *, well_known, credit_status, credit_body=None):
    monkeypatch.setattr(alert, "_get", lambda url, *a, **k: (200, well_known, ""))
    calls = []
    def post(url, payload, timeout, headers=None):
        calls.append((url, payload, headers))
        return credit_status, credit_body, ""
    monkeypatch.setattr(alert, "_post", post)
    return calls


class TestHubIdentity:
    GOOD = {"hub_url": "https://uni.modelmarket.dev",
            "manifest_url": "https://uni.modelmarket.dev/ai-market/v2/manifest",
            "mcp_endpoint": "https://uni.modelmarket.dev/ai-market/mcp"}

    def test_a_healthy_hub_passes_both(self, monkeypatch):
        _identity_stub(monkeypatch, well_known=self.GOOD, credit_status=403)
        checks = {c.name: c for c in alert.probe_hub_identity("https://uni.modelmarket.dev",
                                                              label="uni")}
        assert checks["hub_advertises_public_url@uni"].ok
        assert checks["hub_refuses_published_admin_tokens@uni"].ok
        assert f"all {len(alert.PUBLISHED_ADMIN_TOKENS)}" in \
            checks["hub_refuses_published_admin_tokens@uni"].detail

    def test_advertising_loopback_is_the_uni_regression(self, monkeypatch):
        """What UNI advertised for eight days after the stale script was re-run."""
        _identity_stub(monkeypatch, well_known=dict(
            self.GOOD, manifest_url="http://127.0.0.1:9183/ai-market/v2/manifest"),
            credit_status=403)
        check = {c.name: c for c in alert.probe_hub_identity("https://uni.modelmarket.dev")}[
            "hub_advertises_public_url"]
        assert not check.ok and check.critical and "127.0.0.1" in check.detail

    def test_private_and_plaintext_addresses_are_not_public(self):
        for bad in ("http://modelmarket.dev/x", "https://10.0.0.5/x", "https://localhost/x",
                    "https://[::1]/x", "https://172.17.0.1:9083"):
            assert not alert._publicly_reachable(bad), bad
        assert alert._publicly_reachable("https://uni.modelmarket.dev/ai-market/mcp")

    def test_an_accepted_published_token_pages(self, monkeypatch):
        """Past the token, the amount is not a number: the hub answers 400 and writes nothing."""
        calls = _identity_stub(monkeypatch, well_known=self.GOOD, credit_status=400,
                               credit_body={"detail": "amount_usd must be a number"})
        check = {c.name: c for c in alert.probe_hub_identity("https://uni.modelmarket.dev")}[
            "hub_refuses_published_admin_tokens"]
        assert not check.ok and check.critical and "OPENS" in check.detail
        # The probe itself must be unable to move a cent.
        for url, payload, headers in calls:
            assert url.endswith("/accounts/acct_0000000000000000/credit")
            with pytest.raises(ValueError):
                float(payload["amount_usd"])

    def test_admin_switched_off_is_a_closed_door(self, monkeypatch):
        _identity_stub(monkeypatch, well_known=self.GOOD, credit_status=503, credit_body={
            "detail": "Admin endpoints disabled: AIMARKET_ADMIN_TOKEN not configured"})
        check = {c.name: c for c in alert.probe_hub_identity("https://x.modelmarket.dev")}[
            "hub_refuses_published_admin_tokens"]
        assert check.ok

    def test_a_503_after_the_token_is_an_open_door(self, monkeypatch):
        _identity_stub(monkeypatch, well_known=self.GOOD, credit_status=503,
                       credit_body={"detail": "credit accounts are off on this hub"})
        check = {c.name: c for c in alert.probe_hub_identity("https://x.modelmarket.dev")}[
            "hub_refuses_published_admin_tokens"]
        assert not check.ok

    def test_no_route_is_not_measured_rather_than_passed_or_paged(self, monkeypatch):
        _identity_stub(monkeypatch, well_known=self.GOOD, credit_status=404)
        check = {c.name: c for c in alert.probe_hub_identity("https://x.modelmarket.dev")}[
            "hub_refuses_published_admin_tokens"]
        assert check.ok and not check.critical and "not measured" in check.detail

    def test_the_uni_constant_is_on_the_list(self):
        assert "uni-admin-token-not-a-secret-in-a-bubble" in alert.PUBLISHED_ADMIN_TOKENS
        docs = (ROOT / "docs" / "uni-realm.md").read_text(encoding="utf-8")
        assert "uni-admin-token-not-a-secret-in-a-bubble" in docs  # that is why it is listed


# ── the page a human reads ───────────────────────────────────────────────────────────────


class TestRussianPage:
    def test_a_failure_says_what_broke_why_it_matters_and_the_evidence(self):
        checks = [C("hub_federation_crawl_fresh@uni.modelmarket.dev", False,
                    "stalest peer crawl: KHRONOS Time Series 198.5h ago (threshold 26h)"),
                  C("hub_manifest", True)]
        text = alert.format_message(checks, [checks[0].name], [], False, host="not-my-vps",
                                    hub="https://modelmarket.dev", when="2026-09-24 11:00 UTC",
                                    lang="ru", state=fresh_state(), now=NOW)
        assert "Хаб uni.modelmarket.dev перестал обновлять данные пиров" in text
        assert "Чем грозит:" in text and "Факт: stalest peer crawl: KHRONOS" in text
        assert "not-my-vps" in text and "--dry-run" in text

    def test_a_digest_during_an_outage_says_how_long_it_has_been_open(self):
        state = fresh_state()
        state["checks"]["hub_federation_crawl_fresh@uni"] = {
            "failures": 400, "alerted": True, "since": alert._iso(NOW - 8 * 86400 - 7 * 3600)}
        checks = [C("hub_federation_crawl_fresh@uni", False, "stale"), C("hub_manifest", True)]
        text = alert.format_message(checks, [], [], True, host="h", hub="https://modelmarket.dev",
                                    when="t", lang="ru", state=state,
                                    scope=alert.Scope(("modelmarket.dev",)), now=NOW)
        assert "открыто проблем: 1" in text
        assert "уже 8 сут 7 ч" in text
        assert "всё в порядке" not in text
        assert "Следующая сводка" in text and "Наблюдаю: modelmarket.dev" in text

    def test_a_recovery_says_how_long_it_lasted(self):
        state = fresh_state()
        for i in range(2):
            alert.decide([C("hub_manifest", False, "down")], state, flap=2, heartbeat_hours=24,
                         now=NOW + i * 600)
        _, fixed, _ = alert.decide([C("hub_manifest", True)], state, flap=2, heartbeat_hours=24,
                                   now=NOW + 3 * 3600)
        text = alert.format_message([C("hub_manifest", True)], [], fixed, False, host="h",
                                    hub="https://modelmarket.dev", when="t", lang="ru",
                                    state=state, now=NOW + 3 * 3600)
        assert "починилось" in text and "Хаб modelmarket.dev снова отдаёт каталог" in text
        assert "было сломано 3 ч" in text

    def test_every_check_this_file_can_emit_has_words(self):
        """A new probe without wording would reach the owner as a bare identifier."""
        src = Path(alert.__file__).read_text(encoding="utf-8")
        emitted = set(re.findall(r'Check\(\s*f?"([a-z_]+)', src))
        import payment_canary
        emitted |= set(re.findall(r'(?:Check\(\s*|name = )f?"([a-z_]+)',
                                  Path(payment_canary.__file__).read_text(encoding="utf-8")))
        emitted.discard("x")
        for lang, table in alert._WORDING.items():
            missing = sorted(n for n in emitted if n not in table)
            assert not missing, (lang, missing)
        assert set(alert._PHRASES["en"]) == set(alert._PHRASES["ru"])

    def test_a_failing_channel_is_reported_by_the_one_that_works(self):
        delivery = {"telegram": {"ok": True, "at": "2026-09-24T10:00:00Z"},
                    "email": {"ok": False, "at": "2026-09-24T10:00:00Z",
                              "error": "SMTPAuthenticationError: 535",
                              "failing_since": "2026-09-23T08:00:00Z"}}
        checks = [C("hub_manifest", False, "down")]
        text = alert.format_message(checks, ["hub_manifest"], [], False, host="h",
                                    hub="https://modelmarket.dev", when="t", lang="ru",
                                    state=fresh_state(), delivery=delivery, now=NOW)
        assert "почта ✗" in text and "535" in text and "2026-09-23" in text

    def test_the_russian_page_fits_telegram(self):
        checks = [C(f"peer_alive[https://s{i}.modelmarket.dev]", False, "x" * 300)
                  for i in range(40)]
        text = alert.format_message(checks, [c.name for c in checks], [], False, host="h",
                                    hub="https://x", when="t", lang="ru", state=fresh_state(),
                                    now=NOW)
        assert len(text) < 4000


# ── e-mail ───────────────────────────────────────────────────────────────────────────────


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.events, self.sent = host, port, [], []
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.events.append("starttls")

    def login(self, user, password):
        self.events.append(("login", user))

    def send_message(self, msg):
        self.sent.append(msg)
        return {}

    def quit(self):
        self.events.append("quit")

    def close(self):
        self.events.append("close")


class TestEmail:
    CFG = {"host": "smtp.example", "port": 587, "user": "bot@example.org",
           "password": "pw", "from": "bot@example.org", "to": ["owner@example.org"]}

    def test_starttls_comes_before_the_password(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(alert.smtplib, "SMTP", FakeSMTP)
        ok, info = alert.send_email(self.CFG, "🔴 alexar76: сломалось — 1\nтело")
        assert ok, info
        server = FakeSMTP.instances[0]
        assert server.events[:2] == ["starttls", ("login", "bot@example.org")]
        msg = server.sent[0]
        assert msg["Subject"] == "🔴 alexar76: сломалось — 1"
        assert msg["To"] == "owner@example.org"
        assert "тело" in msg.get_content()

    def test_port_465_is_implicit_tls(self, monkeypatch):
        FakeSMTP.instances.clear()
        monkeypatch.setattr(alert.smtplib, "SMTP_SSL", FakeSMTP)
        def forbidden(*a, **k):
            raise AssertionError("plain SMTP must not be used on 465")
        monkeypatch.setattr(alert.smtplib, "SMTP", forbidden)
        ok, _ = alert.send_email(dict(self.CFG, port=465), "subject\nbody")
        assert ok and "starttls" not in FakeSMTP.instances[0].events

    def test_a_refused_starttls_sends_nothing_and_never_raises(self, monkeypatch):
        class NoTLS(FakeSMTP):
            def starttls(self, context=None):
                raise alert.smtplib.SMTPNotSupportedError("STARTTLS extension not supported")
        FakeSMTP.instances.clear()
        monkeypatch.setattr(alert.smtplib, "SMTP", NoTLS)
        ok, info = alert.send_email(self.CFG, "s\nb")
        assert not ok and "STARTTLS" in info
        assert not FakeSMTP.instances[0].sent
        assert ("login", "bot@example.org") not in FakeSMTP.instances[0].events

    def test_email_is_off_until_both_recipient_and_server_are_set(self, monkeypatch):
        assert alert.email_config_from_env() is None
        monkeypatch.setenv("AICOM_ALERT_EMAIL_TO", "owner@example.org")
        assert alert.email_config_from_env() is None
        monkeypatch.setenv("AICOM_ALERT_SMTP_HOST", "smtp.example")
        monkeypatch.setenv("AICOM_ALERT_SMTP_USER", "bot@example.org")
        cfg = alert.email_config_from_env()
        assert cfg["port"] == 587 and cfg["from"] == "bot@example.org"

    def test_the_password_is_never_a_command_line_argument(self):
        src = (ROOT / "scripts" / "ecosystem_alert.py").read_text(encoding="utf-8")
        assert "--password" not in src and "--smtp" not in src


class TestDelivery:
    def _run(self, monkeypatch, tmp_path, *, telegram_ok, email_ok, checks=None):
        monkeypatch.setattr(alert, "collect",
                            lambda *a, **k: checks or [C("hub_manifest", True, "ok")])
        sent = {"telegram": [], "email": []}
        monkeypatch.setattr(alert, "send_telegram", lambda t, c, text, **k: (
            sent["telegram"].append(text) or (telegram_ok, "1" if telegram_ok else "HTTP 502")))
        monkeypatch.setattr(alert, "send_email", lambda cfg, text, **k: (
            sent["email"].append(text) or (email_ok, "sent" if email_ok else "SMTP 535")))
        monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
        monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
        monkeypatch.setenv("AICOM_ALERT_EMAIL_TO", "owner@example.org")
        monkeypatch.setenv("AICOM_ALERT_SMTP_HOST", "smtp.example")
        state = tmp_path / "state.json"
        rc = alert.main(["--state", str(state)])
        return rc, sent, json.loads(state.read_text())

    def test_both_channels_get_the_same_message(self, monkeypatch, tmp_path):
        rc, sent, state = self._run(monkeypatch, tmp_path, telegram_ok=True, email_ok=True)
        assert rc == 0 and len(sent["telegram"]) == 1 and sent["telegram"] == sent["email"]
        assert state["delivery"]["email"]["ok"] and state["delivery"]["telegram"]["ok"]

    def test_one_channel_down_still_counts_as_told_and_is_remembered(self, monkeypatch, tmp_path):
        rc, _, state = self._run(monkeypatch, tmp_path, telegram_ok=True, email_ok=False)
        assert state["last_heartbeat"]  # the human was reached, the digest is done
        assert state["delivery"]["email"]["ok"] is False
        assert state["delivery"]["email"]["error"] == "SMTP 535"

    def test_every_channel_down_means_nobody_was_told(self, monkeypatch, tmp_path):
        rc, _, state = self._run(monkeypatch, tmp_path, telegram_ok=False, email_ok=False)
        assert rc == 1
        assert state["last_heartbeat"] == ""  # so the next run tries again

    def test_failing_since_survives_repeated_failures(self):
        state = fresh_state()
        chans = [("email", lambda text: (False, "down"))]
        alert.deliver(chans, "x", state, NOW)
        alert.deliver(chans, "x", state, NOW + 3600)
        assert state["delivery"]["email"]["failing_since"] == alert._iso(NOW)
        alert.deliver([("email", lambda text: (True, "sent"))], "x", state, NOW + 7200)
        assert state["delivery"]["email"] == {"ok": True, "at": alert._iso(NOW + 7200)}


def test_the_canary_contacts_nothing_outside_the_scope(monkeypatch):
    """Discarding a result is not the same as not asking: every hourly probe of somebody
    else's service landed in their logs."""
    import payment_canary
    asked: list[str] = []
    def fake_get(url, timeout):
        asked.append(url)
        if url.endswith("/ai-market/v2/prices"):
            return 200, {"prices": [
                {"price_usd": 0.01, "capability_id": "a", "product_id": "p",
                 "source_hub": "https://iot.modelmarket.dev"},
                {"price_usd": 0.01, "capability_id": "b", "product_id": "p",
                 "source_hub": "https://independentai.network/hub"},
            ]}
        if url.endswith("/federation/peers"):
            return 200, {"peers": [{"url": "https://iot.modelmarket.dev"},
                                   {"url": "https://hub.attestedmemory.net"}]}
        return 200, {}
    posted: list[dict] = []
    monkeypatch.setattr(payment_canary, "_get", fake_get)
    monkeypatch.setattr(payment_canary, "_post",
                        lambda url, body, timeout: posted.append(body) or (402, {}))
    peered: list[str] = []
    monkeypatch.setattr(payment_canary, "probe_peer",
                        lambda entry, *a, **k: peered.append(entry["url"]) or dict(entry, alive=True))
    scope = alert.Scope(("modelmarket.dev",))
    seen = payment_canary.observe("https://modelmarket.dev", 5.0, allow=scope.allows)
    assert [b.get("source_hub") for b in posted] == ["https://iot.modelmarket.dev"]
    assert peered == ["https://iot.modelmarket.dev"]
    assert seen["manifest"] is None or "independentai" not in str(
        seen["manifest"].get("_priced_providers"))



class TestEnglishPageIsTheDefault:
    """The owner asked for English (2026-09-24); the plain-language shape is the same."""

    def test_default_language_is_english(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AICOM_ALERT_LANG", raising=False)
        monkeypatch.setattr(alert, "collect", lambda *a, **k: [C("hub_manifest", True, "ok")])
        sent = []
        monkeypatch.setattr(alert, "send_telegram",
                            lambda token, chat, text, **k: (sent.append(text) or (True, "1")))
        monkeypatch.setenv("AICOM_ALERT_TELEGRAM_TOKEN", "123:abc")
        monkeypatch.setenv("AICOM_ALERT_TELEGRAM_CHAT", "42")
        alert.main(["--state", str(tmp_path / "s.json")])
        assert sent and "daily digest — all good" in sent[0] and "Next digest in" in sent[0]

    def test_a_failure_in_english(self):
        checks = [C("hub_federation_crawl_fresh@uni.modelmarket.dev", False,
                    "stalest peer crawl: KHRONOS Time Series 198.5h ago (threshold 26h)")]
        text = alert.format_message(checks, [checks[0].name], [], False, host="not-my-vps",
                                    hub="https://modelmarket.dev", when="t",
                                    state=fresh_state(), now=NOW)
        assert text.startswith("\U0001F534 alexar76: 1 broken")
        assert "✖ Hub uni.modelmarket.dev stopped refreshing its peers" in text
        assert "Impact: its catalogue shows stale capabilities and prices" in text
        assert "Evidence: stalest peer crawl: KHRONOS" in text

    def test_an_english_digest_during_an_outage(self):
        state = fresh_state()
        state["checks"]["hub_federation_crawl_fresh@uni"] = {
            "failures": 400, "alerted": True, "since": alert._iso(NOW - 8 * 86400 - 7 * 3600)}
        scope = alert.Scope(("modelmarket.dev",))
        scope.allows("https://hub.attestedmemory.net")
        checks = [C("hub_federation_crawl_fresh@uni", False, "stale"), C("hub_manifest", True)]
        text = alert.format_message(checks, [], [], True, host="h", hub="https://modelmarket.dev",
                                    when="t", state=state, scope=scope, now=NOW)
        assert "daily digest — 1 open" in text and "open for 8d 7h" in text
        assert "Not watched (other ecosystems, owner's decision): hub.attestedmemory.net" in text
        assert "Delivery: Telegram — no sends yet · e-mail — not configured" in text

    def test_an_english_recovery_says_how_long_it_lasted(self):
        state = fresh_state()
        for i in range(2):
            alert.decide([C("signer_ready", False)], state, flap=2, heartbeat_hours=24,
                         now=NOW + i * 600)
        _, fixed, _ = alert.decide([C("signer_ready", True)], state, flap=2,
                                   heartbeat_hours=24, now=NOW + 26 * 3600)
        text = alert.format_message([C("signer_ready", True)], [], fixed, False, host="h",
                                    hub="https://x", when="t", state=state, now=NOW + 26 * 3600)
        assert "✔ The escrow signer is ready again (was broken for 26h)" in text

    def test_an_unknown_language_falls_back_to_english(self):
        text = alert.format_message([C("hub_manifest", True)], [], [], True, host="h",
                                    hub="https://x", when="t", lang="de", now=NOW)
        assert "all good" in text
