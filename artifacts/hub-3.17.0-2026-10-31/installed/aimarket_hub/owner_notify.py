"""Telling an account's owners that a call waits for them (mandates.md §5.6).

A mandate with ``approvalAbove`` stops a large call until an owner signs it. Until now the
owner learnt that only by asking (``GET /mandates/approvals?status=pending``): the agent's
A2A webhook heard about the wait, the person whose signature it waited for did not. This
module sends each new request — and each answer — to channels the funding account chose:

* ``telegram`` — a message in a chat, from the hub's own bot (``AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN``,
  the owner only gives a chat id after pressing Start) or from the owner's bot (its token).
  HTML first, plain text if Telegram refuses the markup — the same rule as SKOPOS and the
  fleet alerter, so one bad character never silences the channel.
* ``slack`` — an incoming webhook (``https://hooks.slack.com/…``).
* ``jira`` — an issue in a Jira Cloud project (REST API v3, the owner's e-mail and API
  token); an answer to the request is added to that issue as a comment.
* ``webhook`` — any https endpoint, the JSON event signed with HMAC-SHA256 when a secret is set.

A notification tells; it never approves. Approving needs an owner key's signature over the
exact request (mandates.py), which no chat, channel or ticket holds. Every message says how
to approve and how to deny.

The account's API key manages its channels — the same key already lists the account's
pending requests, so a channel reveals nothing the key does not. Channel secrets (a bot
token, a webhook URL, a Jira token) are stored to be used and are never returned.
Delivery runs off the request path, retries what may pass later, and records its outcome
on the channel; it never touches the request it reports on.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from aimarket_hub.db_backend import returning_one

logger = logging.getLogger(__name__)

KINDS = ("telegram", "slack", "jira", "webhook")
MAX_CHANNELS_PER_ACCOUNT = 8
DELIVERY_TIMEOUT_S = 10.0
RETRY_DELAYS_S = (2.0, 10.0)
MAX_REPLY_BYTES = 64 * 1024
TELEGRAM_API = "https://api.telegram.org"
SLACK_HOOKS = ("https://hooks.slack.com/services/", "https://hooks.slack.com/triggers/")

_PRINTABLE = re.compile(r"[\x20-\x7e]*")
_TELEGRAM_TOKEN = re.compile(r"\d{5,15}:[A-Za-z0-9_-]{30,60}")
_TELEGRAM_CHAT = re.compile(r"-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31}")
_JIRA_PROJECT = re.compile(r"[A-Z][A-Z0-9_]{1,19}")
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}")


class NotifyConfigError(ValueError):
    """A channel the hub will not store; the message is safe to return."""


def _secret_env(name: str) -> str:
    path = (os.getenv(f"{name}_FILE") or "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            logger.error("owner notify: %s_FILE is set but unreadable", name)
            return ""
    return (os.getenv(name) or "").strip()


def hub_bot_token() -> str:
    """The hub's own Telegram bot, offered to owners who give only a chat id. Never logged."""
    return _secret_env("AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN")


def hub_bot_name() -> str:
    return (os.getenv("AIMARKET_NOTIFY_TELEGRAM_BOT_NAME") or "").strip().lstrip("@")


def _printable(value: Any, name: str, *, limit: int, required: bool = True) -> str:
    text = value if isinstance(value, str) else ""
    text = text.strip()
    if not text and required:
        raise NotifyConfigError(f"{name} is required")
    if len(text) > limit or not _PRINTABLE.fullmatch(text):
        raise NotifyConfigError(f"{name} must be printable ASCII of at most {limit} characters")
    return text


def _safe_https(url: Any, name: str) -> str:
    """An https URL a caller chose: no whitespace, no userinfo, no private network."""
    from urllib.parse import urlparse

    from aimarket_hub import outbound_http

    text = _printable(url, name, limit=2048)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise NotifyConfigError(f"{name} must be an https URL")
    if parsed.username or parsed.password:
        raise NotifyConfigError(f"{name} must not carry credentials")
    if not outbound_http._url_is_safe(text):
        raise NotifyConfigError(f"{name} points at a private or reserved network")
    return text


