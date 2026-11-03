"""A2A push notifications, returnImmediately, and the owner-approval wait (docs/a2a.md).

The webhook is a URL the caller chose, so the first half pins what the hub refuses to call.
The second half drives the real app: a task answered WORKING finishes on its own and its
webhook hears it; a mandated call over the approval threshold waits for its owner, moves when
the owner answers — on another request, with no word from the client — and runs once.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    approval_payload, balance, funded_account, hub, list_static, request_proof, setup_mandate,
)
from aimarket_hub import a2a_push
from aimarket_hub.a2a_push import PushConfigError, PushDispatcher, PushStore, parse_config

# A literal public address: valid without DNS, and never actually called (deliveries are faked).
HOOK = "https://93.184.216.34/a2a-hook"
ECHO = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "source_hub": "local", "input": {"text": "hi"}}


# ── what a webhook may be ─────────────────────────────────────────────────

class TestConfig:
    def test_a_good_config_is_read_with_its_secrets(self):
        cfg = parse_config({"url": HOOK, "token": "tok-1",
                            "authentication": {"scheme": "Bearer", "credentials": "c-1"}, "id": "mine"})
        assert cfg == {"url": HOOK, "token": "tok-1", "auth_scheme": "Bearer", "auth_credentials": "c-1",
                       "config_id": "mine"}

    @pytest.mark.parametrize("url, why", [
        ("http://93.184.216.34/hook", "https"),
        ("https://127.0.0.1/hook", "private"),
        ("https://10.1.2.3/hook", "private"),
        ("https://169.254.169.254/latest/meta-data", "private"),
        ("https://[::1]/hook", "private"),
        ("https://user:pw@93.184.216.34/hook", "credentials"),
        ("https://93.184.216.34/a b", "whitespace"),
        ("ftp://93.184.216.34/hook", "https"),
        ("https://" + "a" * 3000, "at most"),
        ("", "https"),
    ])
    def test_a_webhook_the_hub_will_not_call_is_refused(self, url, why):
        with pytest.raises(PushConfigError, match=why):
            parse_config({"url": url})

    @pytest.mark.parametrize("auth, why", [
        ({"scheme": "Bearer", "credentials": "x\r\nX-Evil: 1"}, "one line"),
        ({"scheme": "Bear er", "credentials": "x"}, "scheme"),
        ({"scheme": "", "credentials": "x"}, "scheme"),
        ("Bearer x", "object"),
    ])
    def test_credentials_cannot_inject_a_header(self, auth, why):
        with pytest.raises(PushConfigError, match=why):
            parse_config({"url": HOOK, "authentication": auth})

    def test_token_and_id_are_bounded(self):
        with pytest.raises(PushConfigError, match="token"):
            parse_config({"url": HOOK, "token": "t\n"})
        with pytest.raises(PushConfigError, match="id"):
            parse_config({"url": HOOK, "id": "../../x"})

    def test_credentials_are_never_rendered_back(self):
        row = {"task_id": "a2at_x", "config_id": "c", "url": HOOK, "token": "t", "auth_scheme": "Bearer",
               "auth_credentials": "secret"}
        assert a2a_push.render(row) == {"id": "c", "taskId": "a2at_x", "url": HOOK, "token": "t",
                                        "authentication": {"scheme": "Bearer"}}


# ── delivery ──────────────────────────────────────────────────────────────

class _Hook:
    """A fake webhook: records every POST and answers from a script of statuses."""

    def __init__(self, statuses=(200,)):
        self.calls: list[tuple[str, dict, dict]] = []
        self._statuses = list(statuses)

    async def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        if status == -1:
            raise ConnectionError("refused")
        return status, b""

    def states(self, task_id=None):
        return [c[1]["statusUpdate"]["status"]["state"] for c in self.calls
                if task_id is None or c[1]["statusUpdate"]["taskId"] == task_id]


class TestDelivery:
    def _store(self, tmp_path):
        from aimarket_hub.database import HubDatabase

        db = HubDatabase(tmp_path / "hub.db")
        return db, PushStore(db._conn)

    def test_a_status_update_with_the_clients_headers(self, tmp_path):
        db, store = self._store(tmp_path)
        store.create("a2at_1", parse_config({"url": HOOK, "token": "tok",
                                             "authentication": {"scheme": "Bearer", "credentials": "cred"}}))
        hook = _Hook()
        dispatcher = PushDispatcher(store, post=hook, retry_delays=())
        task = {"id": "a2at_1", "contextId": "ctx", "status": {"state": "TASK_STATE_COMPLETED"},
                "artifacts": [{"artifactId": "result"}], "metadata": {"aimarket": {"price_usd": 0.1}}}

        async def go():
            assert dispatcher.notify(task) == 1
            await dispatcher.drain()

        asyncio.run(go())
        (url, body, headers), = hook.calls
        assert url == HOOK
        assert body == {"statusUpdate": {"taskId": "a2at_1", "contextId": "ctx",
                                         "status": {"state": "TASK_STATE_COMPLETED"},
                                         "metadata": {"aimarket": {"price_usd": 0.1}}}}
        assert "artifacts" not in json.dumps(body), "a paid result is read with GetTask, not pushed"
        assert headers["Authorization"] == "Bearer cred"
        assert headers["X-A2A-Notification-Token"] == "tok"
        assert headers["Content-Type"] == "application/a2a+json"
        assert store.get("a2at_1", store.list("a2at_1")[0]["config_id"])["last_status"] == 200
        db.close()

    def test_retries_what_may_pass_and_stops_on_a_refusal(self, tmp_path):
        db, store = self._store(tmp_path)
        store.create("a2at_1", parse_config({"url": HOOK, "id": "flaky"}))
        store.create("a2at_2", parse_config({"url": HOOK, "id": "gone"}))
        flaky, gone = _Hook([503, -1, 200]), _Hook([404])

        async def post(url, body, headers):
            target = flaky if body["statusUpdate"]["taskId"] == "a2at_1" else gone
            return await target(url, body, headers)

        dispatcher = PushDispatcher(store, post=post, retry_delays=(0.0, 0.0, 0.0))

        async def go():
            for tid in ("a2at_1", "a2at_2"):
                dispatcher.notify({"id": tid, "contextId": "c", "status": {"state": "TASK_STATE_FAILED"}})
            await dispatcher.drain()

        asyncio.run(go())
        assert len(flaky.calls) == 3 and store.get("a2at_1", "flaky")["last_status"] == 200
        assert len(gone.calls) == 1 and store.get("a2at_2", "gone")["last_error"] == "HTTP 404"
        db.close()

    def test_a_hanging_webhook_holds_a_slot_for_one_attempt_not_its_retries(self, tmp_path, monkeypatch):
        """Slow, failing webhooks once kept every delivery slot through their whole retry
        cycle (2 s and 10 s pauses included), so any other task's push waited ~42 s."""
        monkeypatch.setattr(a2a_push, "MAX_CONCURRENT_DELIVERIES", 4)
        db, store = self._store(tmp_path)
        for c in range(4):
            store.create("a2at_slow", parse_config({"url": HOOK + "/tarpit", "id": f"c{c}"}))
        store.create("a2at_other", parse_config({"url": HOOK}))
        delivered: dict[str, float] = {}

        async def post(url, body, headers):
            if url.endswith("/tarpit"):
                await asyncio.sleep(0.3)        # stands for the 10 s timeout
                return 503, b""                 # retried
            delivered[body["statusUpdate"]["taskId"]] = time.monotonic()
            return 200, b""

        dispatcher = PushDispatcher(store, post=post, retry_delays=(0.3, 0.3))

        async def go():
            start = time.monotonic()
            dispatcher.notify({"id": "a2at_slow", "contextId": "c", "status": {"state": "TASK_STATE_WORKING"}})
            dispatcher.notify({"id": "a2at_other", "contextId": "c", "status": {"state": "TASK_STATE_COMPLETED"}})
            await dispatcher.drain()
            return delivered["a2at_other"] - start

        # One attempt is 0.3 s; holding the slot through the retries would make it 1.5 s.
        assert asyncio.run(go()) < 0.9
        db.close()

    def test_a_full_queue_drops_and_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setattr(a2a_push, "MAX_PENDING_DELIVERIES", 2)
        db, store = self._store(tmp_path)
        for c in range(4):
            store.create("a2at_1", parse_config({"url": HOOK, "id": f"c{c}"}))
        hook = _Hook()
        dispatcher = PushDispatcher(store, post=hook, retry_delays=())

        async def go():
            assert dispatcher.notify({"id": "a2at_1", "contextId": "c", "status": {"state": "TASK_STATE_WORKING"}}) == 2
            await dispatcher.drain()

        asyncio.run(go())
        assert len(hook.calls) == 2
        errors = sorted(c["last_error"] for c in store.list("a2at_1"))
        assert errors == ["", ""] + ["dropped: too many deliveries pending on this hub"] * 2
        db.close()

    def test_a_task_takes_a_bounded_number_of_webhooks(self, tmp_path):
        db, store = self._store(tmp_path)
        for i in range(a2a_push.MAX_CONFIGS_PER_TASK):
            store.create("a2at_1", parse_config({"url": HOOK, "id": f"c{i}"}))
        store.create("a2at_1", parse_config({"url": HOOK + "/rotated", "id": "c0"}))   # replace is fine
        assert store.get("a2at_1", "c0")["url"] == HOOK + "/rotated"
        with pytest.raises(PushConfigError, match="at most"):
            store.create("a2at_1", parse_config({"url": HOOK, "id": "one-more"}))
        db.close()


