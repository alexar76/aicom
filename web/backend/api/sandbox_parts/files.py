"""Serving a sandbox's files and proxying to it: the preview cookie, content sniffing against
the declared type, and the slash fallback.
"""

from __future__ import annotations

import time

import httpx
from fastapi.responses import HTMLResponse

from web.backend.services.sandbox_proxy_headers import sandbox_proxy_slash_variant


def _attach_sandbox_preview_cookie(response: HTMLResponse, sandbox_id: str, sandbox: dict) -> HTMLResponse:
    token = (sandbox.get("preview_token") or "").strip()
    if not token:
        return response
    max_age = max(60, int(sandbox.get("expires_at", time.time() + 3600) - time.time()))
    response.set_cookie(
        key=f"aicom_sbx_{sandbox_id}",
        value=token,
        httponly=True,
        samesite="lax",
        path="/api/sandbox/",
        max_age=max_age,
    )
    return response


# ── Content-based type validation for sandbox file serving (A8) ──────────────
# Extensions are attacker-controlled (generated code names its own files), so the
# served content-type and security treatment are decided from the actual bytes.

# Declared types whose magic bytes we can verify cheaply.


_MAGIC_BYTE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/x-icon", "font/woff", "font/woff2", "application/wasm"}
)


def _sniff_head_bytes(content: str | bytes, n: int = 512) -> bytes:
    """First ``n`` bytes of the file, regardless of how it was read."""
    if isinstance(content, bytes):
        return content[:n]
    return content[:n].encode("utf-8", errors="ignore")


def _bytes_look_like_html(head: bytes) -> bool:
    """Heuristic HTML sniff matching browser behaviour (leading-whitespace tolerant)."""
    lead = head.lstrip()[:128].lower()
    if lead.startswith(b"<!doctype html") or lead.startswith(b"<html"):
        return True
    # Browsers sniff these tags as HTML even without a doctype.
    return any(tag in lead for tag in (b"<head", b"<body", b"<script", b"<iframe", b"<svg"))


def _content_matches_declared_type(media_type: str, head: bytes) -> bool:
    """True when ``head`` carries the magic bytes expected for ``media_type``."""
    if media_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if media_type == "image/gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/x-icon":
        return head.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"))
    if media_type == "font/woff":
        return head.startswith(b"wOFF")
    if media_type == "font/woff2":
        return head.startswith(b"wOF2")
    if media_type == "application/wasm":
        return head.startswith(b"\x00asm")
    return True


def _binary_media_type_from_magic(raw: bytes) -> str:
    """Pick a safe content-type for a binary file from its magic bytes."""
    for mt in ("image/png", "image/jpeg", "image/gif", "image/x-icon", "font/woff", "font/woff2", "application/wasm"):
        if sandbox_api._content_matches_declared_type(mt, raw[:512]):
            return mt
    return "application/octet-stream"


async def _proxy_request_with_slash_fallback(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
) -> httpx.Response:
    """Proxy one request, retrying without a trailing slash when the app 404s.

    A generated SPA that calls ``/api/v1/accounts/`` against a router serving
    ``/api/v1/accounts`` gets a 404 from the product's own SPA catch-all (which
    matches before FastAPI's redirect logic). Retrying the slash-less variant
    keeps the demo alive; QA still reports the mismatch so the pipeline fixes it.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        upstream = await client.request(
            method, url, headers=headers, content=body if body else None
        )
        if upstream.status_code not in (404, 405):
            return upstream
        alt = sandbox_proxy_slash_variant(url)
        if not alt:
            return upstream
        retry = await client.request(
            method, alt, headers=headers, content=body if body else None
        )
        return retry if retry.status_code < 400 else upstream


# Imported last on purpose: this code reads sandbox's state, settings and helpers at
# call time (where tests patch them), and either module may load first.
from .. import sandbox as sandbox_api  # noqa: E402
