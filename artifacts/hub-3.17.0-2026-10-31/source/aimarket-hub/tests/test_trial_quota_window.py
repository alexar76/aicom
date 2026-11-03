"""The free allowance is a revenue/engagement dial, not a fixed grant.

lifetime = three invokes ever, then pay (revenue).
daily/hourly/weekly = the allowance comes back, so a returning agent keeps using the
hub between purchases (engagement).
"""

import importlib

import pytest


def _ledger(tmp_path, monkeypatch, window=None, maximum="3"):
    monkeypatch.setenv("AIMARKET_SANDBOX_MAX_PER_VISITOR", maximum)
    monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(tmp_path / "trials.db"))
    if window is None:
        monkeypatch.delenv("AIMARKET_SANDBOX_QUOTA_WINDOW", raising=False)
    else:
        monkeypatch.setenv("AIMARKET_SANDBOX_QUOTA_WINDOW", window)
    mod = importlib.reload(importlib.import_module("aimarket_hub.sandbox_trials"))
    return mod, mod.SandboxTrialLedger(str(tmp_path / "trials.db"))


def test_default_is_lifetime_so_behaviour_is_unchanged(tmp_path, monkeypatch):
    mod, led = _ledger(tmp_path, monkeypatch)
    assert mod.quota_window() == "lifetime"
    assert mod.current_window_key() == ""
    for _ in range(3):
        assert "error" not in led.consume("visitor-aaaa")
    assert led.consume("visitor-aaaa")["error"] == "trial_quota_exhausted"


def test_daily_window_renews_the_allowance(tmp_path, monkeypatch):
    mod, led = _ledger(tmp_path, monkeypatch, window="daily")
    for _ in range(3):
        assert "error" not in led.consume("visitor-bbbb")
    assert led.consume("visitor-bbbb")["error"] == "trial_quota_exhausted"

    # Next day: same visitor, fresh allowance.
    tomorrow = mod.time.time() + 86400
    monkeypatch.setattr(mod, "current_window_key", lambda now=None: mod.time.strftime("%Y-%m-%d", mod.time.gmtime(tomorrow)))
    assert "error" not in led.consume("visitor-bbbb")
    assert led.quota("visitor-bbbb")["used"] == 1


def test_switching_window_does_not_forgive_the_lifetime_ledger(tmp_path, monkeypatch):
    """Counters are keyed by window, so a switch starts a period — it does not refund."""
    mod, led = _ledger(tmp_path, monkeypatch)          # lifetime
    for _ in range(3):
        led.consume("visitor-cccc")
    assert led.consume("visitor-cccc")["error"] == "trial_quota_exhausted"

    mod2, led2 = _ledger(tmp_path, monkeypatch, window="daily")
    assert "error" not in led2.consume("visitor-cccc")  # new period, by design

    mod3, led3 = _ledger(tmp_path, monkeypatch)         # back to lifetime
    assert led3.consume("visitor-cccc")["error"] == "trial_quota_exhausted", (
        "the lifetime ledger must still remember what was spent"
    )


def test_unknown_window_falls_back_to_the_strictest_setting(tmp_path, monkeypatch):
    """A typo must not silently grant an unlimited allowance."""
    mod, _ = _ledger(tmp_path, monkeypatch, window="montly")
    assert mod.quota_window() == "lifetime"


def test_policy_advertises_a_renewing_allowance(tmp_path, monkeypatch):
    mod, _ = _ledger(tmp_path, monkeypatch, window="daily")
    policy = mod.trial_policy()
    assert policy["quota_window"] == "daily"
    assert policy["renews"] is True
    assert "until the window renews" in policy["how"]

    mod2, _ = _ledger(tmp_path, monkeypatch)
    policy2 = mod2.trial_policy()
    assert policy2["renews"] is False
    # Asserts the advertised code, not the sentence tail: the wording now also tells the
    # caller what to do about it ("402; open a payment channel to continue"), and pinning the
    # final characters made a clearer message read as a regression.
    assert "402" in policy2["how"]
    assert "until the window renews" not in policy2["how"]
    assert policy2["exhausted_status"] == 402


def test_quota_reports_the_window(tmp_path, monkeypatch):
    mod, led = _ledger(tmp_path, monkeypatch, window="hourly")
    assert led.quota("visitor-dddd")["quota_window"] == "hourly"


def test_window_keys_differ_across_periods(tmp_path, monkeypatch):
    mod, _ = _ledger(tmp_path, monkeypatch, window="hourly")
    now = 1_700_000_000.0
    assert mod.current_window_key(now) != mod.current_window_key(now + 3600)
    assert mod.current_window_key(now) == mod.current_window_key(now + 60)


def _reload(tmp_path, monkeypatch, policy=None, env=None):
    """Fresh module with a policy file on disk and a chosen environment."""
    import json as _json
    for key in ("AIMARKET_SANDBOX_QUOTA_WINDOW", "AIMARKET_SANDBOX_MAX_PER_VISITOR",
                "AIMARKET_SANDBOX_MAX_PER_IP_HOUR"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(tmp_path / "t.db"))
    policy_path = tmp_path / "policy.json"
    if policy is not None:
        policy_path.write_text(_json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("AIMARKET_SANDBOX_POLICY_PATH", str(policy_path))
    mod = importlib.reload(importlib.import_module("aimarket_hub.sandbox_trials"))
    mod._policy_cache = (0.0, {})
    return mod


def test_policy_file_retunes_the_tier_without_a_redeploy(tmp_path, monkeypatch):
    mod = _reload(tmp_path, monkeypatch,
                  policy={"quota_window": "hourly", "max_per_visitor": 5, "max_per_ip_hour": 60})
    assert mod.quota_window() == "hourly"
    assert mod.max_per_visitor() == 5
    assert mod.max_per_ip_hour() == 60
    assert mod.trial_policy()["max_invokes_per_visitor"] == 5


def test_environment_beats_the_file(tmp_path, monkeypatch):
    """An explicit ops decision must not be overridden by a stray config file."""
    mod = _reload(tmp_path, monkeypatch,
                  policy={"quota_window": "hourly", "max_per_visitor": 99},
                  env={"AIMARKET_SANDBOX_QUOTA_WINDOW": "lifetime",
                       "AIMARKET_SANDBOX_MAX_PER_VISITOR": "3"})
    assert mod.quota_window() == "lifetime"
    assert mod.max_per_visitor() == 3


def test_no_file_keeps_the_code_defaults(tmp_path, monkeypatch):
    mod = _reload(tmp_path, monkeypatch)
    assert mod.quota_window() == "lifetime"
    assert mod.max_per_visitor() == 3
    assert mod.max_per_ip_hour() == 30


def test_a_broken_policy_file_is_ignored(tmp_path, monkeypatch):
    (tmp_path / "policy.json").write_text("{not json", encoding="utf-8")
    mod = _reload(tmp_path, monkeypatch)   # _reload points the module at policy.json
    assert mod.quota_window() == "lifetime"
    assert mod.max_per_visitor() == 3


def test_nonsense_values_fall_back_rather_than_disabling_the_limit(tmp_path, monkeypatch):
    mod = _reload(tmp_path, monkeypatch,
                  policy={"max_per_visitor": "plenty", "max_per_ip_hour": None})
    assert mod.max_per_visitor() == 3
    assert mod.max_per_ip_hour() == 30


def test_a_zero_allowance_cannot_be_configured(tmp_path, monkeypatch):
    """Flooring at 1 keeps a misconfiguration from silently closing the free tier."""
    mod = _reload(tmp_path, monkeypatch, policy={"max_per_visitor": 0})
    assert mod.max_per_visitor() == 1
