"""Recovery paths of Pay-on-Verified: what happens when the ledger or a worker fails.

Each test here pins one rule a mutation of the settlement code once broke without any
other test noticing:

  * a decided outcome whose ledger move failed is never signed; the sweep settles it later;
  * a replay of a decided policy refund still refunds (the decision carries force_refund);
  * the periodic sweep reclaims a verification or a hearing whose worker lease expired, and
    leaves a live one alone;
  * one row that raises does not stop the sweep for the rows after it;
  * an appeal worker whose lease was reclaimed cannot decide the outcome with its old token.
"""
from __future__ import annotations

import inspect
import aimarket_hub.channels as channels_mod
import aimarket_hub.verified_settlement as vs_mod
import pytest
from fastapi.testclient import TestClient

from tests import test_verified_appeals as T
from tests.test_verified_settlement import _insert_verifying_row


def _status(db, nonce):
    return T._row_state(db, nonce)


@pytest.mark.parametrize("first_passes", [True, False])
def test_a_failed_ledger_move_signs_nothing_and_the_sweep_settles_it_later(
        tmp_path, monkeypatch, first_passes):
    h = T._build(tmp_path, monkeypatch,
                 T._Court([("judged", first_passes, 0.95 if first_passes else 0.1)]),
                 T._Court([("judged", True, 0.9)]))
    with TestClient(h.app) as client:
        channel_id, _, nonce, _ = T._provisional(h, client, first_passes=first_passes)
        broken = lambda receipt_id: {"error": "ledger unavailable"}  # noqa: E731
        monkeypatch.setattr(vs_mod, "capture_hold", broken)
        monkeypatch.setattr(vs_mod, "release_hold", broken)

        assert T._close_window(h, client)["finalized"] == 0
        assert _status(h.db, nonce) == "finalizing"             # the decision is kept...
        rec = T._lookup(client, nonce)
        assert rec["verification"]["status"] == "provisional"   # ...but nothing is signed
        assert "rejection_receipt" not in rec
        assert T._holds(nonce)[0] == {nonce: "held"}
        assert T._reputation(h.db) == []
        assert h.hook.record_verified_failure.call_count == 0

        monkeypatch.setattr(vs_mod, "capture_hold", channels_mod.capture_hold)
        monkeypatch.setattr(vs_mod, "release_hold", channels_mod.release_hold)
        client.portal.call(h.svc.sweep_appeals)
        env = T._lookup(client, nonce)["verification"]
        assert env["status"] == ("settled" if first_passes else "refunded")
        assert h.signer.verify_verification_signature(env)
        T._assert_closed(channel_id, nonce, used=T.PRICE if first_passes else 0.0,
                         expect_holds={nonce: "captured" if first_passes else "released"})
        assert T._reputation(h.db) == ["verify_passed" if first_passes else "verify_failed"]


def test_a_replayed_policy_refund_still_refunds_under_a_fail_open_policy(tmp_path, monkeypatch):
    """A verifier that claims a pass below the operator's bar is refunded under ANY policy
    (force_refund). If the process dies after the decision is written, the replay reads that
    decision back — and under fail-open, dropping force_refund there would capture it."""
    monkeypatch.setenv("AIMARKET_VERIFY_FAIL_CLOSED", "0")
    h = T._build(tmp_path, monkeypatch, T._Court([]), T._Court([]))
    ledger = channels_mod._ledger
    opened = ledger.open(deposit_usd=T.DEPOSIT)["channel"]
    channel_id = opened["channel_id"]
    assert not ledger.hold(channel_id, T.PRICE, receipt_id="n_force",
                           secret=opened["channel_secret"]).get("error")
    _insert_verifying_row(h.db, nonce="n_force", channel_id=channel_id, price_usd=T.PRICE)
    row = h.svc._claim_worker("n_force", "pending", "verifying")
    assert row is not None

    def killed(*a, **k):
        raise RuntimeError("process killed before the ledger moved")

    # The raw staticmethod, wherever the class defines it (a mixin since the service was split).
    real = inspect.getattr_static(vs_mod.VerifiedSettlementService, "_settle_hold")
    monkeypatch.setattr(vs_mod.VerifiedSettlementService, "_settle_hold", staticmethod(killed))
    with pytest.raises(RuntimeError):
        h.svc._resolve_policy(row, None, cause="pass_below_bar", force_refund=True)
    assert _status(h.db, "n_force") == "finalizing"
    monkeypatch.setattr(vs_mod.VerifiedSettlementService, "_settle_hold", real)

    h.svc.sweep_appeals()
    rec = h.svc.lookup("n_force")
    assert rec["verification"]["status"] == "refunded"
    assert rec["rejection_receipt"]["reason"] == "pass_below_bar"
    assert ledger.hold_state("n_force") == "released"
    assert ledger.get(channel_id)["used_usd"] == pytest.approx(0.0)


