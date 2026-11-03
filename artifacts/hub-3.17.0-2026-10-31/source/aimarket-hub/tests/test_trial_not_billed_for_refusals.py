"""A free trial buys a result, not an attempt.

Measured on production before this existed. A caller sending the documented envelope but
omitting ``source_hub`` got five straight refusals, each carrying the exact hint needed to
fix the call — ``fourier.spectrum@v1 is federated, not local — retry with source_hub=...`` —
and the sixth was refused for ``trial_quota_exhausted``, ``used 5 / max 5``. Five helpful
error messages, zero results, allowance gone. The same happened through a plugin block
(``403 plugin_blocked_response``).

The hub already had the right discipline for money and the wrong one for the free tier. Its
own comment on the paid path says a hold is taken "before the peer is asked to do anything"
so that "a peer that 402s, times out or returns garbage never costs the buyer anything",
and it counts nine exits between reservation and response. The free tier was debited at the
door with no release.

Two changes are covered here:

* the debit moved to *after* validation, so the eight refusals that precede any execution
  attempt cannot spend anything;
* the ledger gained ``release``, paired in the same ``finally`` that hands back the payment
  hold, for the exits after execution begins.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

_ROUTES = Path(__file__).resolve().parents[1] / "aimarket_hub" / "hub_routes"


def _invoke_source() -> str:
    """The invoke path's source in call order: the route, then each branch's phases."""
    parts = ("local_admission", "local_delivery", "federated_admission", "federated_delivery")
    files = [_ROUTES / "invoke.py"] + [_ROUTES / "invoke_parts" / f"{p}.py" for p in parts]
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """A fresh windowed ledger with a small allowance, so exhaustion is cheap to reach."""
    monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(tmp_path / "trials.db"))
    monkeypatch.setenv("AIMARKET_SANDBOX_QUOTA_WINDOW", "hourly")
    monkeypatch.setenv("AIMARKET_SANDBOX_MAX_PER_VISITOR", "3")
    monkeypatch.setenv("AIMARKET_SANDBOX_ENABLED", "1")
    import aimarket_hub.sandbox_trials as st

    importlib.reload(st)
    return st


VISITOR = "visitor-abcdefgh"


def test_release_hands_back_exactly_one(ledger):
    for _ in range(2):
        assert ledger.consume_sandbox_trial(VISITOR).get("ok") is True
    assert ledger.sandbox_quota(VISITOR)["used"] == 2

    out = ledger.release_sandbox_trial(VISITOR)
    assert out["ok"] is True
    assert out["released"] is True
    assert out["used"] == 1
    assert ledger.sandbox_quota(VISITOR)["used"] == 1
    assert ledger.sandbox_quota(VISITOR)["remaining"] == 2


def test_the_production_scenario_no_longer_exhausts_the_tier(ledger):
    """Five refusals then a real call: the caller must still be served.

    This is the exact shape of the observed failure, expressed against the ledger: every
    refused attempt is consumed-then-released, and the allowance must be intact afterwards.
    """
    for _ in range(5):
        assert ledger.consume_sandbox_trial(VISITOR).get("ok") is True
        ledger.release_sandbox_trial(VISITOR)          # the refusal path
    assert ledger.sandbox_quota(VISITOR)["used"] == 0
    assert ledger.sandbox_quota(VISITOR)["remaining"] == 3

    served = ledger.consume_sandbox_trial(VISITOR)     # the call that delivers
    assert served.get("ok") is True
    assert ledger.sandbox_quota(VISITOR)["used"] == 1


def test_a_delivered_call_is_still_billed(ledger):
    """The fix must not make the tier free. Consume without release still counts."""
    for expected in (1, 2, 3):
        assert ledger.consume_sandbox_trial(VISITOR).get("ok") is True
        assert ledger.sandbox_quota(VISITOR)["used"] == expected
    exhausted = ledger.consume_sandbox_trial(VISITOR)
    assert exhausted.get("error") == "trial_quota_exhausted"
    assert exhausted["used"] == 3


def test_release_never_goes_negative(ledger):
    """A stray release must not mint free calls in this window or the next.

    Releases run from a ``finally``, so a double-release is a live possibility (an exception
    during an already-released path). Floor it rather than trust the caller.
    """
    for _ in range(4):
        ledger.release_sandbox_trial(VISITOR)
    assert ledger.sandbox_quota(VISITOR)["used"] == 0
    assert ledger.sandbox_quota(VISITOR)["remaining"] == 3

    ledger.consume_sandbox_trial(VISITOR)
    for _ in range(3):
        ledger.release_sandbox_trial(VISITOR)
    assert ledger.sandbox_quota(VISITOR)["used"] == 0


def test_release_of_an_unknown_visitor_is_a_no_op(ledger):
    out = ledger.release_sandbox_trial("never-seen-before-id")
    assert out["ok"] is True
    assert out["released"] is False


def test_release_rejects_a_malformed_visitor_id(ledger):
    """Same validation as consume: a short id is not a visitor, so it holds no allowance."""
    assert ledger.release_sandbox_trial("short")["error"] == "invalid_visitor_id"


def test_release_is_scoped_to_the_current_window(ledger, monkeypatch):
    """A release must not reach back into a window that has already closed.

    Otherwise a refusal straddling the hour boundary would credit an allowance the caller
    can no longer spend, and — worse — could decrement the *new* window it never used.
    """
    ledger.consume_sandbox_trial(VISITOR)
    assert ledger.sandbox_quota(VISITOR)["used"] == 1

    # Move to the next hourly window.
    real_key = ledger.current_window_key
    monkeypatch.setattr(ledger, "current_window_key", lambda now=None: real_key() + "-next")

    assert ledger.sandbox_quota(VISITOR)["used"] == 0, "new window starts clean"
    out = ledger.release_sandbox_trial(VISITOR)
    assert out["released"] is False, "nothing to release in a window with no usage"
    assert ledger.sandbox_quota(VISITOR)["used"] == 0


def test_lifetime_window_also_releases(ledger, monkeypatch):
    """The un-windowed table is a separate code path and needs the same guarantee."""
    monkeypatch.setenv("AIMARKET_SANDBOX_QUOTA_WINDOW", "lifetime")
    import aimarket_hub.sandbox_trials as st

    importlib.reload(st)
    assert st.quota_window() == "lifetime"

    st.consume_sandbox_trial(VISITOR)
    st.consume_sandbox_trial(VISITOR)
    assert st.sandbox_quota(VISITOR)["used"] == 2
    assert st.release_sandbox_trial(VISITOR)["used"] == 1
    assert st.sandbox_quota(VISITOR)["used"] == 1


def test_the_network_cap_is_not_refunded(ledger, monkeypatch):
    """Deliberate asymmetry, worth pinning so nobody "fixes" it.

    The per-visitor allowance is a promise about delivered value, so a refusal returns it.
    The per-network counter bounds load, and a refused call consumed real work — refunding
    it would turn the network cap into no cap at all for a caller that fails on purpose.
    """
    monkeypatch.setenv("AIMARKET_SANDBOX_MAX_PER_IP_HOUR", "2")
    import aimarket_hub.sandbox_trials as st

    importlib.reload(st)

    ip = "203.0.113.7"
    assert st.consume_sandbox_trial("visitor-aaaaaaaa", client_ip=ip).get("ok") is True
    st.release_sandbox_trial("visitor-aaaaaaaa")
    assert st.consume_sandbox_trial("visitor-bbbbbbbb", client_ip=ip).get("ok") is True
    st.release_sandbox_trial("visitor-bbbbbbbb")

    blocked = st.consume_sandbox_trial("visitor-cccccccc", client_ip=ip)
    assert blocked.get("error") == "rate_limit_exceeded", (
        "releases must not restore the network budget"
    )


def test_api_takes_the_trial_after_validation_not_before():
    """Structural: in the local invoke branch the debit must follow the refusals.

    The bug was ordering, not arithmetic — a release cannot help a path that returns before
    the ``finally`` exists. Asserting on source order is blunt, but it is the property that
    actually broke, and it breaks again the moment someone moves the block back up.
    """
    text = _invoke_source()

    consume_at = text.index("trial = consume_sandbox_trial(x_sandbox_visitor or \"\", client_ip=client_ip)")
    federated_refusal_at = text.index("is federated, not local — retry with ")
    assert federated_refusal_at < consume_at, (
        "the 'federated, not local' refusal must be reachable without spending a trial"
    )
    assert "release_sandbox_trial" in text, "no release paired with the debit"
    # One call in the local branch's finally, one in the federated branch's. Both invoke
    # paths spend a trial, so both need the release; a single call means one was forgotten.
    assert text.count("release_sandbox_trial(") == 2, (
        "expected exactly one release in each of the local and federated finally blocks, "
        f"found {text.count('release_sandbox_trial(')}"
    )


def test_the_published_status_matches_what_the_hub_actually_answers(ledger):
    """A contract an agent branches on must not describe a different code than the code.

    The published text said 402 while the invoke path answers 429 trial_quota_exhausted —
    written when the tier was lifetime and never corrected when it became a renewing window.
    An agent that trusted it would read a temporary refusal as "must pay", abandon a free
    tier it still had, and not come back.
    """
    policy = ledger.trial_policy()
    assert policy["exhausted_error"] == "trial_quota_exhausted"
    assert policy["exhausted_status"] == 429, "hourly window renews, so 429 is the honest code"
    assert "429" in policy["how"]
    assert "402" not in policy["how"]

    api = _invoke_source()
    assert 'code = 429 if trial["error"] in ("trial_quota_exhausted"' in api, (
        "the invoke path no longer answers 429 for an exhausted trial; the published policy "
        "text and exhausted_status must move with it"
    )


def test_a_lifetime_tier_publishes_402_instead(ledger, monkeypatch):
    """With no renewal there is nothing to wait for, so 'payment required' is the truth."""
    import importlib

    monkeypatch.setenv("AIMARKET_SANDBOX_QUOTA_WINDOW", "lifetime")
    import aimarket_hub.sandbox_trials as st

    importlib.reload(st)
    policy = st.trial_policy()
    assert policy["exhausted_status"] == 402
    assert "402" in policy["how"]
    assert "renews" not in policy["how"]


def test_the_policy_states_that_refusals_are_free(ledger):
    """The property a caller most needs before spending its first call, said out loud."""
    how = ledger.trial_policy()["how"].lower()
    assert "refused call costs nothing" in how


def test_model_backed_capabilities_are_outside_the_free_tier(ledger):
    """The free tier's justification does not hold for a capability that calls a paid model.

    Found live: platon.ask@v1 ($0.003), platon.oracle@v1 ($0.02, "LLM mathematical witness")
    and platon.steer@v1 ($0.005) were all served on the free tier through hub federation, and
    a direct call returned a genuinely composed answer — order parameter, Lyapunov exponent,
    prose reasoning — so the tokens were real money. Worse than free: the visitor id is
    self-chosen, so rotating it bypasses the per-caller cap and the exposure is unbounded.
    """
    for cap in ("platon.ask@v1", "platon.oracle@v1", "platon.steer@v1"):
        assert ledger.free_tier_covers(cap) is False, cap
    # A capability whose cost really is noise stays free.
    for cap in ("fourier.spectrum@v1", "platon.random@v1", "atlas.situation.brief@v1"):
        assert ledger.free_tier_covers(cap) is True, cap


def test_the_refusal_explains_itself_and_offers_a_way_forward(ledger):
    body = ledger.model_budget_refusal("platon.ask@v1")
    assert body["error"] == "model_budget_not_free"
    assert "paid model" in body["detail"]
    assert any("payment channel" in s for s in body["how_to_continue"])


def test_the_exclusion_list_is_operator_tunable(ledger, monkeypatch):
    """A new LLM-backed SKU appears on a peer, not here, so this must change from outside."""
    monkeypatch.setenv("AIMARKET_SANDBOX_MODEL_BACKED", "some.new@v1, other.thing@v1")
    import importlib
    import aimarket_hub.sandbox_trials as st

    importlib.reload(st)
    assert st.free_tier_covers("some.new@v1") is False
    assert st.free_tier_covers("other.thing@v1") is False
    assert st.free_tier_covers("platon.ask@v1") is True, "an explicit list replaces the default"


def test_the_exclusion_is_published_so_nobody_learns_it_by_being_refused(ledger):
    policy = ledger.trial_policy()
    assert "platon.ask@v1" in policy["excluded_capabilities"]
    # Says WHY, without claiming a cause that does not apply. The list stopped being
    # model-only when ATLAS's `situation.brief` joined it — a sensor brief with no model in
    # it — and "each call spends paid model budget" would have been a false explanation for
    # a true refusal.
    reason = policy["excluded_reason"]
    assert "real budget" in reason and "not free to serve" in reason


def test_the_refusal_happens_before_the_trial_is_spent():
    """Structural: discovering that a capability is not free must not cost an allowance."""
    api = _invoke_source()
    assert api.count("free_tier_covers(") == 2, "both invoke branches must check"
    for _ in range(2):
        guard_at = api.index("free_tier_covers(")
        consume_at = api.index("consume_sandbox_trial(", guard_at)
        assert guard_at < consume_at, "the free-tier check must precede the debit"
        api = api[consume_at:]
