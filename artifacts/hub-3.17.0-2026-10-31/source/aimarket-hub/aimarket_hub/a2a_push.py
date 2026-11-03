"""A2A push notifications: webhooks a client registers for its own tasks (A2A 1.0 §4.3).

Why a hub that answers SendMessage synchronously needs them at all. Three things change a task
while its client is not on the line:

* a task sent with ``returnImmediately`` runs after the answer has gone (``a2a.py``);
* a task waiting on its owner's approval (mandates.md §5.6) moves when the OWNER answers, on
  another request, possibly hours later;
* the sweep fails a task that waited too long, or that a restart orphaned.

Without a push the client can only poll GetTask. With one, the hub POSTs a ``StreamResponse``
holding a ``statusUpdate`` to the client's webhook. It carries the status, never the
artifacts: a paid result is read with GetTask, under the same authorization as always, so a
webhook that leaks leaks a state change, not the purchase.

The webhook is an address the caller chose, so it gets the treatment every such address gets
on this hub (outbound_http): https only, no private or metadata networks (resolved once and
pinned, against DNS rebinding), no redirects, a short timeout and a capped reply. Delivery is
best effort and off the request path: a few retries, then the outcome is recorded on the
config and the task is still there to be read.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from aimarket_hub.db_backend import returning_one

logger = logging.getLogger(__name__)

MAX_CONFIGS_PER_TASK = 4
MAX_URL_CHARS = 2048
MAX_TOKEN_CHARS = 512
MAX_CREDENTIAL_CHARS = 2048
DELIVERY_TIMEOUT_S = 10.0
#: Seconds to wait before each retry; the first attempt is immediate.
RETRY_DELAYS_S = (2.0, 10.0)
MAX_REPLY_BYTES = 4096
#: Deliveries in flight at once across the hub. A burst beyond it waits its turn rather than
#: opening a connection per task. A slot is held for one attempt, never across a retry's
#: pause: webhooks that hang and fail would otherwise keep every slot through their whole
#: retry cycle, and every other task's push would wait behind them.
MAX_CONCURRENT_DELIVERIES = 16
#: Deliveries scheduled and not finished. Beyond it a push is dropped (and recorded on its
#: config): the task is stored either way, and memory is not a queue a caller can fill.
MAX_PENDING_DELIVERIES = 2048
MEDIA_TYPE = "application/a2a+json"

# RFC 9110 token for the scheme; credentials are printable ASCII without CR/LF — they go
# into an Authorization header, where a line break is a header injection. Always fullmatch:
# `$` also matches before a trailing newline.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]{0,31}")
_PRINTABLE = re.compile(r"[\x20-\x7e]*")
_CONFIG_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class PushConfigError(ValueError):
    """A config the hub will not store; the message is safe to return to the client."""


def enabled() -> bool:
    return os.getenv("AIMARKET_A2A_PUSH_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _allow_http() -> bool:
    """Plain http webhooks, for a local test rig only. Never on a public hub: the token and
    credentials would cross the network in clear."""
    return os.getenv("AIMARKET_A2A_PUSH_ALLOW_HTTP", "").strip() == "1"


def validate_url(url: Any) -> str:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS:
        raise PushConfigError(f"url must be an https URL of at most {MAX_URL_CHARS} characters")
    if any(c in url for c in "\r\n\t "):
        raise PushConfigError("url must not contain whitespace")
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and _allow_http()):
        raise PushConfigError("url must be https")
    if not parsed.hostname:
        raise PushConfigError("url has no host")
    if parsed.username or parsed.password:
        raise PushConfigError("url must not carry credentials; use authentication instead")
    from aimarket_hub import outbound_http

    if not _allow_http() and not outbound_http._url_is_safe(url):
        raise PushConfigError("url points at a private or reserved network")
    return url


def parse_config(obj: Any) -> dict[str, str]:
    """A ``TaskPushNotificationConfig`` from a client, checked. ``taskId`` and ``id`` are the
    caller's business; this reads what is delivered and how."""
    if not isinstance(obj, dict):
        raise PushConfigError("the push notification config must be an object")
    url = validate_url(obj.get("url"))
    token = obj.get("token") or ""
    if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS or not _PRINTABLE.fullmatch(token):
        raise PushConfigError(f"token must be printable ASCII of at most {MAX_TOKEN_CHARS} characters")
    scheme = credentials = ""
    auth = obj.get("authentication")
    if auth is not None:
        if not isinstance(auth, dict):
            raise PushConfigError("authentication must be an object {scheme, credentials}")
        scheme = auth.get("scheme") or ""
        credentials = auth.get("credentials") or ""
        if not isinstance(scheme, str) or not _SCHEME.fullmatch(scheme):
            raise PushConfigError("authentication.scheme must be an HTTP authentication scheme, e.g. Bearer")
        if (not isinstance(credentials, str) or len(credentials) > MAX_CREDENTIAL_CHARS
                or not _PRINTABLE.fullmatch(credentials)):
            raise PushConfigError("authentication.credentials must be printable ASCII on one line")
    config_id = obj.get("id") or ""
    if config_id and (not isinstance(config_id, str) or not _CONFIG_ID.fullmatch(config_id)):
        raise PushConfigError("id must be 1-64 characters of [A-Za-z0-9_.:-]")
    return {"url": url, "token": token, "auth_scheme": scheme, "auth_credentials": credentials,
            "config_id": config_id}


