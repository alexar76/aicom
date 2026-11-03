"""marketplace-invoke: the A2A bridge onto the hub's own invoke path, end to end.

Every test drives the SDK's `A2AClient` against the real app (`session = TestClient`), so
what passes here is the wire contract of docs/a2a.md as a client meets it: the invoke runs
through the ASGI app — middleware, x402 invoices, mandates, credits holds, the trial ledger —
and the task records only what came back. The money assertions read the ledger itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest

pytest.importorskip("aimarket_agent")

from aimarket_agent import A2AClient, A2AError, AgentKey, Mandate, issue_mandate, owner_link_payload  # noqa: E402
from aimarket_agent.a2a import payment_required, status_metadata, task_result, task_state  # noqa: E402

from aimarket_hub.a2a_tasks import A2ATaskStore  # noqa: E402
from aimarket_hub.models import Capability  # noqa: E402
from tests._mandate_kit import HUB, balance, funded_account, hub, list_static  # noqa: E402

ECHO = ("demo-echo", "demo.echo@v1")
SELLER = "0x" + "cd" * 20
TX = "0x" + "11" * 32
COMPLETED, INPUT_REQUIRED, AUTH_REQUIRED = "TASK_STATE_COMPLETED", "TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"


@pytest.fixture
def trials(tmp_path, monkeypatch):
    """A private trial ledger, one allowance per caller. The real one is process-global, so
    without this every test that ever gave "testclient" a trial would spend this one's."""
    from aimarket_hub import sandbox_trials as st

    monkeypatch.setattr(st, "_ledger", st.SandboxTrialLedger(db_path=str(tmp_path / "trials.db")))
    monkeypatch.setenv("AIMARKET_SANDBOX_MAX_PER_VISITOR", "1")
    monkeypatch.setattr(st, "_MAX_PER_VISITOR", 1)
    monkeypatch.setattr(st, "_ENABLED", True)
    return st


@pytest.fixture
def no_trial(monkeypatch):
    from aimarket_hub import sandbox_trials as st

    monkeypatch.setattr(st, "_ENABLED", False)


def _client(client, **kw) -> A2AClient:
    a2a = A2AClient(HUB, **kw)
    a2a.session = client   # TestClient is an httpx.Client: the SDK talks to the real app
    return a2a


def _list_seller_direct(db, price: float = 0.004, **extra) -> None:
    """A listing whose seller is paid on chain (x402), with a static pack so nothing external runs."""
    db.upsert_capability(Capability(
        capability_id="demo.echo@v1", product_id="demo-echo", name="Echo", description="static pack",
        price_per_call_usd=price, source_hub="local", invoke_url="",
        prompt_template='{"answer": "echo", "ok": true}', payout_address=SELLER, **extra,
    ))


def _stub_chain(monkeypatch, *, price: float = 0.004) -> list[dict]:
    """The on-chain verifier says 'this transfer is good' — and records what it was asked.

    Like the chain, a transaction answers only for the nonce it was signed over: the first
    nonce a tx is checked against is its own, and any other is 'not bound to this call'."""
    from aimarket_hub import settle

    seen: list[dict] = []
    signed: dict[str, str] = {}

    def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None,
                require_nonce, rpc_url=""):
        seen.append({"tx_hash": tx_hash, "pay_to": terms.pay_to, "nonce": require_nonce,
                     "paid_before": paid_before})
        if require_nonce and signed.setdefault(tx_hash, require_nonce) != require_nonce:
            raise settle.PaymentError("payment is not bound to this call: the transaction "
                                      "carries no EIP-3009 authorization for this nonce")
        return {"tx_hash": tx_hash, "paid_units": settle.to_units(price, terms.decimals),
                "authorizer": "0x" + "ab" * 20}

    monkeypatch.setattr(settle, "verify_transfer", _verify)
    return seen


def _payload(tx: str | None = TX) -> dict:
    """An x402 PaymentPayload in this hub's profile: the settle txHash is what pays. (A signed
    EIP-3009 authorization may ride along and is then checked too — needs eth-account, which
    the hub's test venv lacks; test_x402_accept covers that half.)"""
    payload: dict = {"x402Version": 2, "scheme": "exact", "network": "eip155:8453"}
    if tx:
        payload["txHash"] = tx
    return payload


def _invoice_secret(db, nonce: str) -> str:
    from aimarket_hub.settle import InvoiceStore

    return InvoiceStore(db._conn).secret_for(nonce)


