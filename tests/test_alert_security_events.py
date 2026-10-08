"""The fleet alerter watched uptime and money and no security event at all.

Two signals now page: the hub's aggregate security posture (signup farming against the
per-address limit, a key-guessing sweep on the credit rail, the daily signup-grant budget
running out), and the hot wallets — a balance under its floor, or money leaving one
faster than its normal gas spend within the last hour.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ecosystem_alert as alert  # noqa: E402

NOW = 1_800_000_000.0


def _posture(**over):
    body = {"window_s": 3600, "signups_refused": 0, "bad_api_key_attempts": 0,
            "signup_grant": {"daily_budget_usd": 5.0, "granted_24h_usd": 0.5,
                             "spent_fraction": 0.1}}
    body.update(over)
    return body


def _by_name(checks):
    return {c.name.split("@")[0]: c for c in checks}


def test_a_quiet_hub_is_green(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, _posture(), ""))
    checks = _by_name(alert.probe_security_posture("https://hub.example"))
    assert all(c.ok for c in checks.values()), [c.detail for c in checks.values()]
    assert {"security_signup_farming", "security_key_guessing", "security_grant_budget"} <= set(checks)


def test_signup_farming_pages(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, _posture(signups_refused=120), ""))
    c = _by_name(alert.probe_security_posture("https://hub.example"))["security_signup_farming"]
    assert c.ok is False and c.critical is True and "120" in c.detail


def test_a_key_guessing_sweep_pages(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, _posture(bad_api_key_attempts=900), ""))
    c = _by_name(alert.probe_security_posture("https://hub.example"))["security_key_guessing"]
    assert c.ok is False and c.critical is True


def test_a_spent_grant_budget_is_reported_without_paging(monkeypatch):
    grant = {"daily_budget_usd": 5.0, "granted_24h_usd": 4.6, "spent_fraction": 0.92}
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (200, _posture(signup_grant=grant), ""))
    c = _by_name(alert.probe_security_posture("https://hub.example"))["security_grant_budget"]
    assert c.ok is False and c.critical is False and "92" in c.detail


def test_a_hub_without_the_endpoint_does_not_page(monkeypatch):
    monkeypatch.setattr(alert, "_get", lambda *a, **k: (404, None, "HTTP 404"))
    checks = alert.probe_security_posture("https://old-hub.example")
    assert len(checks) == 1 and checks[0].critical is False


# ── hot wallets ──────────────────────────────────────────────────────────────────────────

WALLET = "0x" + "ab" * 20


def _rpc(eth_wei: int, usdc_units: int):
    def fake(url, payload, timeout, headers=None):
        method = payload["method"]
        if method == "eth_getBalance":
            return 200, {"result": hex(eth_wei)}, ""
        return 200, {"result": "0x" + format(usdc_units, "064x")}, ""
    return fake


def test_wallets_parse_from_the_environment():
    spec = f"sponsor={WALLET}:0.01, signer=0x{'cd' * 20}"
    parsed = alert.hot_wallets_from_env(spec)
    assert parsed == [("sponsor", WALLET, 0.01), ("signer", "0x" + "cd" * 20, 0.0)]


def test_a_wallet_under_its_floor_pages(monkeypatch):
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=10**15, usdc_units=0))   # 0.001 ETH
    history: dict = {}
    checks = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.01)], history,
                                              rpc="https://rpc.example", now=NOW))
    assert checks["hot_wallet_funded"].ok is False
    assert checks["hot_wallet_funded"].critical is True


def test_a_sudden_outflow_pages_and_stays_red_for_the_hour(monkeypatch):
    history: dict = {}
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**17, usdc_units=250_000_000))
    first = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW))
    assert first["hot_wallet_no_outflow"].ok is True

    # Ten minutes later the wallet is nearly empty: a drain, not gas.
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=10**15, usdc_units=0))
    later = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW + 600))
    assert later["hot_wallet_no_outflow"].ok is False
    assert later["hot_wallet_no_outflow"].critical is True
    assert "USDC" in later["hot_wallet_no_outflow"].detail

    # Still red on the next run, so the two-failure flap filter lets it page.
    again = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW + 1200))
    assert again["hot_wallet_no_outflow"].ok is False


def test_ordinary_gas_spend_is_not_an_outflow(monkeypatch):
    history: dict = {}
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**17, usdc_units=0))
    alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history, rpc="https://rpc.example", now=NOW)
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**17 - 3 * 10**13, usdc_units=0))
    later = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW + 600))
    assert later["hot_wallet_no_outflow"].ok is True


def test_a_gas_wallet_drained_to_dust_pages(monkeypatch):
    """Gas wallets hold ~0.0005 ETH: a fixed 0.005 threshold would miss them being emptied."""
    history: dict = {}
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**14, usdc_units=0))      # 0.0005
    alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history, rpc="https://rpc.example", now=NOW)
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=10**13, usdc_units=0))          # 0.00001
    later = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW + 600))
    assert later["hot_wallet_no_outflow"].ok is False


def test_a_gas_wallet_paying_gas_is_quiet(monkeypatch):
    history: dict = {}
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**14, usdc_units=0))
    alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history, rpc="https://rpc.example", now=NOW)
    monkeypatch.setattr(alert, "_post", _rpc(eth_wei=5 * 10**14 - 2 * 10**13, usdc_units=0))
    later = _by_name(alert.probe_hot_wallets([("sponsor", WALLET, 0.0)], history,
                                             rpc="https://rpc.example", now=NOW + 600))
    assert later["hot_wallet_no_outflow"].ok is True


def test_an_unreachable_rpc_does_not_page(monkeypatch):
    monkeypatch.setattr(alert, "_post", lambda *a, **k: (0, None, "timeout"))
    checks = alert.probe_hot_wallets([("sponsor", WALLET, 0.01)], {}, rpc="https://rpc.example", now=NOW)
    assert checks and all(c.critical is False for c in checks)


def test_every_new_check_has_wording_in_both_languages():
    for name in ("security_signup_farming", "security_key_guessing", "security_grant_budget",
                 "security_posture_published", "hot_wallet_funded", "hot_wallet_no_outflow",
                 "hot_wallet_readable"):
        assert name in alert._EN and name in alert._RU, name
