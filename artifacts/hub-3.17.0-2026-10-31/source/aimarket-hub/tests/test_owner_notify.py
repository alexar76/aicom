"""Owners hear about approval requests (owner_notify.py, mandates.md §5.6).

The destinations are faked at the HTTP edge; everything else is the real app: the mandate,
the refusal that opens a request, the channel routes, the worker threads that deliver.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    ECHO, approval_payload, funded_account, hub, list_static, mandated_invoke, setup_mandate,
)
from aimarket_hub import owner_notify
from aimarket_hub.owner_notify import NotifyConfigError, parse_channel

BOT = "123456789:" + "A" * 35
SLACK = "https://hooks.slack.com/services/T000/B000/" + "x" * 24
JIRA = {"kind": "jira", "base_url": "https://93.184.216.34", "email": "ops@example.com",
        "api_token": "jira-token-123", "project_key": "OPS"}
HOOK = {"kind": "webhook", "url": "https://93.184.216.34/approvals", "secret": "s3cret"}


class FakeWeb:
    """Every destination at once: records each request, answers from a script per host."""

    def __init__(self):
        self.calls: list[dict] = []
        self.lock = threading.Lock()
        self.answers: dict[str, list[tuple[int, str]]] = {}

    def __call__(self, method, url, headers, body):
        with self.lock:
            self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
            for prefix, script in self.answers.items():
                if url.startswith(prefix):
                    return script.pop(0) if len(script) > 1 else script[0]
        if "/rest/api/3/issue" in url and url.endswith("/issue"):
            return 201, json.dumps({"id": "10001", "key": "OPS-7"})
        return 200, json.dumps({"ok": True})

    def wait(self, n, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if len(self.calls) >= n:
                    return list(self.calls)
            time.sleep(0.02)
        with self.lock:
            return list(self.calls)

    def to(self, part):
        return [c for c in self.calls if part in c["url"]]


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    monkeypatch.setattr(owner_notify, "_http", fake)
    monkeypatch.setattr(owner_notify, "RETRY_DELAYS_S", (0.0, 0.0))
    return fake


# ── what a channel may be ─────────────────────────────────────────────────

class TestChannels:
    def test_good_channels(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN", BOT)
        assert parse_channel({"kind": "telegram", "chat_id": "2047891125"}) == (
            "telegram", {"chat_id": "2047891125", "bot_token": ""})
        assert parse_channel({"kind": "telegram", "chat_id": -100123, "bot_token": BOT})[1]["bot_token"] == BOT
        assert parse_channel({"kind": "slack", "webhook_url": SLACK})[1] == {"webhook_url": SLACK}
        assert parse_channel(JIRA)[1]["issue_type"] == "Task"
        assert parse_channel(HOOK)[1] == {"url": HOOK["url"], "secret": "s3cret"}

    @pytest.mark.parametrize("obj, why", [
        ({"kind": "email"}, "kind"),
        ({"kind": "telegram", "chat_id": "not a chat"}, "chat_id"),
        ({"kind": "telegram", "chat_id": "1", "bot_token": "nope"}, "bot_token"),
        ({"kind": "telegram", "chat_id": "1"}, "no Telegram bot"),         # no hub bot configured
        ({"kind": "slack", "webhook_url": "https://evil.example/hook"}, "Slack"),
        ({"kind": "jira", **{**JIRA, "base_url": "https://127.0.0.1"}}, "private"),
        ({"kind": "jira", **{**JIRA, "base_url": "http://93.184.216.34"}}, "https"),
        ({"kind": "jira", **{**JIRA, "project_key": "ops; drop"}}, "project_key"),
        ({"kind": "jira", **{**JIRA, "api_token": "t\nX-Evil: 1"}}, "api_token"),
        ({"kind": "webhook", "url": "https://169.254.169.254/latest"}, "private"),
        ({"kind": "webhook", "url": "https://user:pw@93.184.216.34/x"}, "credentials"),
        ({"kind": "webhook", "url": "https://93.184.216.34/x", "secret": "s\nx"}, "secret"),
    ])
    def test_channels_the_hub_will_not_use(self, monkeypatch, obj, why):
        monkeypatch.delenv("AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(NotifyConfigError, match=why):
            parse_channel(obj)

    def test_secrets_are_never_shown(self):
        for kind, target in (("telegram", {"chat_id": "1", "bot_token": BOT}), ("slack", {"webhook_url": SLACK}),
                             ("jira", parse_channel(JIRA)[1]), ("webhook", {"url": HOOK["url"], "secret": "s3cret"})):
            shown = json.dumps(owner_notify.public({"channel_id": "nch_x", "kind": kind,
                                                    "target_json": json.dumps(target), "created_at": 1}))
            for secret in (BOT, SLACK, "jira-token-123", "s3cret"):
                assert secret not in shown, (kind, secret)


# ── end to end ────────────────────────────────────────────────────────────

def _add(client, key, body):
    r = client.post("/ai-market/v2/mandates/notify", headers={"X-API-Key": key}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


class TestFlow:
    def test_every_channel_hears_the_request_and_the_answer(self, monkeypatch, tmp_path, web):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=3_000)
            for body in ({"kind": "telegram", "chat_id": "2047891125", "bot_token": BOT},
                         {"kind": "slack", "webhook_url": SLACK}, JIRA, HOOK):
                _add(client, m["api_key"], body)
            listed = client.get("/ai-market/v2/mandates/notify", headers={"X-API-Key": m["api_key"]}).json()
            assert [c["kind"] for c in listed["channels"]] == ["telegram", "slack", "jira", "webhook"]

            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            calls = web.wait(4)
            assert len(calls) == 4

            tg, = web.to("api.telegram.org")
            assert tg["url"] == f"https://api.telegram.org/bot{BOT}/sendMessage"
            sent = json.loads(tg["body"])
            assert sent["chat_id"] == "2047891125" and sent["parse_mode"] == "HTML"
            assert "demo.echo@v1" in sent["text"] and approval["approval_id"] in sent["text"]

            slack, = web.to("hooks.slack.com")
            assert approval["approval_id"] in json.loads(slack["body"])["text"]

            jira, = web.to("/rest/api/3/issue")
            assert jira["headers"]["Authorization"] == "Basic " + base64.b64encode(
                b"ops@example.com:jira-token-123").decode()
            fields = json.loads(jira["body"])["fields"]
            assert fields["project"] == {"key": "OPS"} and fields["issuetype"] == {"name": "Task"}
            assert fields["description"]["type"] == "doc" and "aimarket-approval" in fields["labels"]

            hook, = web.to("/approvals")
            stamp, mac = (p.split("=", 1)[1] for p in hook["headers"]["X-AIMarket-Signature"].split(","))
            assert mac == hmac.new(b"s3cret", stamp.encode() + b"." + hook["body"], hashlib.sha256).hexdigest()
            event = json.loads(hook["body"])
            assert event["event"] == "mandate.approval.requested"
            assert event["approval"]["approval_id"] == approval["approval_id"]
            assert "account_id" not in event["approval"]

            # The same call again before an answer is the same request: nobody is told twice.
            mandated_invoke(client, m, ECHO)
            time.sleep(0.3)
            assert len(web.calls) == 4

            r = client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                            json=approval_payload(m["owner"], approval))
            assert r.status_code == 200
            calls = web.wait(8)
            assert len(calls) == 8
            comment = [c for c in web.calls if c["url"].endswith("/rest/api/3/issue/OPS-7/comment")]
            assert len(comment) == 1, "the answer lands on the issue the request opened"
            assert "approved" in json.loads(web.to("api.telegram.org")[-1]["body"])["text"]
            assert json.loads(web.to("/approvals")[-1]["body"])["event"] == "mandate.approval.approved"

            listed = client.get("/ai-market/v2/mandates/notify", headers={"X-API-Key": m["api_key"]}).json()
            assert all(c["last_delivery"]["status"] in (200, 201) for c in listed["channels"])

    def test_two_racing_calls_tell_the_owner_once(self, monkeypatch, tmp_path, web):
        """Two identical calls can both find no request and both insert one; the second insert
        loses on the pending index and must not announce the winner's request again."""
        from aimarket_hub import mandates

        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=3_000)
            _add(client, m["api_key"], {"kind": "slack", "webhook_url": SLACK})
            body_sha = hashlib.sha256(json.dumps(ECHO).encode()).hexdigest()
            real_new_id = mandates.new_approval_id
            winner = real_new_id()

            def other_request_first() -> str:
                # What the other call does in the gap: its request lands first.
                now = time.time()
                db._conn.execute(
                    "INSERT INTO mandate_approvals (approval_id, account_id, leaf_digest, agent, capability_id, "
                    "product_id, source_hub, body_sha256, amount_micro, max_micro, threshold_micro, status, "
                    "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (winner, m["account"], m["digest"], m["agent"].did, ECHO["capability_id"], ECHO["product_id"],
                     "local", body_sha, 4_000, 4_000, 3_000, "pending", now, now + 3600))
                db._conn.commit()
                return real_new_id()

            monkeypatch.setattr(mandates, "new_approval_id", other_request_first)
            r = mandated_invoke(client, m, ECHO)
            assert r.json()["error"] == "approval_required"
            assert r.json()["approval"]["approval_id"] == winner, "the race was staged"
            time.sleep(0.3)
            assert web.calls == [], "the loser of the race announced the winner's request"

    def test_a_channel_belongs_to_its_account(self, monkeypatch, tmp_path, web):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db, approval_above=3_000)
            ch = _add(client, m["api_key"], {"kind": "slack", "webhook_url": SLACK})
            _other, other_key = funded_account(client, db)
            assert client.get("/ai-market/v2/mandates/notify",
                              headers={"X-API-Key": other_key}).json()["channels"] == []
            assert client.delete(f"/ai-market/v2/mandates/notify/{ch['channel_id']}",
                                 headers={"X-API-Key": other_key}).status_code == 404
            assert client.post(f"/ai-market/v2/mandates/notify/{ch['channel_id']}/test",
                               headers={"X-API-Key": other_key}).status_code == 404
            assert client.get("/ai-market/v2/mandates/notify").status_code == 401
            assert client.delete(f"/ai-market/v2/mandates/notify/{ch['channel_id']}",
                                 headers={"X-API-Key": m["api_key"]}).status_code == 200

    def test_the_test_button_says_what_the_channel_said(self, monkeypatch, tmp_path, web):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            ch = _add(client, m["api_key"], {"kind": "telegram", "chat_id": "42", "bot_token": BOT})
            web.answers["https://api.telegram.org"] = [(400, json.dumps({"ok": False,
                                                                        "description": "Bad Request: chat not found"}))]
            r = client.post(f"/ai-market/v2/mandates/notify/{ch['channel_id']}/test",
                            headers={"X-API-Key": m["api_key"]}).json()
            assert r["delivered"] is False and "chat not found" in r["detail"]
            assert r["channel"]["last_delivery"]["error"] == "Bad Request: chat not found"
            assert BOT not in json.dumps(r)
            web.answers.clear()
            r = client.post(f"/ai-market/v2/mandates/notify/{ch['channel_id']}/test",
                            headers={"X-API-Key": m["api_key"]}).json()
            assert r["delivered"] is True

    def test_an_account_takes_a_bounded_number_of_channels(self, monkeypatch, tmp_path, web):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            for _ in range(owner_notify.MAX_CHANNELS_PER_ACCOUNT):
                _add(client, m["api_key"], {"kind": "slack", "webhook_url": SLACK})
            r = client.post("/ai-market/v2/mandates/notify", headers={"X-API-Key": m["api_key"]},
                            json={"kind": "slack", "webhook_url": SLACK})
            assert r.status_code == 400 and "at most" in r.json()["detail"]