# ── end to end ────────────────────────────────────────────────────────────

@pytest.fixture
def hook(monkeypatch):
    """Every hub built after this delivers to a fake webhook, with no retry delay."""
    fake = _Hook()
    monkeypatch.setattr(a2a_push, "_safe_post", fake)
    monkeypatch.setattr(a2a_push, "RETRY_DELAYS_S", ())
    return fake


def _rpc(client, method, params, headers=None, raw: bytes | None = None):
    payload = raw or json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    return client.post("/a2a", content=payload, headers={"A2A-Version": "1.0", "Content-Type": "application/json",
                                                         **(headers or {})}).json()


def _invoke_message(message_id: str, invoke: dict | None = None, *, task_id: str | None = None) -> dict:
    msg = {"messageId": message_id, "role": "ROLE_USER",
           "parts": [{"data": {"invoke": invoke or {k: v for k, v in ECHO.items()}}}]}
    if task_id:
        msg["taskId"] = task_id
    return msg


def _wait_for(client, task_id, headers, state, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = _rpc(client, "GetTask", {"id": task_id}, headers)["result"]
        if task["status"]["state"] == state:
            return task
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} never reached {state}: {task['status']['state']}")


def _wait_calls(hook, n, timeout=5.0):
    deadline = time.time() + timeout
    while len(hook.calls) < n and time.time() < deadline:
        time.sleep(0.02)
    return hook.calls