def render(row: dict[str, Any]) -> dict[str, Any]:
    """The ``TaskPushNotificationConfig`` as the hub returns it. Credentials are never sent
    back: the client has them, and an answer is one more place for them to leak from."""
    out: dict[str, Any] = {"id": row["config_id"], "taskId": row["task_id"], "url": row["url"]}
    if row.get("token"):
        out["token"] = row["token"]
    if row.get("auth_scheme"):
        out["authentication"] = {"scheme": row["auth_scheme"]}
    return out


class PushStore:
    """``a2a_push_configs`` on the hub's shared connection."""

    def __init__(self, conn: Any):
        self._conn = conn

    def create(self, task_id: str, config: dict[str, str], *, now: float | None = None) -> dict[str, Any]:
        """Store a config for a task. The same id again replaces it (a client re-registering
        after rotating its token); a fifth distinct one is refused."""
        now = time.time() if now is None else now
        config_id = config.get("config_id") or f"pnc_{secrets.token_hex(8)}"
        existing = self.get(task_id, config_id)
        if existing is None and len(self.list(task_id)) >= MAX_CONFIGS_PER_TASK:
            raise PushConfigError(f"a task takes at most {MAX_CONFIGS_PER_TASK} push notification configs")
        if existing is not None:
            self._conn.execute(
                "UPDATE a2a_push_configs SET url = ?, token = ?, auth_scheme = ?, auth_credentials = ?, "
                "last_status = 0, last_error = '' WHERE task_id = ? AND config_id = ?",
                (config["url"], config["token"], config["auth_scheme"], config["auth_credentials"],
                 task_id, config_id),
            )
            self._conn.commit()
        else:
            returning_one(
                self._conn,
                "INSERT INTO a2a_push_configs (task_id, config_id, url, token, auth_scheme, auth_credentials, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING RETURNING config_id",
                (task_id, config_id, config["url"], config["token"], config["auth_scheme"],
                 config["auth_credentials"], now),
                commit=True,
            )
        row = self.get(task_id, config_id)
        if row is None:  # pragma: no cover - deleted between two statements
            raise PushConfigError("the config could not be stored; retry")
        return row

    def get(self, task_id: str, config_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM a2a_push_configs WHERE task_id = ? AND config_id = ?", (task_id, config_id),
        ).fetchone()
        return dict(row) if row else None

    def list(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM a2a_push_configs WHERE task_id = ? ORDER BY created_at, config_id", (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, task_id: str, config_id: str) -> bool:
        gone = returning_one(
            self._conn,
            "DELETE FROM a2a_push_configs WHERE task_id = ? AND config_id = ? RETURNING config_id",
            (task_id, config_id), commit=True,
        )
        return gone is not None

    def record(self, task_id: str, config_id: str, *, status: int, error: str, now: float | None = None) -> None:
        self._conn.execute(
            "UPDATE a2a_push_configs SET last_status = ?, last_error = ?, last_sent_at = ? "
            "WHERE task_id = ? AND config_id = ?",
            (int(status), error[:300], time.time() if now is None else now, task_id, config_id),
        )
        self._conn.commit()

    def prune(self) -> int:
        """Configs of tasks that are gone (retention deleted them): their secrets go too."""
        cur = self._conn.execute(
            "DELETE FROM a2a_push_configs WHERE task_id NOT IN (SELECT task_id FROM a2a_tasks)",
        )
        self._conn.commit()
        try:
            return max(0, int(getattr(cur, "rowcount", 0) or 0))
        except (TypeError, ValueError):
            return 0


#: (url, JSON body, headers) -> (HTTP status, reply bytes)
PostCallable = Callable[[str, dict[str, Any], dict[str, str]], Awaitable[tuple[int, bytes]]]


async def _safe_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, bytes]:
    from aimarket_hub import outbound_http

    if _allow_http():
        import httpx

        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_S, follow_redirects=False) as client:
            response = await client.post(url, json=body, headers=headers)
            return response.status_code, response.content[:MAX_REPLY_BYTES]
    status, reply = await outbound_http.safe_post_capped(
        url, json=body, headers=headers, timeout=DELIVERY_TIMEOUT_S, max_bytes=MAX_REPLY_BYTES,
    )
    return status, reply


