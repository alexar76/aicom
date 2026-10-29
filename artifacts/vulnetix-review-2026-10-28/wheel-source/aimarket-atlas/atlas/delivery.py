"""Watchbox check delivery — the loop that was missing.

`webhook_url` has been accepted, validated and stored since watchboxes existed, and
nothing ever POSTed to it: every watchbox was poll-only and the field was decoration.
This module is the other half — it evaluates each subscribed watchbox on an interval,
appends the result to the append-only monitor log, and delivers it.

DESIGN NOTES THAT MATTER

* The log is written BEFORE delivery is attempted. The evidence is that we checked, not
  that someone received it; if delivery fails forever the check still happened and the
  log still says so (and `checks_never_delivered` surfaces it rather than hiding it).
* Deliveries are HMAC-SHA256 signed with a per-watchbox secret, so the receiver can tell
  our POST from anyone who learned the URL. The secret is returned once, at creation.
* Retries are bounded with exponential backoff and every attempt is recorded. An
  unbounded retry loop against a customer endpoint is an outage amplifier, and silent
  retries make a delivery log useless for proving notice.
* Outbound requests are SSRF-guarded at creation (`https://` only, no loopback), and the
  loop re-validates before each POST because a stored row outlives the code that wrote it,
  then posts to the address it checked, never to the name again.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import hmac
import json
import logging
import os
from typing import Any

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx


def _is_public(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_public(str(ip.ipv4_mapped))
        # NAT64 and 6to4 report is_global=True while carrying an IPv4 address inside.
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("2002::/16"):
            return False
    return ip.is_global and not ip.is_multicast


async def _delivery_target(url: str) -> tuple[str, str, dict[str, str], dict[str, str]]:
    """How to POST this webhook: ``(refusal, target_url, headers, extensions)``; a non-empty
    refusal says why the host must not be contacted.

    The POST goes to the address that passed, not to the name. Posting by name let httpx
    resolve it again, and a name that answers public for the check and 127.0.0.1 a moment
    later (or by the next of five retries) was posted to: DNS rebinding, the class of Vulnetix
    GCVE-110-PYPI-2026-021946. The URL carries the checked IP, ``Host`` the name, and
    ``sni_hostname`` the name too, so the certificate is still verified against it.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host:
        return "webhook_url has no host", "", {}, {}
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(host):
            return f"webhook host is a non-public address ({host})", "", {}, {}
        return "", url, {}, {}
    try:
        # Host and SNI carry the ASCII form; httpx cannot put a Unicode name in a header.
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return "webhook host is not a valid name", "", {}, {}
    port = parts.port or 443
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        return f"webhook host does not resolve ({exc.__class__.__name__})", "", {}, {}
    # The resolver's own order, which puts the family this host can reach first.
    addrs = list(dict.fromkeys(info[4][0] for info in infos))
    bad = [a for a in addrs if not _is_public(a.split("%", 1)[0])]
    if bad or not addrs:
        return f"webhook host resolves to a non-public address ({bad[0] if bad else 'none'})", "", {}, {}
    pinned = f"[{addrs[0]}]" if ":" in addrs[0] else addrs[0]
    host_header = ascii_host
    if parts.port:
        pinned = f"{pinned}:{parts.port}"
        host_header = f"{ascii_host}:{parts.port}"
    target = urlunsplit((parts.scheme, pinned, parts.path, parts.query, ""))
    return "", target, {"Host": host_header}, {"sni_hostname": ascii_host}

from . import monitor_log, watchboxes as watchbox_mod
from .geo import utc_now

logger = logging.getLogger("atlas.delivery")

MAX_ATTEMPTS = 5
# 2s, 8s, 32s, 128s — bounded, and long enough that a receiver restart is survivable.
BACKOFF_BASE_S = 2.0


