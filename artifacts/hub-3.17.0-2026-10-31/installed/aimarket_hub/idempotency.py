"""``Idempotency-Key`` for paid invokes: a retry after a timeout is not a second purchase.

A buyer whose ``POST /ai-market/v2/invoke`` timed out cannot tell whether the call ran. On
the x402 and escrow-channel rails the retry is safe already — the buyer's signed nonce or
receiptId can be used once. On the credits rail (``X-API-Key``) and on a ledger channel
(``X-Payment-Channel`` + its secret) the hub minted a fresh receipt for every request, so the
retry ran the provider again and charged again. An outside review (2026-10-22) asked for
exactly this test.

With an ``Idempotency-Key`` header (1-128 of ``A-Z a-z 0-9 . _ : -``) on such a call, the hub
keeps the first answer for 24 hours, keyed by the credential (hashed) and the key:

* the same key with the same body returns the stored answer, marked
  ``X-AIMarket-Idempotency: replayed`` — the provider does not run, nothing is charged;
* the same key with a different body is ``422 idempotency_key_reused``;
* the same key while the first request still runs is ``409 idempotency_in_progress``; a
  request that never finished (the process died) is ``409 idempotency_outcome_unknown`` after
  15 minutes: the ledger (``GET /ai-market/v2/account``) says whether it was charged, and a
  new key starts a new call. Never "run it again and hope".

Answers that come before any money could move (401, 403, 404, 413, 415, 422, 429, 503) are
not kept, so a retry with a fixed credential or after a rate limit is a fresh call. Everything
else is kept, including a 5xx: after a server error the outcome is uncertain, and replaying
the error is safe where re-running is not. Other rails answer ``X-AIMarket-Idempotency:
not-applicable`` and run as before.

This is a layer around the route, not a change to it: the invoke handler and its many exits
stay as they are, and whatever it answers is what is kept.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from typing import Any

from aimarket_hub.db_backend import returning_one

logger = logging.getLogger(__name__)

HEADER = "idempotency-key"
STATUS_HEADER = b"x-aimarket-idempotency"
KEY_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
KEEP_S = 24 * 3600.0
RUNNING_UNKNOWN_AFTER_S = 15 * 60.0
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_STORED_BYTES = 4 * 1024 * 1024
NOT_KEPT = frozenset({401, 403, 404, 405, 413, 415, 422, 429, 503})
_SKIP_RESPONSE_HEADERS = frozenset({b"content-length", b"date", b"server", b"set-cookie", b"transfer-encoding"})
_INVOKE_PATH = "/ai-market/v2/invoke"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def credential_scope(headers: dict[str, str]) -> str:
    """Whose call this is, as a hash of the secret that pays for it, or "" for other rails."""
    api_key = (headers.get("x-api-key") or "").strip()
    if api_key:
        return "key:" + _sha256(api_key.encode())
    channel = (headers.get("x-payment-channel") or "").strip()
    secret = (headers.get("x-payment-channel-secret") or "").strip()
    if channel and secret:
        return "channel:" + _sha256(f"{channel}\n{secret}".encode())
    return ""


class IdempotencyStore:
    def __init__(self, conn: Any):
        self._conn = conn
        self._last_purge = 0.0

    def _purge(self, now: float) -> None:
        if now - self._last_purge < 300:
            return
        self._last_purge = now
        try:
            self._conn.execute("DELETE FROM invoke_idempotency WHERE created_at < ?", (now - KEEP_S,))
            self._conn.commit()
        except Exception as exc:  # noqa: BLE001 - housekeeping must not fail an invoke
            logger.warning("idempotency: purge failed: %s", exc)

    def claim(self, scope: str, key: str, request_sha256: str, *, now: float | None = None) -> dict[str, Any] | None:
        """None when this request owns the key now; otherwise the row that already holds it."""
        now = time.time() if now is None else now
        self._purge(now)
        # An expired row is gone for this key even before the purge gets to it.
        self._conn.execute("DELETE FROM invoke_idempotency WHERE scope = ? AND idem_key = ? AND created_at < ?",
                           (scope, key, now - KEEP_S))
        won = returning_one(
            self._conn,
            "INSERT INTO invoke_idempotency (scope, idem_key, request_sha256, status, created_at) "
            "VALUES (?, ?, ?, 'running', ?) ON CONFLICT DO NOTHING RETURNING idem_key",
            (scope, key, request_sha256, now),
            commit=True,
        )
        if won is not None:
            return None
        row = self._conn.execute(
            "SELECT request_sha256, status, http_status, response_headers, response_body, created_at "
            "FROM invoke_idempotency WHERE scope = ? AND idem_key = ?", (scope, key),
        ).fetchone()
        return dict(row) if row else {"status": "running", "request_sha256": request_sha256, "created_at": now}

    def finish(self, scope: str, key: str, status: int, headers: list[tuple[bytes, bytes]], body: bytes | None) -> None:
        try:
            if status in NOT_KEPT:
                self._conn.execute("DELETE FROM invoke_idempotency WHERE scope = ? AND idem_key = ? AND status = 'running'",
                                   (scope, key))
            else:
                kept = [[k.decode("latin-1"), v.decode("latin-1")] for k, v in headers
                        if k.lower() not in _SKIP_RESPONSE_HEADERS and k.lower() != STATUS_HEADER]
                self._conn.execute(
                    "UPDATE invoke_idempotency SET status = ?, http_status = ?, response_headers = ?, "
                    "response_body = ?, finished_at = ? WHERE scope = ? AND idem_key = ? AND status = 'running'",
                    ("done" if body is not None else "too_large", int(status), json.dumps(kept),
                     base64.b64encode(body or b"").decode("ascii"), time.time(), scope, key),
                )
            self._conn.commit()
        except Exception as exc:  # noqa: BLE001 - the answer is already on its way
            logger.error("idempotency: recording the answer for %s failed: %s", key, exc)


async def _send_json(send: Any, status: int, body: dict[str, Any], marker: bytes) -> None:
    raw = json.dumps({**body, "protocol_version": "v2"}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()),
        (b"cache-control", b"no-store"), (STATUS_HEADER, marker)]})
    await send({"type": "http.response.body", "body": raw})


class InvokeIdempotency:
    """ASGI layer around ``POST /ai-market/v2/invoke`` (see the module docstring)."""

    def __init__(self, app: Any, conn: Any):
        self.app = app
        self.store = IdempotencyStore(conn)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = str(scope.get("path") or "")
        root = str(scope.get("root_path") or "")
        if root and path.startswith(root):
            path = path[len(root):]        # behind a proxy that mounts the hub under a prefix
        if scope.get("type") != "http" or scope.get("method") != "POST" or path.rstrip("/") != _INVOKE_PATH:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        key = (headers.get(HEADER) or "").strip()
        if not key:
            await self.app(scope, receive, send)
            return
        if not KEY_RE.fullmatch(key):
            await _send_json(send, 400, {"success": False, "error": "idempotency_key_invalid",
                                         "detail": "Idempotency-Key is 1-128 of A-Z a-z 0-9 . _ : -"}, b"rejected")
            return
        owner = credential_scope(headers)
        if not owner:
            await self.app(scope, receive, _marking(send, b"not-applicable"))
            return

        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                await _send_json(send, 413, {"success": False, "error": "request_too_large",
                                             "detail": f"an idempotent invoke body is at most {MAX_REQUEST_BYTES} bytes"},
                                 b"rejected")
                return
            chunks.append(chunk)
            more = bool(message.get("more_body"))
        body = b"".join(chunks)

        held = self.store.claim(owner, key, _sha256(body))
        if held is not None:
            await self._answer_held(send, held, _sha256(body))
            return

        delivered = False

        async def replay_body() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        status = 500
        kept_headers: list[tuple[bytes, bytes]] = []
        out: list[bytes] | None = []
        out_size = 0

        async def capture(message: dict[str, Any]) -> None:
            nonlocal status, kept_headers, out, out_size
            if message["type"] == "http.response.start":
                status = int(message["status"])
                kept_headers = list(message.get("headers") or [])
                message = {**message, "headers": [*kept_headers, (STATUS_HEADER, b"stored")]}
            elif message["type"] == "http.response.body" and out is not None:
                chunk = message.get("body", b"")
                out_size += len(chunk)
                if out_size > MAX_STORED_BYTES:
                    out = None
                else:
                    out.append(chunk)
            await send(message)

        try:
            await self.app(scope, replay_body, capture)
        except BaseException:
            self.store.finish(owner, key, 500, [(b"content-type", b"application/json")],
                              json.dumps({"success": False, "error": "internal_error",
                                          "detail": "the first request with this key failed inside the hub; "
                                                    "check GET /ai-market/v2/account before paying again"}).encode())
            raise
        self.store.finish(owner, key, status, kept_headers, b"".join(out) if out is not None else None)

    async def _answer_held(self, send: Any, held: dict[str, Any], request_sha256: str) -> None:
        if held.get("request_sha256") != request_sha256:
            await _send_json(send, 422, {"success": False, "error": "idempotency_key_reused",
                                         "detail": "this Idempotency-Key was used with a different request body"},
                             b"rejected")
            return
        if held.get("status") == "running":
            age = time.time() - float(held.get("created_at") or 0)
            if age < RUNNING_UNKNOWN_AFTER_S:
                await _send_json(send, 409, {"success": False, "error": "idempotency_in_progress",
                                             "detail": "the first request with this key is still running; retry later"},
                                 b"in-progress")
            else:
                await _send_json(send, 409, {"success": False, "error": "idempotency_outcome_unknown",
                                             "detail": "the first request with this key never finished; "
                                                       "GET /ai-market/v2/account shows whether it was charged, "
                                                       "and a new key starts a new call"},
                                 b"unknown")
            return
        if held.get("status") == "too_large":
            await _send_json(send, 409, {"success": False, "error": "idempotency_answer_not_kept",
                                         "detail": f"the first request with this key was answered HTTP "
                                                   f"{held.get('http_status')}, too large to keep for replay"},
                             b"replayed")
            return
        stored = base64.b64decode(held.get("response_body") or "")
        headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in json.loads(held.get("response_headers") or "[]")]
        await send({"type": "http.response.start", "status": int(held.get("http_status") or 200),
                    "headers": [*headers, (b"content-length", str(len(stored)).encode()), (STATUS_HEADER, b"replayed")]})
        await send({"type": "http.response.body", "body": stored})


def _marking(send: Any, marker: bytes) -> Any:
    async def marked(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            message = {**message, "headers": [*(message.get("headers") or []), (STATUS_HEADER, marker)]}
        await send(message)
    return marked
