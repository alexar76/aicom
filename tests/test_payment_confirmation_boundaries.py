"""Complete the confirmation contract at concurrency, legacy and store boundaries."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from tests.test_payment_chain_recovery import isolated
from tests.test_payment_failure_recovery import TX, assert_one_license, checkout_http

pytestmark = pytest.mark.component_integration


def test_internal_confirmation_refuses_a_blank_transfer(checkout_http):
    env = checkout_http
    with pytest.raises(HTTPException) as exc:
        asyncio.run(env.p._confirm_payment(env.quote["payment_id"], " ", "present", {"sub": env.buyer["id"]}, None))
    assert exc.value.status_code == 400
    assert env.store.get_order_by_tx_hash(TX) is None


def test_chain_specific_hash_validation_refuses_a_solana_encoding_on_evm(checkout_http):
    env = checkout_http
    response = env.confirm(tx_hash="Z" * 64)
    assert response.status_code == 400, response.text
    assert env.store.get_order_by_tx_hash(TX) is None


def test_quote_consumed_while_waiting_for_request_lock_cannot_deliver_twice(checkout_http):
    env = checkout_http

    async def race():
        payment_id = env.quote["payment_id"]
        lock = asyncio.Lock()
        env.p._confirm_locks[payment_id] = lock
        async with lock:
            waiting = asyncio.create_task(env.p._confirm_payment(
                payment_id, TX, "present", {"sub": env.buyer["id"]}, None))
            await asyncio.sleep(0)  # The contender reaches the real locked boundary.
            assert not waiting.done()
            env.p._pending_payments.pop(payment_id)
        with pytest.raises(HTTPException) as exc:
            await waiting
        assert exc.value.status_code == 404

    asyncio.run(race())
    assert env.store.conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 0


def test_legacy_quote_without_amount_uses_server_price_and_one_license(checkout_http, monkeypatch):
    env = checkout_http
    for name in ("amount", "quote_version", "quote_seal"):
        env.quote.pop(name)
    monkeypatch.setattr(env.p, "_catalog_checkout_usdt", lambda _: 5.0)
    assert_one_license(env, env.confirm())
    assert env.store.get_order_by_tx_hash(TX)["amount"] == 5.0


def test_pinned_transfer_retries_in_a_legacy_pending_state(checkout_http):
    env = checkout_http
    env.quote["tx_hash"] = TX
    assert_one_license(env, env.confirm(tx_hash=TX.upper()))


def test_a_persisted_quote_on_an_unsupported_chain_cannot_deliver(checkout_http):
    env = checkout_http
    env.quote["chain"] = "unsupported"
    env.quote["quote_seal"] = env.p._quote_seal(env.quote)
    response = env.confirm()
    assert response.status_code == 400, response.text
    assert "does not support" in response.json()["detail"]["error"]
    assert env.store.get_order_by_tx_hash(TX) is None


def test_order_conflict_after_initial_reads_is_a_409_without_another_license(checkout_http, monkeypatch):
    env = checkout_http
    competing = env.store.create_order_and_license(
        customer_id=env.buyer["id"], customer_email=env.buyer["email"], payment_id="competing-checkout",
        product_id=env.quote["product_id"], amount=5.0, currency="USDC", tx_hash=TX)
    lookup = env.store.get_order_by_tx_hash
    reads = []

    def initial_snapshot(tx_hash):
        # Simulate insertion becoming visible after the API and claim prechecks.
        reads.append(tx_hash)
        return None if len(reads) <= 2 else lookup(tx_hash)

    monkeypatch.setattr(env.store, "get_order_by_tx_hash", initial_snapshot)
    response = env.confirm()
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["existing_payment_id"] == "competing-checkout"
    assert competing["license_key"] not in response.text
    assert env.quote["status"] == "pending_confirmation"
    assert env.store.conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 1