# ── delivery ──────────────────────────────────────────────────────────────

class _Store:
    def __init__(self):
        self.recorded: list[tuple] = []
        self.refs: dict = {}

    def record(self, channel_id, *, status, error, now=None):
        self.recorded.append((channel_id, status, error))

    def ref(self, approval_id, channel_id):
        return self.refs.get((approval_id, channel_id), "")

    def remember_ref(self, approval_id, channel_id, ref):
        self.refs[(approval_id, channel_id)] = ref


def _channel(kind, target):
    return {"channel_id": "nch_1", "kind": kind, "target_json": json.dumps(target)}


APPROVAL = {"approval_id": "apr_" + "a" * 24, "capability_id": "demo.echo@v1", "amount_usd": 12.0,
            "max_usd": 12.13, "threshold_usd": 10.0, "agent": "did:key:z6Mk" + "x" * 40,
            "expires_at": "2026-10-22T00:00:00Z", "url": "https://hub.test/ai-market/v2/mandates/approvals/apr_x"}


class TestDelivery:
    def test_telegram_falls_back_to_plain_text_when_the_markup_is_refused(self):
        calls = []

        def post(method, url, headers, body):
            calls.append(json.loads(body))
            if len(calls) == 1:
                return 400, json.dumps({"ok": False, "description": "Bad Request: can't parse entities"})
            return 200, json.dumps({"ok": True})

        notifier = owner_notify.OwnerNotifier(_Store(), None, post=post, retry_delays=())
        ok, status, _ = notifier._send(_channel("telegram", {"chat_id": "1", "bot_token": BOT}), "requested",
                                       APPROVAL, retry=True)
        assert ok and status == 200
        assert calls[0]["parse_mode"] == "HTML" and "parse_mode" not in calls[1]

    def test_retries_what_may_pass_and_stops_on_a_refusal(self):
        script = [(503, ""), (0, None), (200, "ok")]
        seen = []

        def post(method, url, headers, body):
            seen.append(url)
            status, reply = script.pop(0)
            if reply is None:
                raise ConnectionError("refused")
            return status, reply

        notifier = owner_notify.OwnerNotifier(_Store(), None, post=post, retry_delays=(0.0, 0.0))
        ok, _, _ = notifier._send(_channel("slack", {"webhook_url": SLACK}), "requested", APPROVAL, retry=True)
        assert ok and len(seen) == 3
        seen.clear()
        script[:] = [(404, "no_service")]
        ok, status, detail = notifier._send(_channel("slack", {"webhook_url": SLACK}), "requested", APPROVAL,
                                            retry=True)
        assert not ok and status == 404 and len(seen) == 1

    def test_an_error_never_carries_a_secret(self):
        def post(method, url, headers, body):
            raise ConnectionError(f"failed to reach {url}")

        notifier = owner_notify.OwnerNotifier(_Store(), None, post=post, retry_delays=())
        for kind, target, secret in (("telegram", {"chat_id": "1", "bot_token": BOT}, BOT),
                                     ("slack", {"webhook_url": SLACK}, SLACK)):
            ok, _, detail = notifier._send(_channel(kind, target), "requested", APPROVAL, retry=True)
            assert not ok and secret not in detail and "<hidden>" in detail

    def test_html_is_escaped_in_telegram(self):
        words = owner_notify.message("requested", {**APPROVAL, "capability_id": "<b>x</b>&"})
        text = owner_notify._telegram_html(words)
        assert "&lt;b&gt;x&lt;/b&gt;&amp;" in text and text.startswith("<b>")