class TestReturnImmediately:
    def test_answered_working_then_finished_and_pushed(self, monkeypatch, tmp_path, hook):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, key = funded_account(client, db, 1.0)
            headers = {"X-API-Key": key}
            answer = _rpc(client, "SendMessage", {
                "message": _invoke_message("m-async"),
                "configuration": {"returnImmediately": True,
                                  "taskPushNotificationConfig": {"url": HOOK, "token": "t-1"}},
            }, headers)
            task = answer["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_WORKING"
            done = _wait_for(client, task["id"], headers, "TASK_STATE_COMPLETED")
            assert any(a["artifactId"] == "result" for a in done["artifacts"])
            _wait_calls(hook, 1)
            assert hook.states(task["id"]) == ["TASK_STATE_COMPLETED"]
            assert hook.calls[0][2]["X-A2A-Notification-Token"] == "t-1"
            assert balance(db, account) == pytest.approx(1.0 - 0.004)

            # The config is the task's: listed, read, deleted under the task's own principal.
            configs = _rpc(client, "ListTaskPushNotificationConfigs", {"taskId": task["id"]}, headers)["result"]
            assert [c["url"] for c in configs["configs"]] == [HOOK]
            _other, other_key = funded_account(client, db, 1.0)
            hidden = _rpc(client, "ListTaskPushNotificationConfigs", {"taskId": task["id"]}, {"X-API-Key": other_key})
            assert hidden["error"]["code"] == -32001
            cid = configs["configs"][0]["id"]
            assert _rpc(client, "GetTaskPushNotificationConfig", {"taskId": task["id"], "id": cid},
                        headers)["result"]["id"] == cid
            assert _rpc(client, "DeleteTaskPushNotificationConfig", {"taskId": task["id"], "id": cid},
                        headers)["result"] == {}
            assert _rpc(client, "ListTaskPushNotificationConfigs", {"taskId": task["id"]},
                        headers)["result"]["configs"] == []
            # A finished task takes no new webhook: nothing would ever call it.
            late = _rpc(client, "CreateTaskPushNotificationConfig", {"taskId": task["id"], "url": HOOK}, headers)
            assert late["error"]["code"] == -32004

    def test_a_retried_async_send_does_not_run_twice(self, monkeypatch, tmp_path, hook):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            account, key = funded_account(client, db, 1.0)
            params = {"message": _invoke_message("m-twice"), "configuration": {"returnImmediately": True}}
            first = _rpc(client, "SendMessage", params, {"X-API-Key": key})["result"]["task"]
            again = _rpc(client, "SendMessage", params, {"X-API-Key": key})["result"]["task"]
            assert again["id"] == first["id"]
            _wait_for(client, first["id"], {"X-API-Key": key}, "TASK_STATE_COMPLETED")
            assert balance(db, account) == pytest.approx(1.0 - 0.004)

    def test_returnImmediately_must_be_a_boolean(self, monkeypatch, tmp_path, hook):
        with hub(monkeypatch, tmp_path) as (client, db):
            body = _rpc(client, "SendMessage", {"message": _invoke_message("m-bad"),
                                                "configuration": {"returnImmediately": "yes"}})
            assert body["error"]["code"] == -32602


class TestPushOnInterrupted:
    def test_a_webhook_registered_on_a_waiting_task_hears_its_expiry(self, monkeypatch, tmp_path, hook):
        from aimarket_hub import a2a_tasks
        from aimarket_hub import sandbox_trials as st

        monkeypatch.setattr(st, "_ENABLED", False)
        monkeypatch.setattr(a2a_tasks, "_SWEEP_EVERY_S", 0.0)   # every request sweeps
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            # An unknown key: the task waits for credentials.
            task = _rpc(client, "SendMessage", {"message": _invoke_message("m-wait")},
                        {"X-API-Key": "aimk_unknown"})["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_AUTH_REQUIRED"
            created = _rpc(client, "CreateTaskPushNotificationConfig",
                           {"taskId": task["id"], "url": HOOK,
                            "authentication": {"scheme": "Bearer", "credentials": "never-echoed"}})
            assert created["result"]["authentication"] == {"scheme": "Bearer"}
            assert "never-echoed" not in json.dumps(created)
            db._conn.execute("UPDATE a2a_tasks SET expires_at = ? WHERE task_id = ?", (time.time() - 1, task["id"]))
            db._conn.commit()
            # The next request of ANY caller sweeps; the expiry is pushed without this client asking.
            _rpc(client, "SendMessage", {"message": _invoke_message("m-other")}, {"X-API-Key": "aimk_other"})
            _wait_calls(hook, 1)
            assert hook.states(task["id"]) == ["TASK_STATE_FAILED"]
            assert hook.calls[0][2]["Authorization"] == "Bearer never-echoed"


# ── the owner-approval wait over A2A (mandates.md §5.6) ───────────────────

def _mandated_send(client, m, invoke_bytes: bytes, message_id: str, *, task_id: str | None = None,
                   configuration: dict | None = None):
    msg = {"messageId": message_id, "role": "ROLE_USER",
           "parts": [{"raw": base64.b64encode(invoke_bytes).decode(), "mediaType": "application/json"}]}
    if task_id:
        msg["taskId"] = task_id
    params: dict = {"message": msg}
    if configuration:
        params["configuration"] = configuration
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": params}).encode()
    headers = {
        "X-AIMarket-Mandate": m["digest"],
        "X-AIMarket-Mandate-Proof": request_proof(m["agent"], m["digest"], invoke_bytes),
        "X-AIMarket-A2A-Proof": request_proof(m["agent"], m["digest"], raw, path="/a2a"),
    }
    return _rpc(client, "SendMessage", None, headers, raw=raw)


class TestApprovalOverA2A:
    def test_the_task_waits_for_the_owner_moves_when_answered_and_runs_once(self, monkeypatch, tmp_path, hook):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, approval_above=3_000)
            invoke = json.dumps(ECHO).encode()
            task = _mandated_send(client, m, invoke, "m-big",
                                  configuration={"taskPushNotificationConfig": {"url": HOOK}})["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_AUTH_REQUIRED"
            approval = task["status"]["message"]["metadata"]["aimarket"]["approval"]
            assert approval["status"] == "pending"
            row = db._conn.execute("SELECT awaiting, expires_at FROM a2a_tasks WHERE task_id = ?",
                                   (task["id"],)).fetchone()
            assert row["awaiting"] == approval["approval_id"]
            assert row["expires_at"] > time.time() + 3600, "an owner gets the approval's day, not 15 minutes"
            assert balance(db, m["account"]) == pytest.approx(1.0)
            _wait_calls(hook, 1)   # the webhook hears every change, the first wait included
            assert hook.states(task["id"]) == ["TASK_STATE_AUTH_REQUIRED"]

            # The owner answers on its own request; the client says nothing.
            r = client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                            json=approval_payload(m["owner"], approval))
            assert r.status_code == 200, r.text
            _wait_calls(hook, 2)
            assert hook.states(task["id"]) == ["TASK_STATE_AUTH_REQUIRED"] * 2
            pushed = hook.calls[1][1]["statusUpdate"]
            assert pushed["metadata"]["aimarket"]["approval"]["status"] == "approved"
            assert "approved" in pushed["status"]["message"]["parts"][0]["text"]

            # The run still needs the agent's own fresh proof — and happens once.
            done = _mandated_send(client, m, invoke, "m-big-go", task_id=task["id"])["result"]["task"]
            assert done["status"]["state"] == "TASK_STATE_COMPLETED", done["status"]
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.004)
            _wait_calls(hook, 3)
            assert hook.states(task["id"]) == ["TASK_STATE_AUTH_REQUIRED"] * 2 + ["TASK_STATE_COMPLETED"]
            again = _mandated_send(client, m, invoke, "m-big-go", task_id=task["id"])["result"]["task"]
            assert again["status"]["state"] == "TASK_STATE_COMPLETED"
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.004)

    def test_a_denial_ends_the_task_and_tells_its_webhook(self, monkeypatch, tmp_path, hook):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, approval_above=3_000)
            invoke = json.dumps(ECHO).encode()
            task = _mandated_send(client, m, invoke, "m-no",
                                  configuration={"taskPushNotificationConfig": {"url": HOOK}})["result"]["task"]
            approval_id = db._conn.execute("SELECT awaiting FROM a2a_tasks WHERE task_id = ?",
                                           (task["id"],)).fetchone()["awaiting"]
            r = client.post(f"/ai-market/v2/mandates/approvals/{approval_id}",
                            headers={"X-API-Key": m["api_key"]}, json={"decision": "deny"})
            assert r.status_code == 200
            _wait_calls(hook, 2)
            assert hook.states(task["id"]) == ["TASK_STATE_AUTH_REQUIRED", "TASK_STATE_REJECTED"]
            row = db._conn.execute("SELECT task_state, invoke_body, awaiting FROM a2a_tasks WHERE task_id = ?",
                                   (task["id"],)).fetchone()
            assert row["task_state"] == "TASK_STATE_REJECTED" and row["invoke_body"] == "" and row["awaiting"] == ""
            assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_a_peers_approval_required_is_not_a_wait(self, monkeypatch, tmp_path, hook):
        """A routed call's 402 comes from the peer. Its "approval" names no request of this hub,
        so the task must not wait on it — nor keep the buyer's input as long as the peer says."""
        import aimarket_hub.outbound_http as ohttp
        from tests.test_federated_invoke import (
            MCP_ENDPOINT, ORACLE_PEER, _add_federated_capability, _add_peer, _Outbound, _Resp,
        )

        with hub(monkeypatch, tmp_path) as (client, db):
            _add_peer(db, ORACLE_PEER, categories=["oracle"])
            _add_federated_capability(db, ORACLE_PEER, price=0.01)
            fake = {"success": False, "error": "approval_required", "detail": "owner must approve",
                    "approval": {"approval_id": "apr_" + "a" * 24, "amount_usd": 1, "max_usd": 1,
                                 "expires_at": "9999-12-31T23:59:59Z"}}
            outbound = _Outbound(_Resp(402, fake), well_known={"mcp_endpoint": MCP_ENDPOINT})
            monkeypatch.setattr(ohttp, "safe_get", outbound.safe_get)
            monkeypatch.setattr(ohttp, "safe_post", outbound.safe_post)
            _account, key = funded_account(client, db, 1.0)
            invoke = {"product_id": "prod-x", "capability_id": "cap.x@v1", "source_hub": ORACLE_PEER,
                      "input": {"q": "the buyer's input"}}
            task = _rpc(client, "SendMessage", {"message": _invoke_message("m-peer", invoke)},
                        {"X-API-Key": key})["result"]["task"]
            assert len(outbound.posts) == 1
            row = db._conn.execute("SELECT awaiting, expires_at FROM a2a_tasks WHERE task_id = ?",
                                   (task["id"],)).fetchone()
            assert row["awaiting"] == ""
            assert row["expires_at"] < time.time() + 86_400
            assert "approval" not in (task["status"]["message"].get("metadata") or {}).get("aimarket", {})

    def test_an_answer_given_while_the_call_runs_reaches_the_task(self, monkeypatch, tmp_path, hook):
        """The owner can answer between the invoke saying approval_required and the run
        recording the wait. The listener then finds no waiting task, so the run must look."""
        from aimarket_hub import a2a_tasks, mandates

        stores = []
        real_init = mandates.MandateStore.__init__

        def init(self, *a, **kw):
            real_init(self, *a, **kw)
            stores.append(self)

        monkeypatch.setattr(mandates.MandateStore, "__init__", init)
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, approval_above=3_000)
            app_store = next(s for s in stores if s.decision_listeners)
            real_finish = a2a_tasks.A2ATaskStore.finish
            answered = []

            def finish(self, row, **kw):
                if kw.get("awaiting") and not answered:
                    pub = mandates.approval_public(app_store.approval(kw["awaiting"]))
                    signed = approval_payload(m["owner"], pub)
                    result = app_store.decide_approval(pub["approval_id"], decision="approve", by=signed["by"],
                                                       proof={k: signed[k] for k in ("t", "n", "s")})
                    app_store.notify_decision(result)
                    answered.append(result["status"])
                return real_finish(self, row, **kw)

            monkeypatch.setattr(a2a_tasks.A2ATaskStore, "finish", finish)
            invoke = json.dumps(ECHO).encode()
            task = _mandated_send(client, m, invoke, "m-race",
                                  configuration={"taskPushNotificationConfig": {"url": HOOK}})["result"]["task"]
            assert answered == ["approved"]
            row = db._conn.execute("SELECT task_state, awaiting, status_json FROM a2a_tasks WHERE task_id = ?",
                                   (task["id"],)).fetchone()
            assert row["task_state"] == "TASK_STATE_AUTH_REQUIRED" and row["awaiting"] == ""
            assert "approved" in json.loads(row["status_json"])["message"]["parts"][0]["text"]
            _wait_calls(hook, 2)
            assert hook.states(task["id"]) == ["TASK_STATE_AUTH_REQUIRED"] * 2


def test_the_sweep_names_what_it_expired(tmp_path):
    from aimarket_hub.a2a_tasks import A2ATaskStore, AUTH_REQUIRED
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(tmp_path / "hub.db")
    store = A2ATaskStore(db._conn)
    row, _ = store.create(principal="anon:x", context_id="c", message_id="m", product_id="p", capability_id="c@v1",
                          source_hub="local", invoke_b64="", invoke_sha256="s", history=[])
    store.finish(row, state=AUTH_REQUIRED, status={"state": AUTH_REQUIRED})
    swept = store.sweep(now=time.time() + 10_000, force=True)
    assert swept["expired"] == 1 and swept["task_ids"] == [row["task_id"]]
    db.close()
