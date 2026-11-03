"""An A2A task survives the death of the process running it (a2a_tasks leases, a2a.py recovery).

A crash is staged in the database exactly as a dead process leaves it: a WORKING task whose
lease lapsed, its call marked as sent, and the credit reservations its ChargeJournal named.
The recovery then runs through the real app, on the next request's sweep.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    ECHO, approval_payload, balance, funded_account, hub, list_static, mandated_invoke, setup_mandate,
)
from aimarket_hub import a2a, a2a_tasks, credits, mandates
from aimarket_hub.a2a_tasks import A2ATaskStore

PRICE = 0.004
INVOKE = json.dumps(ECHO).encode()


@pytest.fixture(autouse=True)
def sweep_every_request(monkeypatch):
    monkeypatch.setattr(a2a_tasks, "_SWEEP_EVERY_S", 0.0)


def _rpc(client, method, params, headers=None):
    return client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                       headers={"A2A-Version": "1.0", **(headers or {})}).json()


def _poke(client):
    """Any A2A request sweeps — and recovers what is abandoned."""
    _rpc(client, "ListTasks", {})


def _crashed_task(db, account: str, *, started: bool = True, rail: str = "credits", hold: str | None = "hold",
                  mandate_store=None, chain=None) -> tuple[str, str]:
    """A task a dead process left: WORKING, lease lapsed, maybe a reservation in the ledger."""
    store = A2ATaskStore(db._conn)
    row, _ = store.create(principal=a2a._principal("acct", account), context_id="ctx-crash", message_id="m-crash",
                          product_id=ECHO["product_id"], capability_id=ECHO["capability_id"], source_hub="local",
                          invoke_b64=base64.b64encode(INVOKE).decode(),
                          invoke_sha256=hashlib.sha256(INVOKE).hexdigest(), history=[])
    receipt = f"rcp_crash_{row['task_id'][-6:]}"
    if started:
        store.started(row["task_id"], rail=rail)
    if hold:
        store.note_charge(row["task_id"], receipt, "hold")
        if chain is not None:
            mandate_store.reserve(chain, receipt_id=receipt, amount_micro=int(PRICE * 1_000_000),
                                  product_id=ECHO["product_id"])
        assert not credits.CreditsLedger(db._conn).hold(account, PRICE, receipt).get("error")
        if hold == "captured":
            credits.CreditsLedger(db._conn).capture_hold(receipt)
    db._conn.execute("UPDATE a2a_tasks SET lease_until = ? WHERE task_id = ?", (time.time() - 1, row["task_id"]))
    db._conn.commit()
    return row["task_id"], receipt


def _task(db, task_id):
    return A2ATaskStore(db._conn).get(task_id)


class TestRecovery:
    def test_a_reservation_left_held_is_released_and_the_task_runs_on_a_follow_up(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            account, key = funded_account(client, db, 1.0)
            task_id, receipt = _crashed_task(db, account)
            assert balance(db, account) == pytest.approx(1.0 - PRICE), "the dead call's money is frozen"
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_AUTH_REQUIRED"
            assert row["invoke_body"], "the input is kept, so a follow-up can run the call"
            status = json.loads(row["status_json"])
            assert status["message"]["metadata"]["aimarket"]["recovered"] == {"outcome": "released", "receipts": []}
            assert "Nothing was charged" in status["message"]["parts"][0]["text"]
            assert balance(db, account) == pytest.approx(1.0), "the reservation came back"
            hold = db._conn.execute("SELECT status FROM credit_holds WHERE receipt_id = ?", (receipt,)).fetchone()
            assert hold["status"] == "released"

            follow = {"messageId": "m-follow", "role": "ROLE_USER", "taskId": task_id, "contextId": "ctx-crash",
                      "parts": [{"text": "run it"}]}
            done = _rpc(client, "SendMessage", {"message": follow}, {"X-API-Key": key})["result"]["task"]
            assert done["status"]["state"] == "TASK_STATE_COMPLETED"
            assert balance(db, account) == pytest.approx(1.0 - PRICE), "charged once, by the run that delivered"

    def test_a_captured_charge_fails_the_task_naming_the_receipt(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            account, _key = funded_account(client, db, 1.0)
            task_id, receipt = _crashed_task(db, account, hold="captured")
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_FAILED" and row["invoke_body"] == ""
            recovered = json.loads(row["metadata_json"])["aimarket"]["recovered"]
            assert recovered == {"outcome": "charged", "receipts": [receipt]}
            assert balance(db, account) == pytest.approx(1.0 - PRICE), "nothing is refunded behind the operator's back"

    def test_a_call_never_sent_waits_again_with_nothing_charged(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, _key = funded_account(client, db, 1.0)
            task_id, _ = _crashed_task(db, account, started=False, hold=None)
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_AUTH_REQUIRED"
            assert "before sending this call" in json.loads(row["status_json"])["message"]["parts"][0]["text"]

    def test_a_rail_the_hub_cannot_read_back_is_not_guessed(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, _key = funded_account(client, db, 1.0)
            task_id, _ = _crashed_task(db, account, rail="x402", hold=None)
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_FAILED"
            assert json.loads(row["metadata_json"])["aimarket"]["recovered"]["outcome"] == "unknown"

    def test_a_mandate_reservation_and_its_approval_go_back_with_the_money(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            m = setup_mandate(client, db, approval_above=3_000)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            assert client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                               json=approval_payload(m["owner"], approval)).status_code == 200
            store = mandates.MandateStore(db._conn, "https://hub.test")
            chain = store.chain(m["digest"])
            task_id, receipt = _crashed_task(db, m["account"], mandate_store=store, chain=chain)
            assert store.claim_approval(approval["approval_id"], receipt_id=receipt, need_micro=4_000)
            assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(PRICE)
            _poke(client)
            assert _task(db, task_id)["task_state"] == "TASK_STATE_AUTH_REQUIRED"
            assert store.usage(m["digest"])["spent_today_usd"] == 0, "the mandate's limit came back"
            assert store.approval(approval["approval_id"])["status"] == "approved", "the owner's yes still stands"

    def test_the_hubs_own_sweep_recovers_with_no_a2a_traffic(self, monkeypatch, tmp_path):
        """A hub nobody sends A2A requests to still frees the money: the lifespan runs the
        sweep app.state.a2a_sweep names every minute; here it is called as that loop does."""
        monkeypatch.setattr(a2a_tasks, "_SWEEP_EVERY_S", 3600.0)   # the request path would not sweep
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            account, _key = funded_account(client, db, 1.0)
            task_id, _receipt = _crashed_task(db, account)
            client.app_ref.state.a2a_sweep()
            assert _task(db, task_id)["task_state"] == "TASK_STATE_AUTH_REQUIRED"
            assert balance(db, account) == pytest.approx(1.0)

    def test_a_job_allowance_is_not_guessed_at(self, monkeypatch, tmp_path):
        """An allowance is carved by the job tree on its own schedule: the recovery cannot tell
        what it paid, so it says so instead of releasing or claiming anything."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, _key = funded_account(client, db, 1.0)
            task_id, _ = _crashed_task(db, account, hold=None)
            A2ATaskStore(db._conn).note_charge(task_id, "rcp_allowance_1", "allowance")
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_FAILED"
            assert json.loads(row["metadata_json"])["aimarket"]["recovered"]["outcome"] == "unknown"

    def test_a_hold_a_payment_verifier_still_owns_is_left_to_it(self, monkeypatch, tmp_path):
        """A Pay-on-Verified call's hold is settled by its verifier, which may still capture it:
        releasing it here would hand back money the verifier is about to take."""
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            account, _key = funded_account(client, db, 1.0)
            task_id, receipt = _crashed_task(db, account)
            db._conn.execute("INSERT INTO verified_settlements (nonce, product_id, capability_id, status) "
                             "VALUES (?, ?, ?, 'pending')", (receipt, ECHO["product_id"], ECHO["capability_id"]))
            db._conn.commit()
            _poke(client)
            row = _task(db, task_id)
            assert row["task_state"] == "TASK_STATE_FAILED"
            assert json.loads(row["metadata_json"])["aimarket"]["recovered"]["outcome"] == "unknown"
            hold = db._conn.execute("SELECT status FROM credit_holds WHERE receipt_id = ?", (receipt,)).fetchone()
            assert hold["status"] == "held"

    def test_a_live_lease_is_left_alone(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, _key = funded_account(client, db, 1.0)
            task_id, _ = _crashed_task(db, account)
            db._conn.execute("UPDATE a2a_tasks SET lease_until = ? WHERE task_id = ?", (time.time() + 60, task_id))
            db._conn.commit()
            _poke(client)
            assert _task(db, task_id)["task_state"] == "TASK_STATE_WORKING"
            assert balance(db, account) == pytest.approx(1.0 - PRICE), "a running call's reservation stays"


class TestLease:
    def _row(self, db):
        store = A2ATaskStore(db._conn)
        row, _ = store.create(principal="anon:x", context_id="c", message_id="m", product_id="p",
                              capability_id="c@v1", source_hub="local", invoke_b64="", invoke_sha256="s", history=[])
        return store, row

    def test_renew_keeps_the_lease_and_a_recovery_takes_it_once(self, tmp_path):
        from aimarket_hub.database import HubDatabase

        db = HubDatabase(tmp_path / "hub.db")
        store, row = self._row(db)
        before = store.get(row["task_id"])["lease_until"]
        time.sleep(0.01)
        assert store.renew(row["task_id"]) and store.get(row["task_id"])["lease_until"] > before
        assert store.take_stale(row) is None, "a renewed lease is not stale"
        db._conn.execute("UPDATE a2a_tasks SET lease_until = ? WHERE task_id = ?", (time.time() - 1, row["task_id"]))
        db._conn.commit()
        taken = store.take_stale(row)
        assert taken is not None and taken["lease_owner"] == a2a_tasks.RECOVERY_OWNER
        assert store.take_stale(row) is None, "two sweeps cannot both recover one task"
        assert not store.renew(row["task_id"]), "the runner lost the task"
        # A runner that was only slow cannot record over the recovery either.
        late = store.finish(store.get(row["task_id"]), state="TASK_STATE_COMPLETED", status={"state": "x"})
        assert late["task_state"] == "TASK_STATE_WORKING"
        db.close()


class TestJournal:
    def test_an_a2a_credits_call_names_its_reservation(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            _account, key = funded_account(client, db, 1.0)
            msg = {"messageId": "m-j", "role": "ROLE_USER", "parts": [{"data": {"invoke": ECHO}}]}
            task = _rpc(client, "SendMessage", {"message": msg}, {"X-API-Key": key})["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_COMPLETED"
            charges = A2ATaskStore(db._conn).charges(task["id"])
            assert [c["kind"] for c in charges] == ["hold"]
            hold = db._conn.execute("SELECT status FROM credit_holds WHERE receipt_id = ?",
                                    (charges[0]["receipt_id"],)).fetchone()
            assert hold["status"] == "captured"
            row = _task(db, task["id"])
            assert row["invoke_rail"] == "credits" and row["invoke_started"] > 0

    def test_an_outside_caller_cannot_attach_its_call_to_a_task(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=PRICE)
            _account, key = funded_account(client, db, 1.0)
            fake_task = "a2at_" + "1" * 24
            for secret in ("guess", ""):
                r = client.post("/ai-market/v2/invoke", content=INVOKE, headers={
                    "Content-Type": "application/json", "X-API-Key": key,
                    a2a.TASK_HEADER: fake_task, a2a.INTERNAL_HEADER: secret})
                assert r.status_code == 200
            assert A2ATaskStore(db._conn).charges(fake_task) == []