def parse_channel(obj: Any) -> tuple[str, dict[str, str]]:
    """(kind, target) from what an owner sent, checked."""
    if not isinstance(obj, dict):
        raise NotifyConfigError("a channel is a JSON object with a kind")
    kind = obj.get("kind")
    if kind not in KINDS:
        raise NotifyConfigError(f"kind must be one of {', '.join(KINDS)}")
    if kind == "telegram":
        chat = _printable(str(obj.get("chat_id") or ""), "chat_id", limit=40)
        if not _TELEGRAM_CHAT.fullmatch(chat):
            raise NotifyConfigError("chat_id must be a numeric Telegram chat id or an @channel name")
        token = _printable(obj.get("bot_token") or "", "bot_token", limit=80, required=False)
        if token and not _TELEGRAM_TOKEN.fullmatch(token):
            raise NotifyConfigError("bot_token must be a Telegram bot token (digits:letters)")
        if not token and not hub_bot_token():
            raise NotifyConfigError("this hub has no Telegram bot of its own: give bot_token")
        return kind, {"chat_id": chat, "bot_token": token}
    if kind == "slack":
        url = _printable(obj.get("webhook_url"), "webhook_url", limit=512)
        if not url.startswith(SLACK_HOOKS):
            raise NotifyConfigError("webhook_url must be a Slack incoming webhook (https://hooks.slack.com/…)")
        return kind, {"webhook_url": url}
    if kind == "jira":
        base = _safe_https(obj.get("base_url"), "base_url").rstrip("/")
        email = _printable(obj.get("email"), "email", limit=254)
        if not _EMAIL.fullmatch(email):
            raise NotifyConfigError("email must be the Jira account's e-mail")
        token = _printable(obj.get("api_token"), "api_token", limit=512)
        project = _printable(obj.get("project_key"), "project_key", limit=20)
        if not _JIRA_PROJECT.fullmatch(project):
            raise NotifyConfigError("project_key must be a Jira project key, e.g. OPS")
        issue_type = _printable(obj.get("issue_type") or "Task", "issue_type", limit=40)
        return kind, {"base_url": base, "email": email, "api_token": token, "project_key": project,
                      "issue_type": issue_type}
    url = _safe_https(obj.get("url"), "url")
    secret = _printable(obj.get("secret") or "", "secret", limit=256, required=False)
    return kind, {"url": url, "secret": secret}


def public(row: dict[str, Any]) -> dict[str, Any]:
    """A channel as its account sees it: where it goes, never the secret that reaches it."""
    target = _load(row.get("target_json"))
    out: dict[str, Any] = {"channel_id": row["channel_id"], "kind": row["kind"]}
    if row["kind"] == "telegram":
        out.update(chat_id=target.get("chat_id"), bot="own" if target.get("bot_token") else "hub")
    elif row["kind"] == "slack":
        out["webhook"] = "https://hooks.slack.com/…" + str(target.get("webhook_url", ""))[-4:]
    elif row["kind"] == "jira":
        out.update({k: target.get(k) for k in ("base_url", "email", "project_key", "issue_type")})
    else:
        out.update(url=target.get("url"), signed=bool(target.get("secret")))
    out["created_at"] = _iso(float(row.get("created_at") or 0))
    if row.get("last_sent_at"):
        out["last_delivery"] = {"at": _iso(float(row["last_sent_at"])), "status": int(row.get("last_status") or 0),
                                "error": row.get("last_error") or ""}
    return out


def _load(text: Any) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


# ── storage ──────────────────────────────────────────────────────────────────


