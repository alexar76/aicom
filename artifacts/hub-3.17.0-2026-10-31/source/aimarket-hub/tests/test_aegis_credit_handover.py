"""The old AEGIS grant wire and paid-deposit wire must share one transfer claim."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import channels, credits, deposit_verify
from aimarket_hub.api import OPERATOR_CREDIT_STACK
from tests._mandate_kit import ADMIN_TOKEN, balance, funded_account, hub

TX = "0x" + "37" * 32
REFERENCE = "usdc:base:" + TX


def credit(client, account, *, old_wire=False, chain="base", amount=5):
    body = {"amount_usd": amount, "reference": REFERENCE} if old_wire else {
        "amount_usd": amount, "chain": chain, "tx_hash": TX,
    }
    return client.post(f"/ai-market/v2/accounts/{account}/credit", json=body,
                       headers={"Authorization": "Bearer " + ADMIN_TOKEN})


@pytest.fixture(autouse=True)
def offline_chain(monkeypatch):
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.delenv("AIMARKET_DEPOSIT_RPC_URL", raising=False)
    monkeypatch.setattr(deposit_verify, "registry_chain_id", lambda label: 8453)


def test_old_aegis_wire_is_paid_credit_and_blocks_other_doors(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        first = credit(client, account, old_wire=True)
        assert first.status_code == 200, first.text
        assert balance(db, account) == 5
        state = credits.CreditsLedger(db._conn).account(account)
        assert state["topped_up_usd"] == 5 and state["granted_usd"] == 0
        other = channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="channel", amount_cents=500)
        assert other["ok"] is False and other["error"] == "already_claimed"


def test_a_transfer_another_door_consumed_cannot_credit_aegis(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        assert channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="channel", amount_cents=500)["ok"]
        assert credit(client, account, old_wire=True).status_code == 409
        assert balance(db, account) == 0


def test_committed_legacy_grant_is_reconciled_without_crediting_again(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        credits.CreditsLedger(db._conn).grant(account, 5, reference=REFERENCE)
        for old in (True, False):
            response = credit(client, account, old_wire=old)
            assert response.status_code == 200 and response.json()["idempotent_replay"]
        assert balance(db, account) == 5
        assert not channels._claim_deposit_shared(chain="base", tx_hash=TX, channel_id="other", amount_cents=500)["ok"]


def test_racing_old_new_and_alias_requests_credit_once(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        barrier = threading.Barrier(8)

        def attempt(index):
            barrier.wait(timeout=5)
            return credit(client, account, old_wire=index % 2 == 0, chain="base-alias" if index % 3 == 0 else "base")

        with ThreadPoolExecutor(max_workers=8) as workers:
            responses = list(workers.map(attempt, range(8)))
        assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
        assert balance(db, account) == 5
        assert sum(not response.json()["idempotent_replay"] for response in responses) == 1


def test_an_interrupted_old_claim_without_a_credit_fails_closed(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        assert channels.claim_deposit_as(OPERATOR_CREDIT_STACK, chain="base", tx_hash=TX,
                                         claim_id=account, amount_cents=500)["ok"]
        assert credit(client, account).status_code == 409
        assert balance(db, account) == 0


def test_legacy_credit_to_another_account_or_amount_never_rebinds(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        other, _ = funded_account(client, db, 0)
        credits.CreditsLedger(db._conn).grant(account, 5, reference=REFERENCE)
        assert credit(client, other, old_wire=True).status_code == 409
        assert credit(client, account, amount=6).status_code == 409
        assert balance(db, account) == 5 and balance(db, other) == 0


def test_unequal_amount_race_never_releases_a_concurrent_successful_credit(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0)
        first_claimed = threading.Event()
        second_finished = threading.Event()
        original_claim = channels.claim_deposit_as

        def pause_first_claim(stack, **kwargs):
            result = original_claim(stack, **kwargs)
            if kwargs["amount_cents"] == 500:
                first_claimed.set()
                assert second_finished.wait(timeout=10)
            return result

        monkeypatch.setattr(channels, "claim_deposit_as", pause_first_claim)
        # Separate ASGI portals model distinct server workers: pausing a sync
        # registry call in one worker must not stop the second worker's loop.
        other_worker = TestClient(client.app)
        with ThreadPoolExecutor(max_workers=1) as workers:
            first = workers.submit(credit, other_worker, account, amount=5)
            try:
                assert first_claimed.wait(timeout=10)
                second = credit(client, account, amount=6)
                assert second.status_code == 200, second.text
            finally:
                second_finished.set()
            assert first.result(timeout=10).status_code == 400
        other_worker.close()
        assert balance(db, account) == 6
        other_door = channels._claim_deposit_shared(
            chain="base", tx_hash=TX, channel_id="other-door", amount_cents=600)
        assert not other_door["ok"] and other_door["error"] == "already_claimed"