def status_update(task: dict[str, Any]) -> dict[str, Any]:
    """The StreamResponse a webhook receives for a rendered Task."""
    event: dict[str, Any] = {"taskId": task["id"], "contextId": task["contextId"], "status": task["status"]}
    metadata = task.get("metadata")
    if isinstance(metadata, dict) and metadata:
        event["metadata"] = metadata
    return {"statusUpdate": event}


class PushDispatcher:
    """Sends a task's status to every webhook registered for it, off the request path."""

    def __init__(self, store: PushStore, *, post: PostCallable | None = None,
                 retry_delays: tuple[float, ...] | None = None):
        self.store = store
        self._post = post
        self._retry_delays = retry_delays
        self._inflight: set[asyncio.Task[Any]] = set()
        self._gate: asyncio.Semaphore | None = None

    def notify(self, task: dict[str, Any]) -> int:
        """Schedule one delivery per config of ``task`` (a rendered Task). Returns how many
        were scheduled. Never raises: a push is a courtesy on top of a task that is recorded."""
        try:
            configs = self.store.list(str(task.get("id") or ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning("a2a push: reading configs of %s failed: %s", task.get("id"), exc)
            return 0
        if not configs:
            return 0
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("a2a push: no event loop to deliver %s on; the client must read the task", task.get("id"))
            return 0
        body = status_update(task)
        scheduled = 0
        for config in configs:
            if len(self._inflight) >= MAX_PENDING_DELIVERIES:
                logger.warning("a2a push: %d deliveries pending; dropped one for task %s",
                               len(self._inflight), task.get("id"))
                self._record(config, 0, "dropped: too many deliveries pending on this hub")
                continue
            job = loop.create_task(self._deliver(config, body))
            self._inflight.add(job)
            job.add_done_callback(self._inflight.discard)
            scheduled += 1
        return scheduled

    async def drain(self) -> None:
        """Wait for deliveries in flight (tests, and a clean shutdown)."""
        while self._inflight:
            await asyncio.gather(*list(self._inflight), return_exceptions=True)

    @staticmethod
    def headers_for(config: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": MEDIA_TYPE, "User-Agent": "aimarket-hub-a2a-push/1"}
        if config.get("auth_scheme"):
            value = config["auth_scheme"]
            if config.get("auth_credentials"):
                value = f"{value} {config['auth_credentials']}"
            headers["Authorization"] = value
        if config.get("token"):
            # The header A2A clients read the task token from (0.3 named it; 1.0 keeps `token`
            # in the config without naming a header, and clients still look here).
            headers["X-A2A-Notification-Token"] = config["token"]
        return headers

    async def _deliver(self, config: dict[str, Any], body: dict[str, Any]) -> None:
        if self._gate is None:
            self._gate = asyncio.Semaphore(MAX_CONCURRENT_DELIVERIES)
        headers = self.headers_for(config)
        post = self._post or _safe_post
        delays = RETRY_DELAYS_S if self._retry_delays is None else self._retry_delays
        status, error = 0, ""
        for delay in (0.0, *delays):
            if delay:
                await asyncio.sleep(delay)
            async with self._gate:
                try:
                    status, _ = await post(config["url"], body, headers)
                    error = "" if 200 <= status < 300 else f"HTTP {status}"
                except Exception as exc:  # noqa: BLE001 - a refused, unsafe or dead webhook
                    status, error = 0, f"{type(exc).__name__}: {exc}"[:300]
            # Retry what may pass next time: no answer, a 5xx, or a 429. A 4xx is the
            # client's webhook saying no; asking again would not change its mind.
            if 200 <= status < 300 or (400 <= status < 500 and status != 429):
                break
        self._record(config, status, error)

    def _record(self, config: dict[str, Any], status: int, error: str) -> None:
        try:
            self.store.record(config["task_id"], config["config_id"], status=status, error=error)
        except Exception as exc:  # noqa: BLE001
            logger.warning("a2a push: recording delivery to task %s failed: %s", config.get("task_id"), exc)
        if error:
            logger.info("a2a push: task %s config %s not delivered: %s",
                        config.get("task_id"), config.get("config_id"), error)