class NotifyStore:
    """``owner_notify_channels`` and ``owner_notify_refs`` on the hub's shared connection."""

    def __init__(self, conn: Any):
        self._conn = conn

    def add(self, account_id: str, kind: str, target: dict[str, str], *, now: float | None = None) -> dict[str, Any]:
        if len(self.list(account_id)) >= MAX_CHANNELS_PER_ACCOUNT:
            raise NotifyConfigError(f"an account takes at most {MAX_CHANNELS_PER_ACCOUNT} channels")
        channel_id = f"nch_{secrets.token_hex(8)}"
        self._conn.execute(
            "INSERT INTO owner_notify_channels (channel_id, account_id, kind, target_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, account_id, kind, json.dumps(target, separators=(",", ":")),
             time.time() if now is None else now),
        )
        self._conn.commit()
        row = self.get(account_id, channel_id)
        assert row is not None
        return row

    def get(self, account_id: str, channel_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM owner_notify_channels WHERE account_id = ? AND channel_id = ?", (account_id, channel_id),
        ).fetchone()
        return dict(row) if row else None

    def list(self, account_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM owner_notify_channels WHERE account_id = ? ORDER BY created_at, channel_id", (account_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, account_id: str, channel_id: str) -> bool:
        gone = returning_one(
            self._conn,
            "DELETE FROM owner_notify_channels WHERE account_id = ? AND channel_id = ? RETURNING channel_id",
            (account_id, channel_id), commit=True,
        )
        return gone is not None

    def record(self, channel_id: str, *, status: int, error: str, now: float | None = None) -> None:
        self._conn.execute(
            "UPDATE owner_notify_channels SET last_status = ?, last_error = ?, last_sent_at = ? WHERE channel_id = ?",
            (int(status), error[:300], time.time() if now is None else now, channel_id),
        )
        self._conn.commit()

    def remember_ref(self, approval_id: str, channel_id: str, ref: str) -> None:
        self._conn.execute(
            "INSERT INTO owner_notify_refs (approval_id, channel_id, external_ref) VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING", (approval_id, channel_id, ref[:200]),
        )
        self._conn.commit()

    def ref(self, approval_id: str, channel_id: str) -> str:
        row = self._conn.execute(
            "SELECT external_ref FROM owner_notify_refs WHERE approval_id = ? AND channel_id = ?",
            (approval_id, channel_id),
        ).fetchone()
        return str(dict(row)["external_ref"]) if row else ""


# ── what is said ─────────────────────────────────────────────────────────────


def _short(did: str) -> str:
    return did if len(did) <= 26 else f"{did[:18]}…{did[-6:]}"


def message(event: str, approval: dict[str, Any]) -> dict[str, Any]:
    """The words of a notification, one shape for every channel: a title and lines."""
    rid = approval.get("approval_id", "")
    url = approval.get("url", "")
    if event == "requested":
        title = (f"Approval needed: {approval.get('capability_id')} for ${approval.get('amount_usd'):g}"
                 if isinstance(approval.get("amount_usd"), (int, float)) else "Approval needed")
        lines = [
            f"An agent ({_short(str(approval.get('agent', '')))}) wants to call {approval.get('capability_id')} "
            f"for ${approval.get('amount_usd')} (at most ${approval.get('max_usd')}), over the "
            f"${approval.get('threshold_usd')} its mandate may spend without you.",
            f"Request {rid}, open until {approval.get('expires_at')}. Nothing is spent until you answer.",
            f"Approve: sign it with an owner key — POST {url} with "
            "aimarket_agent.approval_payload(owner_key, hub_origin=…, approval=…).",
            f"Deny: curl -X POST {url} -H 'X-API-Key: <account key>' -H 'Content-Type: application/json' "
            "-d '{\"decision\": \"deny\"}'",
        ]
    elif event == "test":
        title = "AIMarket hub: notifications are set up"
        lines = ["This channel will be told when a mandate's call waits for an owner's approval, "
                 "and when an owner answers. A test only; nothing waits."]
    else:
        status = approval.get("status") or event
        title = f"Request {rid} {status}"
        lines = [f"{approval.get('capability_id')} for ${approval.get('amount_usd')} was {status} by "
                 f"{_short(str(approval.get('decided_by', '')))} at {approval.get('decided_at', '')}."]
        if status == "approved":
            lines.append("The agent may now send the same call again; it runs once.")
    return {"event": event, "title": title, "lines": lines, "url": url}


def _telegram_html(words: dict[str, Any]) -> str:
    body = "\n".join(html.escape(line) for line in words["lines"])
    return f"<b>{html.escape(words['title'])}</b>\n{body}"[:4096]


def _plain(words: dict[str, Any]) -> str:
    return (words["title"] + "\n" + "\n".join(words["lines"]))[:4096]


def _adf(lines: list[str]) -> dict[str, Any]:
    """Atlassian Document Format: one paragraph per line."""
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line[:3000]}]} for line in lines]}


# ── delivery ─────────────────────────────────────────────────────────────────

