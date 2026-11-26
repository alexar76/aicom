#!/usr/bin/env python3
"""Public API: healthz + optional AIMarket economy endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# How long a hub may keep serving this node's catalogue when a re-read fails (RFC 5861), the same
# period the hubs use themselves (AIMARKET_FEDERATED_MAX_UNVERIFIED_S).
_STALE_IF_ERROR_S = 172800

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skopos.api")

_MAX_BODY = 256_000
#: Reports are bigger than chat messages and are compressible, so they get their
#: own ceiling rather than raising the limit for every endpoint.
_MAX_REPORT_BODY = 8 * 1024 * 1024

#: Ingest is the only expensive thing this process does. Capping how much of it
#: can be in flight keeps /healthz answering while a fleet reports in.
_INGEST_SLOTS = threading.Semaphore(2)

#: Per-IP chat budget — stolen Bearer tokens must not burn unbounded LLM spend.
_AGENT_CHAT_WINDOW_SEC = 60.0
_AGENT_CHAT_MAX_PER_WINDOW = 20
_agent_chat_hits: dict[str, list[float]] = {}
_agent_chat_lock = threading.Lock()


def _agent_cors_origins() -> set[str]:
    raw = os.environ.get(
        "SKOPOS_AGENT_CORS_ORIGINS",
        "https://skopos.modelmarket.dev,http://127.0.0.1:8501,http://localhost:8501",
    )
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def _agent_rate_limited(peer_ip: str) -> bool:
    now = time.time()
    key = peer_ip or "unknown"
    with _agent_chat_lock:
        hits = [t for t in _agent_chat_hits.get(key, []) if now - t < _AGENT_CHAT_WINDOW_SEC]
        if len(hits) >= _AGENT_CHAT_MAX_PER_WINDOW:
            _agent_chat_hits[key] = hits
            return True
        hits.append(now)
        _agent_chat_hits[key] = hits
        return False


def _economy_cfg():
    from skopos.economy.config import load_economy_config

    return load_economy_config()


def _skopos_cfg():
    from skopos.config import load_config

    return load_config(os.environ.get("SKOPOS_CONFIG_PATH", "./servers.yaml"))


#: Seconds between retention passes; 0 turns them off.
_RETENTION_EVERY_S = int(os.environ.get("SKOPOS_RETENTION_INTERVAL_S", "3600") or 0)


def _apply_retention() -> tuple[int, int]:
    """Drop line hashes and stored requests past their configured age; returns (hashes, requests).

    The collector's cycle does this after every poll, but a host whose nodes push their
    reports runs no cycle: until 2026-11-02 nothing on metis applied `dedup_retention_days`
    or `http_retention_days`, the hashes grew to 30 M rows, and setting the window did nothing.
    """
    from skopos.db import connect_for_config, prune_dedup, prune_old_requests

    cfg = _skopos_cfg()
    dedup = int(getattr(cfg, "dedup_retention_days", 0) or 0)
    kept = int(getattr(cfg, "http_retention_days", 0) or 0)
    if dedup <= 0 and kept <= 0:
        return 0, 0
    con = connect_for_config(cfg)
    try:
        return prune_dedup(con, dedup), prune_old_requests(con, kept)
    finally:
        con.close()


def _retention_forever() -> None:
    while True:
        try:
            hashes, rows = _apply_retention()
            if hashes or rows:
                logger.info("retention: removed %d line hashes and %d stored requests past their age", hashes, rows)
        except Exception:
            logger.exception("retention pass failed")
        time.sleep(_RETENTION_EVERY_S)


def _check_api_key(handler: BaseHTTPRequestHandler, cfg) -> bool:
    if not cfg.api_key:
        # No key configured used to mean "let everyone in". These endpoints
        # expose fleet posture — which ports are open, which host has no
        # firewall — so an unconfigured deployment must be closed, not open.
        return False
    auth = handler.headers.get("Authorization", "")
    presented = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not presented:
        presented = handler.headers.get("X-API-Key", "").strip()
    # compare_digest: an == comparison on a secret leaks its prefix by timing.
    # It also raises TypeError on a non-ASCII str, and HTTP headers arrive
    # latin-1 decoded — so one high byte would turn a rejection into a 500.
    if not presented or not presented.isascii():
        return False
    return hmac.compare_digest(presented, cfg.api_key)


def _credential_presented(handler: BaseHTTPRequestHandler) -> bool:
    """Did the caller offer anything at all? Not whether it was any good."""
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:].strip():
        return True
    return bool(handler.headers.get("X-API-Key", "").strip())


def _agent_authorized(handler: BaseHTTPRequestHandler) -> bool:
    from skopos.agent_token import verify_token

    auth = handler.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = handler.headers.get("X-Skopos-Agent-Token", "").strip()
    if not token.isascii():
        return False
    return verify_token(token)


class Handler(BaseHTTPRequestHandler):
    #: A peer that opens a socket and says nothing used to block the whole
    #: server, /healthz included. With a timeout it is reaped instead.
    timeout = 20
    protocol_version = "HTTP/1.0"

    def _cors_applies(self) -> bool:
        # The chat widget runs in a browser and needs CORS. Machine-to-machine
        # endpoints do not, and a wildcard origin on them would let any page
        # read their error responses.
        return urlparse(self.path).path.startswith("/agent/")

    def _send_cors(self) -> None:
        if not self._cors_applies():
            return
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        allowed = _agent_cors_origins()
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Authorization, Content-Type, X-Skopos-Agent-Token",
            )
            self.send_header("Access-Control-Max-Age", "600")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_document(self, payload: dict, *, max_age_s: int) -> None:
        """A public discovery document with its validity stated in HTTP (RFC 9111 Cache-Control,
        RFC 5861 stale-if-error, weak ETag per RFC 9110). A hub reads these to decide how long it
        may keep serving this node's catalogue when a re-read fails; every other response stays
        no-store. Both documents are re-signed on every request, so the ETag leaves out the
        signature and the generation time and changes only when what they say changes."""
        content = {k: v for k, v in payload.items() if k not in ("generated_at", "signature")}
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                           default=str).encode("utf-8")).hexdigest()
        names = {part.strip().removeprefix("W/") for part in (self.headers.get("If-None-Match") or "").split(",")}
        not_modified = "*" in names or f'"{digest}"' in names
        body = b"" if not_modified else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(304 if not_modified else 200)
        if not not_modified:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", f'W/"{digest}"')
        self.send_header("Cache-Control", f"public, max-age={max_age_s}, stale-if-error={_STALE_IF_ERROR_S}")
        self._send_cors()
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_body(self, *, limit: int) -> bytes:
        """Read the request body without believing what the headers claim.

        ``int(Content-Length)`` accepts ``-1``, and ``rfile.read(-1)`` then reads
        until EOF — an unauthenticated peer could stream gigabytes into memory.
        So the header is validated, and the read is chunked against a running
        counter that stops at the limit whatever the header said.
        """
        raw = (self.headers.get("Content-Length") or "").strip()
        if not raw.isdigit():
            raise ValueError("Content-Length must be a non-negative integer")
        declared = int(raw)
        if declared > limit:
            raise ValueError("body too large")

        chunks = []
        remaining = declared
        while remaining > 0:
            block = self.rfile.read(min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
            if sum(len(c) for c in chunks) > limit:
                raise ValueError("body too large")
        return b"".join(chunks)

    def _read_json(self) -> dict:
        raw = self._read_body(limit=_MAX_BODY)
        data = json.loads(raw.decode("utf-8") or "{}")
        return data if isinstance(data, dict) else {}

    def _peer_ip(self) -> str | None:
        """The rate-limit key: the caller, never a header the caller picked.

        This used to take the LEFT-most X-Forwarded-For hop. nginx sets that header with
        `$proxy_add_x_forwarded_for`, which APPENDS the real address to whatever the client
        sent, so the left-most value was attacker-chosen — and it is the only key on the
        /agent/chat LLM-spend limiter, whose whole purpose is that a stolen agent token
        cannot burn unbounded paid calls. A fresh header value per request meant a fresh
        empty bucket per request. See skopos/client_ip.py.
        """
        from skopos.client_ip import resolve

        try:
            peer = self.client_address[0]
        except Exception:
            peer = ""
        return resolve(peer, lambda name: self.headers.get(name)) or None

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        cfg = _economy_cfg()

        if path in ("/healthz", "/healthz/"):
            from skopos.public_status import build_status

            status = build_status(config_path=cfg.config_path)
            self._send_json(200 if status.get("ok") else 503, status)
            return

        if path in ("/agent/ping", "/agent/ping/"):
            # Cheap availability probe for the floating widget (no secrets).
            self._send_json(200, {"ok": True, "agent": True})
            return

        if not cfg.enabled:
            self.send_response(404)
            self.end_headers()
            return

        if path == "/.well-known/ai-market.json":
            from skopos.economy.manifest import build_well_known

            self._send_document(build_well_known(cfg), max_age_s=60)
            return

        if path == "/ai-market/v2/manifest":
            from skopos.economy.manifest import build_v2_manifest

            self._send_document(build_v2_manifest(cfg), max_age_s=300)
            return

        if path in ("/security/export", "/security/export/"):
            self._handle_security_export()
            return

        if path == "/ai-market/v2/prices":
            from skopos.economy.manifest import build_prices

            self._send_json(200, build_prices(cfg))
            return

        self.send_response(404)
        self.end_headers()

    def _handle_security_export(self) -> None:
        """Publish the latest security findings, read-only, for the MOMUS-side puller.

        404 rather than 403 when it is switched off: an endpoint that answers "wrong
        token" also answers "this host runs SKOPOS and has findings to give", which is
        the first thing a scanner wants to know.
        """
        from skopos.security.export import HEADER, build_export, export_enabled, token_ok

        if not export_enabled():
            self.send_response(404)
            self.end_headers()
            return
        if not token_ok(self.headers.get(HEADER)):
            self._send_json(403, {"error": "export token required"})
            return

        from skopos.config import load_config
        from skopos.db_connection import connect_for_config

        try:
            cfg = load_config(os.environ.get("SKOPOS_CONFIG_PATH", "./servers.yaml"))
            con = connect_for_config(cfg)
        except Exception:  # noqa: BLE001 - a config or database fault is not a 500 story
            self._send_json(503, {"error": "findings database unavailable"})
            return
        try:
            self._send_json(200, build_export(con))
        finally:
            con.close()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path in ("/agent/chat", "/agent/chat/"):
            self._handle_agent_chat()
            return

        if path in ("/node/v1/report", "/node/v1/report/"):
            self._handle_node_report()
            return

        if path in ("/node/v1/enroll", "/node/v1/enroll/"):
            self._handle_node_enroll()
            return

        cfg = _economy_cfg()

        if not cfg.enabled or path not in ("/aimarket/invoke", "/aimarket/invoke/"):
            self.send_response(404)
            self.end_headers()
            return

        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError):
            body = {}

        if not _check_api_key(self, cfg):
            # No credential at all is not a rejection, it is an unpaid caller: answer 402
            # with the price and the rails (skopos.economy.payments). A presented-but-wrong
            # credential is still 401 — and says nothing more than that.
            if _credential_presented(self):
                self._send_json(401, {"error": "unauthorized"})
                return
            from skopos.economy.payments import payment_required_body

            self._send_json(
                402, payment_required_body(str(body.get("capability_id") or ""), cfg),
            )
            return

        try:
            from skopos.economy.invoke import InvokeError, dispatch_invoke

            payload = dispatch_invoke(body, cfg=cfg)
            self._send_json(200, payload)
        except InvokeError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
        except Exception:
            logger.exception("invoke failed")
            self._send_json(500, {"error": "internal error"})

    def _handle_node_report(self) -> None:
        """Ingest one signed report from a monitored host.

        Every rejection answers the same way. Telling a caller apart —
        "no such node" from "bad signature" from "revoked" — would let anyone
        with a socket enumerate the fleet one guess at a time.
        """
        from skopos.node_ingest import (
            AuthError,
            IngestError,
            SeqConflict,
            authenticate_request,
            ingest_authenticated,
        )
        from skopos.node_protocol import ProtocolError

        try:
            body = self._read_body(limit=_MAX_REPORT_BODY)
        except ValueError as exc:
            self._send_json(413, {"error": str(exc)})
            return

        # Authenticate before admitting the work. The ingest slots are the
        # scarce resource here; if an unauthenticated request could hold one,
        # anyone with a socket could take them all and stop the fleet reporting.
        cfg = _skopos_cfg()
        try:
            credential, skew = authenticate_request(cfg, self.headers, body)
        except SeqConflict as exc:
            logger.info("node resync: %s", exc)
            self._send_json(409, {"error": "seq", "next_seq": exc.next_seq})
            return
        except AuthError as exc:
            logger.warning("node report rejected: %s", exc)
            self._send_json(401, {"error": "unauthorized"})
            return
        except Exception:
            logger.exception("node authentication failed")
            self._send_json(500, {"error": "internal error"})
            return

        if not _INGEST_SLOTS.acquire(blocking=False):
            self.send_response(503)
            self.send_header("Retry-After", "30")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            try:
                result = ingest_authenticated(
                    cfg, credential, self.headers, body,
                    clock_skew_s=skew, peer_ip=self._peer_ip(),
                )
            except SeqConflict as exc:
                # The signature already verified, so this is a real node that
                # fell behind — usually because an earlier attempt of its own
                # was authenticated and then failed. Hand it the next number so
                # it recovers on the following tick instead of retrying a spent
                # one forever.
                logger.info("node resync: %s", exc)
                self._send_json(409, {"error": "seq", "next_seq": exc.next_seq})
                return
            except AuthError as exc:
                # Logged with the reason, answered without it.
                logger.warning("node report rejected: %s", exc)
                self._send_json(401, {"error": "unauthorized"})
                return
            except (IngestError, ProtocolError) as exc:
                logger.warning("node report invalid: %s", exc)
                self._send_json(400, {"error": str(exc)[:200]})
                return
            except Exception:
                logger.exception("node report failed")
                self._send_json(500, {"error": "internal error"})
                return

            # The response carries counts and a clock, and nothing the agent
            # acts on. A response the node obeys would turn this into a
            # fleet-wide remote execution channel pointing the wrong way.
            self._send_json(200, {
                "ok": True,
                "accepted": result.accepted,
                "duplicate": result.duplicates,
                "rejected": result.rejected,
                "server_time": int(time.time()),
            })
        finally:
            _INGEST_SLOTS.release()

    def _handle_node_enroll(self) -> None:
        from skopos.node_ingest import AuthError, handle_enroll

        try:
            body = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except RecursionError:
            # Deeply nested arrays: neither a ValueError nor a JSONDecodeError,
            # so without this it escapes the handler entirely.
            self._send_json(400, {"error": "invalid json"})
            return

        try:
            payload = handle_enroll(_skopos_cfg(), body, peer_ip=self._peer_ip())
        except AuthError as exc:
            logger.warning("enrollment refused: %s", exc)
            self._send_json(401, {"error": "unauthorized"})
            return
        except Exception:
            logger.exception("enrollment failed")
            self._send_json(500, {"error": "internal error"})
            return
        self._send_json(200, payload)

    def _handle_agent_chat(self) -> None:
        if not _agent_authorized(self):
            self._send_json(401, {"error": "unauthorized"})
            return
        if _agent_rate_limited(self._peer_ip()):
            self._send_json(429, {"error": "rate limited"})
            return
        try:
            body = self._read_json()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return

        messages = body.get("messages")
        if not isinstance(messages, list):
            self._send_json(400, {"error": "messages must be a list"})
            return
        page = body.get("page") if isinstance(body.get("page"), str) else None
        server_name = body.get("server_name") if isinstance(body.get("server_name"), str) else None

        try:
            from skopos.agent.providers import LLMProviderError
            from skopos.agent.service import answer_agent_message

            result = answer_agent_message(messages, server_name=server_name, page=page)
            self._send_json(
                200,
                {
                    "reply": result.reply,
                    "provider": result.provider,
                    "model": result.model,
                    "actions": list(result.actions),
                },
            )
        except LLMProviderError as exc:
            logger.warning("agent chat unavailable: %s", exc)
            # Never echo upstream provider payloads (keys, body snippets) to clients.
            self._send_json(503, {"error": "assistant temporarily unavailable"})
        except Exception:
            logger.exception("agent chat failed")
            self._send_json(500, {"error": "internal error"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    cfg = _economy_cfg()
    if cfg.enabled and cfg.auto_register:
        from skopos.economy.consumer import try_auto_register

        try_auto_register(cfg)

    port = int(os.environ.get("SKOPOS_HEALTHZ_PORT", "8502"))
    logger.info(
        "SKOPOS API on :%s (healthz + agent chat + node ingest%s)",
        port,
        " + AIMarket economy" if cfg.enabled else "",
    )
    # Threading, so one slow or silent peer cannot hold the whole API — and
    # daemon threads so a hung request never blocks shutdown.
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    if _RETENTION_EVERY_S > 0:
        threading.Thread(target=_retention_forever, name="retention", daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