def test_the_sweep_reclaims_expired_workers_and_leaves_live_ones(tmp_path, monkeypatch):
    h = T._build(tmp_path, monkeypatch, T._Court([]), T._Court([]))
    now = h.clock.t
    rows = {
        "pending": ("pending", 0),
        "verifying_dead": ("verifying", now - 1),
        "verifying_live": ("verifying", now + 60),
        "appealed": ("appealed", 0),
        "hearing_dead": ("appeal_verifying", now - 1),
        "hearing_live": ("appeal_verifying", now + 60),
    }
    for nonce, (status, lease) in rows.items():
        _insert_verifying_row(h.db, nonce=nonce)
        h.db._conn.execute("UPDATE verified_settlements SET status = ?, lease_until = ? WHERE nonce = ?",
                           (status, lease, nonce))
    h.db._conn.commit()
    verifications, hearings = [], []
    monkeypatch.setattr(h.svc, "_schedule", verifications.append)
    monkeypatch.setattr(h.svc, "_schedule_appeal",
                        lambda nonce, reclaim_stale=False: hearings.append((nonce, reclaim_stale)))

    assert h.svc.sweep_appeals()["appeals_queued"] == 2
    assert sorted(verifications) == ["pending", "verifying_dead"]
    assert sorted(hearings) == [("appealed", True), ("hearing_dead", True)]


def test_one_row_that_raises_does_not_stop_the_sweep(tmp_path, monkeypatch):
    h = T._build(tmp_path, monkeypatch, T._Court([("judged", True, 0.95)]), T._Court([("judged", True, 0.9)]))
    with TestClient(h.app) as client:
        first_channel, _, first, _ = T._provisional(h, client, first_passes=True)
        second_channel, _, second, _ = T._provisional(h, client, first_passes=True)
        real = h.svc._finalize_expired

        def poisoned(nonce):
            if nonce == first:
                raise RuntimeError("a row the sweep cannot read")
            return real(nonce)

        monkeypatch.setattr(h.svc, "_finalize_expired", poisoned)
        assert T._close_window(h, client)["finalized"] == 1
        assert _status(h.db, first) == "provisional"
        assert T._lookup(client, second)["verification"]["status"] == "settled"

        monkeypatch.setattr(h.svc, "_finalize_expired", real)
        assert client.portal.call(h.svc.sweep_appeals)["finalized"] == 1
        for channel_id, nonce in ((first_channel, first), (second_channel, second)):
            T._assert_closed(channel_id, nonce, used=T.PRICE, expect_holds={nonce: "captured"})


def test_a_reclaimed_hearing_cannot_be_decided_with_the_old_token(tmp_path, monkeypatch):
    """The court answered a worker whose lease had lapsed and been taken over. Its answer
    is dropped; only the current holder of the row decides — and the money moves once."""
    h = T._build(tmp_path, monkeypatch, T._Court([("judged", True, 0.95)]),
                 T._Court([("judged", False, 0.1)], trace="tr_court"))
    with TestClient(h.app) as client:
        channel_id, secret, nonce, _ = T._provisional(h, client, first_passes=True)
        monkeypatch.setattr(h.svc, "_schedule_appeal", lambda *a, **k: None)
        assert T._appeal(client, nonce, secret=secret).status_code == 202
        assert _status(h.db, nonce) == "appealed"

        old = h.svc._claim_worker(nonce, "appealed", "appeal_verifying")
        h.db._conn.execute("UPDATE verified_settlements SET lease_until = 0 WHERE nonce = ?", (nonce,))
        h.db._conn.commit()
        new = h.svc._claim_worker(nonce, "appealed", "appeal_verifying")
        assert old and new and old["worker_token"] != new["worker_token"]

        client.portal.call(h.svc._hear_appeal, old)
        after = h.svc._row(nonce)
        assert after["status"] == "appeal_verifying" and after["worker_token"] == new["worker_token"]
        assert not after["final_json"] and not after["appeal_json"]
        assert T._holds(nonce)[0] == {nonce: "held", f"appeal_{nonce}": "held"}

        client.portal.call(h.svc._hear_appeal, new)
        env = T._lookup(client, nonce)["verification"]
        assert env["status"] == "refunded" and env["appeal"]["outcome"] == "overturned"
        T._assert_closed(channel_id, nonce, used=0.0,
                         expect_holds={nonce: "released", f"appeal_{nonce}": "released"})
        assert len(h.court.prompts) == 2
