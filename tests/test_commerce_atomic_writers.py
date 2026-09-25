"""Multi-statement CommerceService writers run as one unit on the shared connection."""
from __future__ import annotations

import threading
import time

import pytest

from web.backend.services.commerce import CommerceService


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "synthetic-test-secret-000000000000000")
    return CommerceService(base_dir=str(tmp_path / "store"))


def test_a_monthly_run_limit_holds_under_concurrency(store, monkeypatch):
    real = store.get_monthly_run_usage

    def slow_usage(*a, **k):
        out = real(*a, **k)
        time.sleep(0.01)  # widen the window between the check and the write
        return out

    monkeypatch.setattr(store, "get_monthly_run_usage", slow_usage)
    allowed = []

    def run():
        allowed.append(store.consume_monthly_run("cust-1", limit=5)["allowed"])

    threads = [threading.Thread(target=run) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 5
    assert real("cust-1")["runs_count"] == 5


def test_a_writer_that_fails_midway_leaves_nothing_for_the_next_commit(store, monkeypatch):
    customer = store.register_customer("buyer@example.test", "correct-horse-battery")
    session = "cs_test_1"
    store.save_stripe_checkout_session(session_id=session, customer_id=customer["id"],
                                       customer_email="buyer@example.test", target_plan="maker",
                                       amount_total=900, currency="usd", status="open",
                                       payment_status="unpaid", idempotency_key=None)

    def broken(*a, **k):
        raise RuntimeError("plan store down")

    monkeypatch.setattr(store, "set_customer_plan", broken)
    with pytest.raises(RuntimeError):
        store.apply_stripe_webhook_event("evt_1", "checkout.session.completed", session,
                                         payment_status="paid", session_status="complete")
    monkeypatch.undo()
    # Another request commits right after. The failed webhook's rows must not ride along.
    store.register_customer("other@example.test", "another-long-password")
    row = store.conn.execute("SELECT 1 FROM stripe_webhook_events WHERE event_id = 'evt_1'").fetchone()
    assert row is None, "half of a failed webhook was committed by the next request"
    # The event is still unprocessed, so Stripe's retry is applied in full.
    out = store.apply_stripe_webhook_event("evt_1", "checkout.session.completed", session,
                                           payment_status="paid", session_status="complete")
    assert out == {"already_processed": False, "plan_upgraded": True}