def sign_body(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the exact bytes we send, hex, prefixed by the scheme.

    Signing the serialized bytes rather than the dict means the receiver verifies what
    arrived, with no need to agree on a canonical JSON form.
    """
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


class DeliveryLoop:
    """Periodically evaluate subscribed watchboxes, log, and deliver."""

    def __init__(
        self,
        *,
        evaluate: Any,
        signer: Any,
        interval_s: float | None = None,
        store: monitor_log.MonitorLog | None = None,
        client_factory: Any = None,
    ) -> None:
        # `evaluate(watchbox_row) -> dict` is injected rather than imported so the loop is
        # testable without a live fleet, and so the check logic stays in one place.
        self._evaluate = evaluate
        self._signer = signer
        self._interval = float(
            interval_s
            if interval_s is not None
            else os.environ.get("ATLAS_WATCHBOX_INTERVAL_S", 300)
        )
        self._store = store
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=15))
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def store(self) -> monitor_log.MonitorLog:
        if self._store is None:
            self._store = monitor_log.get_store()
        return self._store

    async def start(self) -> None:
        if os.environ.get("ATLAS_WATCHBOX_DELIVERY", "1") not in ("1", "true", "TRUE"):
            logger.info("watchbox delivery disabled (ATLAS_WATCHBOX_DELIVERY)")
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown path
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # One bad watchbox must never kill the loop for every other one.
                logger.exception("watchbox delivery tick failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """One pass over every watchbox. Returns how many checks were logged."""
        logged = 0
        # Unsubscribed boxes are skipped here and nowhere else: the row survives so the
        # owner can still read the evidence they already paid for, but we stop adding to
        # it — continuing to check a cancelled subscription would bill work nobody asked
        # for and would make the log claim a watch that was called off.
        for row in watchbox_mod.STORE.list(include_inactive=False):
            try:
                logged += 1 if await self.check_and_deliver(row) else 0
            except Exception:  # noqa: BLE001
                logger.exception("watchbox %s failed", row.get("id"))
        return logged

    async def check_and_deliver(self, row: dict[str, Any]) -> bool:
        # `evaluate` may be sync (tests) or async (the real path goes through the same
        # bbox-densifying station fetch the paid check SKU uses).
        result = self._evaluate(row)
        if inspect.isawaitable(result):
            result = await result
        if not result or not result.get("ok", True):
            return False

        payload = {
            "event": "atlas.watchbox.check",
            "watchbox_id": row.get("id"),
            "label": row.get("label"),
            "evaluated_at": result.get("evaluated_at") or utc_now(),
            "bbox": result.get("bbox") or {},
            "layers": result.get("layers") or [],
            "match_count": int(result.get("match_count") or 0),
            "live_match_count": int(result.get("live_match_count") or 0),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        signature = self._signer.sign_canonical(canonical)

        # Evidence first: the log records that WE checked, independently of whether the
        # receiver was reachable.
        check_id = self.store.append_check(
            watchbox_id=str(row.get("id")),
            evaluated_at=str(payload["evaluated_at"]),
            match_count=int(payload["match_count"]),
            live_match_count=int(payload["live_match_count"]),
            layers=list(payload["layers"]),
            bbox=dict(payload["bbox"]),
            digest=digest,
            signature_b64=signature,
            public_key_b64=self._signer.public_key_b64,
        )

        url = (row.get("webhook_url") or "").strip()
        if not url:
            return True  # logged; nothing subscribed to receive it
        await self._deliver(check_id, url, row, payload, digest, signature)
        return True

    async def _deliver(
        self,
        check_id: int,
        url: str,
        row: dict[str, Any],
        payload: dict[str, Any],
        digest: str,
        signature: str,
    ) -> None:
        # Re-validate: the stored row outlives the code that wrote it, and a row could
        # have been written by an older, laxer validator.
        try:
            url = watchbox_mod._validate_webhook(url)
        except ValueError as exc:
            self.store.record_delivery(
                check_id=check_id, attempt=0, status_code=None,
                error=f"refusing to deliver: {exc}", delivered=False,
            )
            return

        body = json.dumps(
            {**payload, "digest": digest, "signature_b64": signature,
             "public_key_b64": self._signer.public_key_b64},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")

        secret = row.get("webhook_secret") or ""
        headers = {
            "content-type": "application/json",
            "user-agent": "ATLAS-watchbox/1 (+https://atlas.modelmarket.dev)",
            "x-atlas-check-id": str(check_id),
            "x-atlas-digest": digest,
        }
        if secret:
            headers["x-atlas-signature"] = sign_body(secret, body)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._stopping.is_set():
                self.store.record_delivery(
                    check_id=check_id, attempt=attempt, status_code=None,
                    error="shutting down before delivery", delivered=False,
                )
                return
            # The validator checks literals only; a NAME is resolved here, at every attempt,
            # and the POST goes to the address that passed, so a webhook host that points at
            # 127.0.0.1 or the metadata endpoint, now or by a later retry, is refused.
            refusal, target, pin_headers, extensions = await _delivery_target(url)
            if refusal:
                self.store.record_delivery(
                    check_id=check_id, attempt=attempt, status_code=None,
                    error=f"refusing to deliver: {refusal}", delivered=False,
                )
                return
            try:
                async with self._client_factory() as client:
                    if extensions:
                        resp = await client.post(target, content=body, headers={**headers, **pin_headers},
                                                 extensions=extensions)
                    else:
                        resp = await client.post(target, content=body, headers=headers)
                code = int(resp.status_code)
                ok = 200 <= code < 300
                self.store.record_delivery(
                    check_id=check_id, attempt=attempt, status_code=code,
                    error=None if ok else f"HTTP {code}", delivered=ok,
                )
                if ok:
                    return
                # 4xx other than 408/429 is the receiver saying "never send this again";
                # retrying is pointless and looks like an attack from their side.
                if 400 <= code < 500 and code not in (408, 429):
                    return
            except Exception as exc:  # noqa: BLE001
                self.store.record_delivery(
                    check_id=check_id, attempt=attempt, status_code=None,
                    error=f"{type(exc).__name__}: {exc}", delivered=False,
                )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE_S ** attempt)


LOOP: DeliveryLoop | None = None