def _rows(db) -> list[dict]:
    return [dict(r) for r in db._conn.execute("SELECT * FROM a2a_tasks").fetchall()]


def _rpc(client, method, params, headers=None):
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                       headers={"A2A-Version": "1.0", **(headers or {})}).json()


def test_retry_without_context_charges_once_on_sdk_and_wire(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        list_static(db, price=0.004)
        account, key = funded_account(client, db, 1.0)
        a2a = _client(client, api_key=key)
        first = a2a.invoke(*ECHO, {}, message_id="sdk-retry")
        assert a2a.invoke(*ECHO, {}, message_id="sdk-retry")["id"] == first["id"]
        msg = {"messageId": "wire-retry", "role": "ROLE_USER", "parts": [{"data": {"invoke": {
            "product_id": ECHO[0], "capability_id": ECHO[1], "input": {}}}}]}
        first = _rpc(client, "SendMessage", {"message": msg}, {"X-API-Key": key})["result"]["task"]
        again = _rpc(client, "SendMessage", {"message": msg}, {"X-API-Key": key})["result"]["task"]
        assert again["id"] == first["id"]
        # mixed: the SDK sends contextId = messageId, a bare retry sends none — one task
        mixed = _rpc(client, "SendMessage", {"message": {**msg, "messageId": "sdk-retry"}},
                     {"X-API-Key": key})
        assert mixed["result"]["task"]["id"] == a2a.invoke(*ECHO, {}, message_id="sdk-retry")["id"]
        assert balance(db, account) == pytest.approx(0.992)
        assert len(_rows(db)) == 2


def test_invalid_and_rate_limited_requests_do_not_create_rows(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path, AIMARKET_INVOKE_RATE_PER_MIN="2") as (client, db):
        for i in range(10):
            msg = {"messageId": str(i), "role": "ROLE_USER", "parts": [{"data": {"invoke": {
                "product_id": ECHO[0], "capability_id": ECHO[1], "input": {},
                "verify": {"intent": "PRIVATE" * 5000}}}}]}
            r = _rpc(client, "SendMessage", {"message": msg})
            assert r["error"]["code"] == (-32602 if i < 2 else -32000)
            assert "PRIVATE" not in json.dumps(r)
        assert not _rows(db)


def test_mandate_digest_cannot_read_cancel_or_pollute_tasks(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        db.upsert_capability(Capability(
            product_id=ECHO[0], capability_id=ECHO[1], name="echo", price_per_call_usd=0.004,
            prompt_template='{"ok":true}',
            input_schema={"type": "object", "required": ["text"]},
        ))
        account, _, mandate = TestMandates()._mandate(client, db)
        a2a = _client(client, mandate=mandate)
        task = a2a.invoke(*ECHO, {})
        assert task_state(task) == INPUT_REQUIRED
        msg = a2a._follow_up_message(task, "attack", "no", {"x402.payment.status": "payment-rejected"})
        denied = _rpc(client, "SendMessage", {"message": msg}, {"X-AIMarket-Mandate": mandate.digest})
        assert denied["error"]["code"] == -32001
        msg.pop("taskId")
        msg["parts"] = [{"raw": base64.b64encode(json.dumps({
            "product_id": ECHO[0], "capability_id": ECHO[1], "input": {},
        }).encode()).decode(), "mediaType": "application/json"}]
        denied = _rpc(client, "SendMessage", {"message": msg}, {"X-AIMarket-Mandate": mandate.digest})
        assert "error" in denied
        assert a2a.list_tasks()["totalSize"] == 1
        done = a2a.resume(task, input_payload={"text": "hello"})
        assert task_state(done) == COMPLETED
        assert balance(db, account) == pytest.approx(0.996)


def test_x402_released_payment_retries_with_original_nonce(monkeypatch, tmp_path, no_trial):
    from aimarket_hub import settle

    with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
        _list_seller_direct(db)
        bound = {}

        def verify(*, tx_hash, terms, require_nonce=None, **kw):
            bound.setdefault(tx_hash, require_nonce)
            assert require_nonce == bound[tx_hash]
            return {"tx_hash": tx_hash, "paid_units": settle.to_units(0.004, terms.decimals),
                    "authorizer": "0x" + "ab" * 20}

        monkeypatch.setattr(settle, "verify_transfer", verify)
        a2a = _client(client)
        task = a2a.invoke(*ECHO, {}, verify={"requested": True, "intent": ""})
        nonce = payment_required(task)["accepts"][0]["extra"]["nonce"]
        paid = a2a.pay_x402(task, _payload())
        assert task_state(paid) == INPUT_REQUIRED
        assert status_metadata(paid)["x402.payment.status"] == "payment-retry"
        msg = a2a._follow_up_message(paid, "retry", "retry", {
            "x402.payment.status": "payment-submitted", "x402.payment.payload": _payload()})
        msg["parts"].append({"data": {"invoke": {
            "product_id": ECHO[0], "capability_id": ECHO[1], "input": {}}}})
        answer = _rpc(client, "SendMessage", {"message": msg})
        assert "result" in answer, answer
        done = answer["result"]["task"]
        assert task_state(done) == COMPLETED
        assert bound[TX] == nonce.lower()
        assert len(_rows(db)) == 1


class TestCredits:
    def test_a_credit_call_completes_with_result_receipt_and_provenance(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, key = funded_account(client, db, 1.0)
            task = _client(client, api_key=key).invoke(*ECHO, {"text": "private words"}, max_price_usd=0.01)

            assert task_state(task) == COMPLETED, task
            assert task["id"].startswith("a2at_") and task["contextId"]
            assert task_result(task) == {"answer": "echo", "ok": True}
            names = [a["name"] for a in task["artifacts"]]
            assert names[:2] == ["result", "aimarket-receipt"]
            receipt = next(a for a in task["artifacts"] if a["name"] == "aimarket-receipt")
            assert receipt["metadata"]["verifyEndpoint"] == f"{HUB}/ai-market/v2/receipts/verify"
            # Verified by the SDK against the key the hub publishes, not taken on trust.
            assert task["receipt_verified"] is True, task["receipt_verify_reason"]
            if _has_provenance():
                provenance = next(a for a in task["artifacts"] if a["name"] == "provenance")
                assert provenance["metadata"]["digest_sri"].startswith("sha256-")
            meta = task["metadata"]["aimarket"]
            assert meta["capability"]["capability_id"] == "demo.echo@v1"
            assert meta["remaining_balance"] == pytest.approx(1.0 - 0.004)
            assert balance(db, account) == pytest.approx(1.0 - 0.004)

            # What the hub keeps: no input, no key, and no invoke body once it is done.
            (row,) = _rows(db)
            assert row["invoke_body"] == ""
            stored = json.dumps(row)
            assert "private words" not in stored and key not in stored

    def test_a_retried_send_returns_its_task_and_never_pays_twice(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, key = funded_account(client, db, 1.0)
            a2a = _client(client, api_key=key)
            first = a2a.invoke(*ECHO, {"text": "hi"}, message_id="msg-retry", context_id="ctx-1")
            again = a2a.invoke(*ECHO, {"text": "hi"}, message_id="msg-retry", context_id="ctx-1")
            assert task_state(first) == task_state(again) == COMPLETED
            assert again["id"] == first["id"]
            assert balance(db, account) == pytest.approx(1.0 - 0.004)
            # The same messageId with a different request is a bug, not a retry.
            with pytest.raises(A2AError) as refused:
                a2a.invoke(*ECHO, {"text": "something else"}, message_id="msg-retry", context_id="ctx-1")
            assert refused.value.code == -32602
            assert balance(db, account) == pytest.approx(1.0 - 0.004)
            # A new message is a new purchase.
            assert a2a.invoke(*ECHO, {"text": "hi"}, context_id="ctx-1")["id"] != first["id"]
            assert balance(db, account) == pytest.approx(1.0 - 0.008)

    def test_an_unknown_key_asks_for_credentials_and_the_right_key_resumes_the_task(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, key = funded_account(client, db, 1.0)
            a2a = _client(client, api_key="amk_not_a_key_of_this_hub")
            task = a2a.invoke(*ECHO, {"text": "hi"})
            assert task_state(task) == AUTH_REQUIRED
            assert status_metadata(task)["aimarket"]["error"] == "invalid_api_key"
            (row,) = _rows(db)
            assert row["invoke_body"], "a waiting task keeps its input until it can resume"

            a2a.api_key = key
            done = a2a.resume(task)
            assert task_state(done) == COMPLETED and done["id"] == task["id"]
            assert balance(db, account) == pytest.approx(1.0 - 0.004)
            assert _rows(db)[0]["invoke_body"] == ""
            # A finished task takes no more messages.
            with pytest.raises(A2AError) as closed:
                a2a.resume(done)
            assert closed.value.code == -32004

    def test_missing_input_waits_and_the_complete_input_is_charged_once(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            db.upsert_capability(Capability(
                capability_id="demo.echo@v1", product_id="demo-echo", name="Echo", description="static",
                price_per_call_usd=0.004, source_hub="local", invoke_url="",
                prompt_template='{"answer": "echo"}',
                input_schema={"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
            ))
            account, key = funded_account(client, db, 1.0)
            a2a = _client(client, api_key=key)
            task = a2a.invoke(*ECHO, {})
            assert task_state(task) == INPUT_REQUIRED
            assert status_metadata(task)["aimarket"]["missing"] == ["text"]
            assert balance(db, account) == pytest.approx(1.0), "a short request must not be billed"
            done = a2a.resume(task, input_payload={"text": "hi"})
            assert task_state(done) == COMPLETED
            assert balance(db, account) == pytest.approx(1.0 - 0.004)


class TestX402:
    def test_an_unpaid_call_is_quoted_the_hubs_own_x402_terms(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            task = _client(client).invoke(*ECHO, {"text": "hi"})
            assert task_state(task) == INPUT_REQUIRED
            meta = status_metadata(task)
            assert meta["x402.payment.status"] == "payment-required"
            terms = payment_required(task)
            (offer,) = terms["accepts"]
            assert offer["payTo"] == SELLER and offer["amount"] == "4000"
            assert offer["network"] == "eip155:8453"
            # Minted by the app's x402 middleware — proof the invoke ran through the app, not
            # around it: without an invoice the payment below could never bind.
            nonce = offer["extra"]["nonce"]
            invoice = db._conn.execute("SELECT * FROM settle_invoices WHERE nonce = ?", (nonce,)).fetchone()
            assert invoice is not None and invoice["pay_to"] == SELLER
            assert meta["aimarket"]["payment_ways"]

    def test_paying_on_chain_completes_the_task_with_x402_receipts(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            seen = _stub_chain(monkeypatch)
            a2a = _client(client)
            task = a2a.invoke(*ECHO, {"text": "hi"})
            nonce = payment_required(task)["accepts"][0]["extra"]["nonce"]

            paid = a2a.pay_x402(task, _payload(), message_id="pay-1")
            assert task_state(paid) == COMPLETED, paid
            assert paid["id"] == task["id"]
            meta = status_metadata(paid)
            assert meta["x402.payment.status"] == "payment-completed"
            assert meta["x402.payment.receipts"] == [{"success": True, "transaction": TX, "network": "eip155:8453"}]
            assert task_result(paid) == {"answer": "echo", "ok": True}
            # The payload carried no nonce: the task's own invoice was presented with it. It
            # was paid inside its TTL, so no mined-before-expiry bound was asked for.
            assert seen == [{"tx_hash": TX, "pay_to": SELLER, "nonce": nonce, "paid_before": None}]
            assert _rows(db)[0]["invoke_body"] == ""

            # The same payment message again is a retry: nothing is verified or run twice.
            again = a2a.pay_x402(task, _payload(), message_id="pay-1")
            assert again["id"] == paid["id"] and task_state(again) == COMPLETED
            assert len(seen) == 1
            # The same transaction cannot buy a second task.
            second = a2a.invoke(*ECHO, {"text": "hi"})
            reused = a2a.pay_x402(second, _payload())
            assert task_state(reused) == INPUT_REQUIRED
            assert status_metadata(reused)["x402.payment.status"] == "payment-failed"
            # The chain says why: that transaction's authorization is for the first invoice.
            assert status_metadata(reused)["x402.payment.error"] == "INVALID_SIGNATURE"

    def test_a_task_cannot_redeem_an_invoice_another_task_was_quoted(self, monkeypatch, tmp_path, no_trial):
        """The bridge redeems with the secret of the task's OWN invoice. A second caller who
        watched the chain opens a task, names the first task's public nonce in its payment
        and presents the first buyer's transaction: no secret comes with it, so the hub
        refuses — and the first buyer's task still completes on that payment."""
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            _stub_chain(monkeypatch)
            buyer = _client(client)
            task = buyer.invoke(*ECHO, {"text": "hi"})
            nonce = payment_required(task)["accepts"][0]["extra"]["nonce"]
            watcher = _client(client, api_key=funded_account(client, db, 1.0)[1])
            theirs = watcher.invoke(*ECHO, {"text": "mine"})
            stolen = watcher.pay_x402(theirs, {**_payload(), "nonce": nonce})
            assert task_state(stolen) != COMPLETED
            paid = buyer.pay_x402(task, _payload())
            assert task_state(paid) == COMPLETED, paid
            # and the secret never reached a task record
            for row in _rows(db):
                assert all(settle_secret not in json.dumps(row, default=str)
                           for settle_secret in [_invoice_secret(db, nonce)])

    def test_a_signature_without_a_settled_transfer_is_not_a_payment(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            seen = _stub_chain(monkeypatch)
            a2a = _client(client)
            task = a2a.invoke(*ECHO, {"text": "hi"})
            unsettled = a2a.pay_x402(task, _payload(tx=None))
            assert task_state(unsettled) == INPUT_REQUIRED
            meta = status_metadata(unsettled)
            assert meta["x402.payment.status"] == "payment-failed"
            assert meta["x402.payment.error"] == "SETTLEMENT_FAILED"
            assert "never settles" in meta["aimarket"]["detail"]
            assert meta["x402.payment.required"] == payment_required(task), "the quote stays payable"
            assert seen == []
            # Settling and answering again completes the same task.
            assert task_state(a2a.pay_x402(unsettled, _payload())) == COMPLETED

    def test_declining_the_price_cancels_and_a_canceled_task_stays_canceled(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            a2a = _client(client)
            task = a2a.invoke(*ECHO, {"text": "hi"})
            canceled = a2a.reject_payment(task)
            assert task_state(canceled) == "TASK_STATE_CANCELED"
            assert _rows(db)[0]["invoke_body"] == ""
            with pytest.raises(A2AError) as closed:
                a2a.pay_x402(canceled, _payload())
            assert closed.value.code == -32004


class TestTrial:
    def test_a_stranger_gets_the_same_trial_as_on_mcp_then_the_price(self, monkeypatch, tmp_path, trials):
        from aimarket_hub.mcp_gateway import visitor_for

        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            a2a = _client(client)
            first = a2a.invoke(*ECHO, {"text": "hi"})
            assert task_state(first) == COMPLETED
            assert first["metadata"]["aimarket"]["sandbox"] == {"sandbox": True, "remaining": 0, "used": 1,
                                                                "max_trials": 1}
            # One caller, one allowance, whichever protocol it speaks: A2A spends the identity
            # the MCP gateway would present for this address.
            assert trials.sandbox_quota(visitor_for("testclient"))["used"] == 1

            second = a2a.invoke(*ECHO, {"text": "hi"})
            assert task_state(second) == INPUT_REQUIRED
            assert status_metadata(second)["aimarket"]["trial_exhausted"] is True
            assert payment_required(second)["accepts"][0]["payTo"] == SELLER

    def test_a_free_capability_never_spends_the_trial(self, monkeypatch, tmp_path, trials):
        from aimarket_hub.mcp_gateway import visitor_for

        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.0)
            a2a = _client(client)
            for _ in range(3):
                assert task_state(a2a.invoke(*ECHO, {"text": "hi"})) == COMPLETED
            assert trials.sandbox_quota(visitor_for("testclient"))["used"] == 0


class TestMandates:
    def _mandate(self, client, db, *, per_day_usd: float = 0.008):
        account, api_key = funded_account(client, db, 1.0)
        owner, agent = AgentKey.generate(), AgentKey.generate()
        r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                        json=owner_link_payload(owner, hub_origin=HUB, account_id=account))
        assert r.status_code == 200, r.text
        doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["demo.*"],
                            per_call_usd=0.01, per_day_usd=per_day_usd)
        assert client.post("/ai-market/v2/mandates", json=doc).status_code == 200
        return account, owner, Mandate(document=doc, key=agent, hub_origin=HUB)

    def test_a_mandate_pays_until_its_daily_limit_then_the_task_is_rejected(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, owner, mandate = self._mandate(client, db)
            a2a = _client(client, mandate=mandate)
            first = a2a.invoke(*ECHO, {"text": "hi"})
            second = a2a.invoke(*ECHO, {"text": "hi"})
            third = a2a.invoke(*ECHO, {"text": "hi"})
            assert task_state(first) == task_state(second) == COMPLETED
            assert first["metadata"]["aimarket"]["mandate"]["principal"] == owner.did
            assert task_state(third) == "TASK_STATE_REJECTED"
            refusal = status_metadata(third)["aimarket"]
            assert refusal["error"] == "mandate_limit" and refusal["limit"] == "perDay"
            assert balance(db, account) == pytest.approx(1.0 - 0.008)

            # The task belongs to the mandate: read back with a fresh proof over /a2a …
            assert a2a.get_task(first["id"])["id"] == first["id"]
            listed = a2a.list_tasks()
            assert listed["totalSize"] == 3 and {t["id"] for t in listed["tasks"]} == {
                first["id"], second["id"], third["id"]}
            # … and to nobody else, even holding the id.
            with pytest.raises(A2AError) as hidden:
                _client(client).get_task(first["id"])
            assert hidden.value.code == -32001

    def test_a_mandated_invoke_must_carry_the_exact_signed_bytes(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, _owner, mandate = self._mandate(client, db)
            invoke = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "source_hub": "local",
                      "input": {"text": "hi"}}
            raw = json.dumps(invoke).encode()
            message = {"messageId": "m-data", "role": "ROLE_USER",
                       "parts": [{"data": {"invoke": invoke}}]}
            a2a = _client(client, mandate=mandate)
            with pytest.raises(A2AError, match="raw"):
                a2a._rpc("SendMessage", {"message": message}, headers=mandate.headers(raw))
            # Bytes that differ from the signed ones (here: re-serialized) fail the proof.
            message = {"messageId": "m-raw", "role": "ROLE_USER", "parts": [{
                "raw": base64.b64encode(json.dumps(invoke, indent=1).encode()).decode(),
                "mediaType": "application/json"}]}
            task = a2a._rpc("SendMessage", {"message": message}, headers=mandate.headers(raw))["task"]
            assert task["status"]["state"] == AUTH_REQUIRED
            assert balance(db, account) == pytest.approx(1.0)


class TestTaskManagement:
    def test_tasks_are_listed_and_read_only_by_their_own_account(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.001)
            _a, key_a = funded_account(client, db, 1.0)
            _b, key_b = funded_account(client, db, 1.0)
            alice, bob = _client(client, api_key=key_a), _client(client, api_key=key_b)
            mine = [alice.invoke(*ECHO, {"text": "a"}, context_id="ctx-a"),
                    alice.invoke(*ECHO, {"text": "b"}, context_id="ctx-b")]
            theirs = bob.invoke(*ECHO, {"text": "c"})

            page = alice.list_tasks(page_size=1)
            assert page["totalSize"] == 2 and len(page["tasks"]) == 1 and page["nextPageToken"]
            rest = alice.list_tasks(page_size=1, page_token=page["nextPageToken"])
            assert rest["nextPageToken"] == ""
            assert {page["tasks"][0]["id"], rest["tasks"][0]["id"]} == {t["id"] for t in mine}
            assert "artifacts" not in page["tasks"][0], "ListTasks leaves artifacts out unless asked"
            assert [t["id"] for t in alice.list_tasks(context_id="ctx-b")["tasks"]] == [mine[1]["id"]]
            assert alice.list_tasks(status=COMPLETED, include_artifacts=True)["tasks"][0]["artifacts"]
            assert [t["id"] for t in bob.list_tasks()["tasks"]] == [theirs["id"]]
            assert _client(client).list_tasks()["tasks"] == []

            assert alice.get_task(mine[0]["id"], history_length=0).get("history") is None
            for stranger in (bob, _client(client)):
                with pytest.raises(A2AError) as hidden:
                    stranger.get_task(mine[0]["id"])
                assert hidden.value.code == -32001

    def test_only_a_waiting_task_can_be_canceled(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            a2a = _client(client)
            waiting = a2a.invoke(*ECHO, {"text": "hi"})
            assert task_state(a2a.cancel(waiting["id"])) == "TASK_STATE_CANCELED"
            with pytest.raises(A2AError) as twice:
                a2a.cancel(waiting["id"])
            assert twice.value.code == -32002

            list_static(db, capability_id="free.echo@v1", product_id="free-echo", price=0.0)
            done = a2a.invoke("free-echo", "free.echo@v1", {"text": "hi"})
            assert task_state(done) == COMPLETED
            with pytest.raises(A2AError) as finished:
                a2a.cancel(done["id"])
            assert finished.value.code == -32002

    def test_a_task_that_waits_too_long_fails_and_forgets_its_input(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            a2a = _client(client)
            task = a2a.invoke(*ECHO, {"text": "hi"})
            assert _rows(db)[0]["invoke_body"]
            A2ATaskStore(db._conn).sweep(now=time.time() + 3600, force=True)
            expired = a2a.get_task(task["id"])
            assert task_state(expired) == "TASK_STATE_FAILED"
            assert "expired" in expired["status"]["message"]["parts"][0]["text"]
            assert _rows(db)[0]["invoke_body"] == ""

    def test_history_keeps_the_exchange_but_not_the_input_or_payment(self, monkeypatch, tmp_path, no_trial):
        with hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1") as (client, db):
            _list_seller_direct(db)
            _stub_chain(monkeypatch)
            a2a = _client(client)
            task = a2a.invoke(*ECHO, {"text": "my secret question"})
            paid = a2a.pay_x402(task, _payload())
            roles = [m["role"] for m in paid["history"]]
            assert roles == ["ROLE_USER", "ROLE_AGENT", "ROLE_USER", "ROLE_AGENT"]
            assert paid["history"][0]["parts"][0]["data"]["invoke"]["capability_id"] == "demo.echo@v1"
            assert paid["history"][2]["metadata"] == {"x402.payment.status": "payment-submitted"}
            dump = json.dumps(_rows(db))
            assert "my secret question" not in dump
            # The payment payload the client sent is not kept; the receipt the hub issued
            # for it (in the agent's COMPLETED message) is.
            users = [m for m in paid["history"] if m["role"] == "ROLE_USER"]
            assert TX not in json.dumps(users)
            stored_history = json.loads(_rows(db)[0]["history_json"])
            assert not any("x402.payment.payload" in (m.get("metadata") or {}) for m in stored_history)
            assert status_metadata(paid)["x402.payment.receipts"][0]["transaction"] == TX


class TestTaskStore:
    def test_one_follow_up_wins_a_waiting_task(self, tmp_path):
        from aimarket_hub.database import HubDatabase

        store = A2ATaskStore(HubDatabase(tmp_path / "hub.db")._conn)
        row, created = store.create(principal="anon:x", context_id="c", message_id="m0", product_id="p",
                                    capability_id="c@v1", source_hub="local", invoke_b64="e30=",
                                    invoke_sha256=hashlib.sha256(b"{}").hexdigest(), history=[])
        assert created
        again, created_again = store.create(principal="anon:x", context_id="c", message_id="m0", product_id="p",
                                            capability_id="c@v1", source_hub="local", invoke_b64="e30=",
                                            invoke_sha256="x", history=[])
        assert not created_again and again["task_id"] == row["task_id"]
        waiting = store.finish(row, state=INPUT_REQUIRED, status={"state": INPUT_REQUIRED})
        assert waiting["invoke_body"] == "e30="

        claimed = store.claim(row["task_id"], message_id="m1")
        assert claimed is not None and claimed["task_state"] == "TASK_STATE_WORKING"
        assert store.claim(row["task_id"], message_id="m2") is None, "a running task cannot be claimed"
        assert store.cancel(claimed, status={"state": "TASK_STATE_CANCELED"}) is None
        back = store.finish(claimed, state=INPUT_REQUIRED, status={"state": INPUT_REQUIRED})
        assert store.claim(row["task_id"], message_id="m1") is None, "the same follow-up is not run twice"
        # A stale copy of the row cannot overwrite a newer state.
        store.finish(claimed, state=COMPLETED, status={"state": COMPLETED})
        assert store.get(row["task_id"])["task_state"] == INPUT_REQUIRED
        done = store.finish(store.claim(row["task_id"], message_id="m3"), state=COMPLETED,
                            status={"state": COMPLETED})
        assert done["task_state"] == COMPLETED and done["invoke_body"] == "" and back["revision"] < done["revision"]


class TestWire:
    @pytest.mark.parametrize("part, why", [
        ({"raw": base64.b64encode(b'{"product_id":"demo-echo"}').decode(), "mediaType": "text/plain"}, "mediaType"),
        ({"data": {"invoke": {"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                              "payment_authorization": {}}}}, "payment_authorization"),
        ({"data": {"invoke": {"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                              "max_price_usd": -1}}}, "max_price_usd"),
    ])
    def test_malformed_invokes_are_refused_before_any_task(self, monkeypatch, tmp_path, part, why):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            answer = _rpc(client, "SendMessage", {"message": {"messageId": "m", "role": "ROLE_USER", "parts": [part]}})
            assert answer["error"]["code"] == -32602 and why in answer["error"]["message"]
            assert _rows(db) == []

    def test_job_headers_are_refused_rather_than_dropped(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            message = {"messageId": "m", "role": "ROLE_USER", "parts": [{"data": {"invoke": {
                "product_id": "demo-echo", "capability_id": "demo.echo@v1"}}}]}
            answer = _rpc(client, "SendMessage", {"message": message}, {"X-AIMarket-Job": "token"})
            assert answer["error"]["code"] == -32602

    def test_task_outcomes_are_counted_by_state(self, monkeypatch, tmp_path):
        from aimarket_hub.metrics import REGISTRY

        def value() -> float:
            return REGISTRY.get_sample_value(
                "aimarket_hub_a2a_requests_total", {"method": "SendMessage", "result": "completed"}) or 0.0

        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.0)
            before = value()
            _client(client).invoke(*ECHO, {"text": "hi"})
            assert value() == before + 1


def _has_provenance() -> bool:
    try:
        import aimarket_provenance  # noqa: F401
    except ImportError:
        return False
    return True


def test_an_a2a_mandate_proof_is_checked_on_the_path_relative_to_the_base_url():
    """A hub mounted under a prefix (independentai.network/hub) sees "/hub/a2a"; the
    client signed "/a2a" (mandates.md §5.1). Checked on the raw path, every mandated
    A2A call there would be refused."""
    from aimarket_hub.a2a import _signed_path

    class _Req:
        class url:  # noqa: N801 - stand-in for starlette's URL
            path = "/hub/a2a"

        scope = {"root_path": "/hub"}

    assert _signed_path(_Req()) == "/a2a"
    _Req.scope, _Req.url.path = {}, "/a2a"
    assert _signed_path(_Req()) == "/a2a"


def test_a_refusal_keeps_only_error_and_detail():
    """A task persists the refusal it shows. Whatever else the answer carried — FastAPI's
    echo of the offending input, a provider's raw body — is not kept."""
    from aimarket_hub import a2a

    invoke = a2a._Invoke(raw=b"{}", product_id=ECHO[0], capability_id=ECHO[1], source_hub="local")
    body = {
        "detail": [{"type": "int_type", "loc": ["body", "input", "n"], "msg": "Input should be a valid integer",
                    "input": "PRIVATE-INPUT", "ctx": {"given": "PRIVATE-INPUT"}}],
        "raw": "PRIVATE-PROVIDER-BODY",
    }
    for status in (422, 409, 502):
        out = a2a._outcome(status_code=status, headers={}, body=body, task_id="t", context_id="c",
                           invoke=invoke, hub_url=HUB, payment=None, trial_exhausted=False)
        data = out.message["parts"][1]["data"]
        assert set(data) == {"success", "error", "detail"}
        assert "Input should be a valid integer" in data["detail"]
        assert "PRIVATE" not in json.dumps(out.message)


def test_an_anonymous_retry_gets_the_task_but_not_its_result(monkeypatch, tmp_path):
    """An anonymous principal is an address, and an address is shared: whoever resends the
    same messageId and bytes from it must not be handed the first caller's result."""
    with hub(monkeypatch, tmp_path) as (client, db):
        list_static(db, price=0.0)
        msg = {"messageId": "anon-retry", "role": "ROLE_USER", "parts": [{"data": {"invoke": {
            "product_id": ECHO[0], "capability_id": ECHO[1], "input": {"q": "mine"}}}}]}
        first = _rpc(client, "SendMessage", {"message": msg})["result"]["task"]
        assert first.get("artifacts"), "the original caller gets the result"
        again = _rpc(client, "SendMessage", {"message": msg})["result"]["task"]
        assert again["id"] == first["id"]
        assert not again.get("artifacts")
        assert len(_rows(db)) == 1      # still one task, nothing run twice


def test_a_keyed_retry_still_gets_its_result(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        list_static(db, price=0.004)
        _, key = funded_account(client, db, 1.0)
        msg = {"messageId": "keyed-retry", "role": "ROLE_USER", "parts": [{"data": {"invoke": {
            "product_id": ECHO[0], "capability_id": ECHO[1], "input": {}}}}]}
        _rpc(client, "SendMessage", {"message": msg}, {"X-API-Key": key})
        again = _rpc(client, "SendMessage", {"message": msg}, {"X-API-Key": key})["result"]["task"]
        assert again.get("artifacts")