#: (method, url, headers, body bytes) -> (HTTP status, reply text)
PostCallable = Callable[[str, str, dict[str, str], bytes], tuple[int, str]]


def _http(method: str, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
    """One request to a destination an owner chose: validated, pinned against DNS rebinding,
    no redirects, a short timeout, a capped reply."""
    import httpx

    from aimarket_hub import outbound_http

    target, pin_headers, ext = outbound_http.prepare_safe_request(url)
    with httpx.Client(timeout=DELIVERY_TIMEOUT_S, follow_redirects=False) as client:
        with client.stream(method, target, headers={**headers, **pin_headers}, content=body,
                           extensions=ext or None) as response:
            chunks = bytearray()
            for chunk in response.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_REPLY_BYTES:
                    break
            return response.status_code, bytes(chunks[:MAX_REPLY_BYTES]).decode("utf-8", "replace")


class OwnerNotifier:
    """Sends approval events to an account's channels, in worker threads."""

    def __init__(self, store: NotifyStore, mandate_store: Any, *, post: PostCallable | None = None,
                 retry_delays: tuple[float, ...] | None = None, workers: int = 4):
        self.store = store
        self.mandates = mandate_store
        self._post = post
        self._retry_delays = retry_delays
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="owner-notify")
        self._futures: list[Future[Any]] = []
        self._lock = threading.Lock()

    # hooks the mandate store calls ------------------------------------------

    def on_requested(self, row: dict[str, Any]) -> None:
        """A NEW approval request (internal row, with its account)."""
        from aimarket_hub import mandates

        approval = mandates.approval_public(row, base_url=self.mandates.hub_origin)
        self._fan_out(str(row["account_id"]), "requested", approval)

    def on_decided(self, approval: dict[str, Any]) -> None:
        row = self.mandates.approval(str(approval.get("approval_id") or ""))
        if row is None:
            return
        self._fan_out(str(row["account_id"]), str(approval.get("status") or "decided"), approval)

    def _fan_out(self, account_id: str, event: str, approval: dict[str, Any]) -> None:
        try:
            channels = self.store.list(account_id)
        except Exception as exc:  # noqa: BLE001 - telling is best effort
            logger.warning("owner notify: reading channels of %s failed: %s", account_id, exc)
            return
        for channel in channels:
            future = self._pool.submit(self._deliver, channel, event, approval)
            with self._lock:
                self._futures = [f for f in self._futures if not f.done()] + [future]

    def drain(self, timeout: float = 30.0) -> None:
        """Wait for deliveries in flight (tests, and a clean shutdown)."""
        deadline = time.time() + timeout
        while True:
            with self._lock:
                pending = [f for f in self._futures if not f.done()]
            if not pending or time.time() > deadline:
                return
            pending[0].result(timeout=max(0.0, deadline - time.time()))

    # sending ------------------------------------------------------------------

    def send_test(self, channel: dict[str, Any]) -> tuple[bool, str]:
        """Deliver a test message now and say what happened (the route waits for it)."""
        ok, status, detail = self._send(channel, "test", {}, retry=False)
        self.store.record(channel["channel_id"], status=status, error="" if ok else detail)
        return ok, detail

    def _deliver(self, channel: dict[str, Any], event: str, approval: dict[str, Any]) -> None:
        ok, status, detail = self._send(channel, event, approval, retry=True)
        try:
            self.store.record(channel["channel_id"], status=status, error="" if ok else detail)
        except Exception as exc:  # noqa: BLE001
            logger.warning("owner notify: recording delivery on %s failed: %s", channel.get("channel_id"), exc)
        if not ok:
            logger.warning("owner notify: %s channel %s not delivered: %s", channel.get("kind"),
                           channel.get("channel_id"), detail)

    def _send(self, channel: dict[str, Any], event: str, approval: dict[str, Any], *,
              retry: bool) -> tuple[bool, int, str]:
        post = self._post or _http
        delays = (RETRY_DELAYS_S if self._retry_delays is None else self._retry_delays) if retry else ()
        target = _load(channel.get("target_json"))
        words = message(event, approval)
        status, detail = 0, ""
        for delay in (0.0, *delays):
            if delay:
                time.sleep(delay)
            try:
                status, detail = self._send_once(post, channel, target, words, approval)
            except Exception as exc:  # noqa: BLE001 - an unsafe, refused or dead destination
                status, detail = 0, f"{type(exc).__name__}: {exc}"[:300]
            if 200 <= status < 300 or (400 <= status < 500 and status != 429):
                break
        if 200 <= status < 300:
            return True, status, "ok"
        # An error text can quote the URL it failed on — and a Telegram URL carries the bot
        # token, a Slack one is itself the secret. None of it may reach the channel record.
        for hidden in (target.get("bot_token"), hub_bot_token(), target.get("api_token"), target.get("secret"),
                       target.get("webhook_url")):
            if hidden:
                detail = detail.replace(hidden, "<hidden>")
        return False, status, detail

    def _send_once(self, post: PostCallable, channel: dict[str, Any], target: dict[str, str],
                   words: dict[str, Any], approval: dict[str, Any]) -> tuple[int, str]:
        kind = channel["kind"]
        json_headers = {"Content-Type": "application/json", "User-Agent": "aimarket-hub-owner-notify/1"}
        if kind == "telegram":
            token = target.get("bot_token") or hub_bot_token()
            if not token:
                return 0, "no Telegram bot token (the hub's was removed)"
            url = f"{TELEGRAM_API}/bot{token}/sendMessage"
            body = {"chat_id": target["chat_id"], "text": _telegram_html(words), "parse_mode": "HTML",
                    "disable_web_page_preview": True}
            status, reply = post("POST", url, json_headers, json.dumps(body).encode())
            if status == 400 and "parse" in reply.lower():
                # Telegram refused the markup: the same words as plain text, rather than silence.
                body = {"chat_id": target["chat_id"], "text": _plain(words), "disable_web_page_preview": True}
                status, reply = post("POST", url, json_headers, json.dumps(body).encode())
            return status, _telegram_error(reply, token)
        if kind == "slack":
            body = {"text": _plain(words)}
            return post("POST", target["webhook_url"], json_headers, json.dumps(body).encode())
        if kind == "jira":
            return self._jira(post, channel, target, words, approval, json_headers)
        payload = json.dumps({"event": f"mandate.approval.{words['event']}", "approval": approval,
                              "title": words["title"], "text": _plain(words)}, separators=(",", ":")).encode()
        headers = {**json_headers, "X-AIMarket-Event": f"mandate.approval.{words['event']}"}
        if target.get("secret"):
            stamp = str(int(time.time()))
            mac = hmac.new(target["secret"].encode(), stamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
            headers["X-AIMarket-Signature"] = f"t={stamp},v1={mac}"
        return post("POST", target["url"], headers, payload)

    def _jira(self, post: PostCallable, channel: dict[str, Any], target: dict[str, str], words: dict[str, Any],
              approval: dict[str, Any], json_headers: dict[str, str]) -> tuple[int, str]:
        auth = base64.b64encode(f"{target['email']}:{target['api_token']}".encode()).decode()
        headers = {**json_headers, "Authorization": f"Basic {auth}", "Accept": "application/json"}
        base = target["base_url"]
        rid = str(approval.get("approval_id") or "")
        issue = self.store.ref(rid, channel["channel_id"]) if rid and words["event"] != "requested" else ""
        if issue:
            # An answer goes on the issue the request opened, not into a new one.
            body = {"body": _adf([words["title"], *words["lines"]])}
            return post("POST", f"{base}/rest/api/3/issue/{issue}/comment", headers, json.dumps(body).encode())
        body = {"fields": {
            "project": {"key": target["project_key"]},
            "issuetype": {"name": target["issue_type"]},
            "summary": words["title"][:250],
            "description": _adf(words["lines"]),
            "labels": ["aimarket-approval"],
        }}
        status, reply = post("POST", f"{base}/rest/api/3/issue", headers, json.dumps(body).encode())
        if 200 <= status < 300 and rid and words["event"] == "requested":
            key = str(_load(reply).get("key") or "")
            if key:
                self.store.remember_ref(rid, channel["channel_id"], key)
        return status, reply[:300]


def _telegram_error(reply: str, token: str) -> str:
    """Telegram's own description of a failure, with the token never in it."""
    try:
        detail = str(json.loads(reply).get("description") or reply)
    except (TypeError, ValueError):
        detail = reply
    return detail.replace(token, "<token>")[:300]
