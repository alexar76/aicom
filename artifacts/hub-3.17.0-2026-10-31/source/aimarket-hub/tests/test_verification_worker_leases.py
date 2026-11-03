"""Cross-process claims and stale verdicts must never move another worker's money."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub import channels, verified_settlement as vs
from aimarket_hub.database import HubDatabase
from tests import test_verified_appeals as T


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


@pytest.mark.parametrize("passes,fail_open", [(True, False), (False, True)])
def test_second_process_does_not_steal_live_verification(tmp_path, monkeypatch, passes, fail_open):
    if fail_open:
        monkeypatch.setenv("AIMARKET_VERIFY_FAIL_CLOSED", "0")
    first = T._Court([("judged", passes, 0.95 if passes else 0.1)])
    court = T._Court([("judged", False, 0.1)])
    h = T._build(tmp_path, monkeypatch, first, court)
    original = vs.httpx.AsyncClient
    entered, release = threading.Event(), threading.Event()

    class GatedClient(original):
        async def post(self, *args, **kwargs):
            entered.set()
            await asyncio.to_thread(release.wait, 5)
            return await super().post(*args, **kwargs)

    monkeypatch.setattr(vs, "httpx", SimpleNamespace(AsyncClient=GatedClient, RequestError=httpx.RequestError))
    try:
        with TestClient(h.app) as client:
            cid, secret = T._open(client)
            body = client.post("/ai-market/v2/invoke", headers={
                "X-Payment-Channel": cid, "X-Payment-Channel-Secret": secret,
            }, json={**T.CAP, "source_hub": "local", "input": {"text": "paid"},
                     "verify": {**T.VERIFY, "wait": False}}).json()
            nonce = body["receipt"]["nonce"]
            assert entered.wait(2)
            stale_row = h.svc._row(nonce)
            other = vs.VerifiedSettlementService(HubDatabase(str(tmp_path / "hub.db")), h.signer)
            try:
                client.portal.call(other.reconcile)
                wait_until(lambda: not other._inflight)
                assert other._claim_worker(nonce, "pending", "verifying") is None
                release.set()
                wait_until(lambda: T._row_state(h.db, nonce) == "provisional")
                # A delayed answer from an old worker cannot refund a provisional pass
                # or charge a provisional failure, even with the opposite fail policy.
                other._resolve_policy(stale_row, None)
                assert T._holds(nonce)[0][nonce] == "held"
                T._close_window(h, client)
                env = T._lookup(client, nonce)["verification"]
                assert env["status"] == ("settled" if passes else "refunded")
                assert channels._ledger.get(cid)["used_usd"] == pytest.approx(T.PRICE if passes else 0)
                assert len(first.prompts) == 1
            finally:
                client.portal.call(other.shutdown)
    finally:
        release.set()


@pytest.mark.parametrize("pending,working", [("pending", "verifying"), ("appealed", "appeal_verifying")])
def test_expired_worker_is_reclaimed_but_old_token_is_fenced(tmp_path, monkeypatch, pending, working):
    from tests.test_verified_settlement import _insert_verifying_row

    h = T._build(tmp_path, monkeypatch, T._Court([]), T._Court([]))
    row = _insert_verifying_row(h.db)
    nonce = row["nonce"]
    h.db._conn.execute("UPDATE verified_settlements SET status = ? WHERE nonce = ?", (pending, nonce))
    h.db._conn.commit()
    old = h.svc._claim_worker(nonce, pending, working)
    assert old and h.svc._claim_worker(nonce, pending, working) is None
    h.db._conn.execute("UPDATE verified_settlements SET lease_until = 0 WHERE nonce = ?", (nonce,))
    h.db._conn.commit()
    new = h.svc._claim_worker(nonce, pending, working)
    assert new and new["worker_token"] != old["worker_token"]
    if working == "verifying":
        h.svc._resolve_policy(old, None)
        assert h.svc._row(nonce)["status"] == working
