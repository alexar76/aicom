"""The RouteVerdict check pipeline — observation only, NEVER pays the target.

For a resource_url the checker:
  1. probes it unauthenticated (GET, then POST {} if the first answer was
     not a 402) and records status, latency, and the raw challenge;
  2. parses the 402 challenge (parsers.py);
  3. scores the Bazaar discovery schema quality (schema_quality.py);
  4. looks the resource up in the CDP Bazaar and PayAI indexes (catalog.py);
  5. computes a trust score with ITEMIZED deductions and a diff against the
     previous stored check of the same URL (store.py);
  6. emits TRUSTED / CAUTION / AVOID with a 0-100 trust score.

Score convention: 100 = fully trusted, deductions are named penalties.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx

from .catalog import cdp_bazaar_presence, payai_presence
from .parsers import format_price, parse_challenge
from .schema_quality import evaluate_schema_quality
from .store import CheckStore

USER_AGENT = "route-verdict/1.0 (x402 trust probe)"

# --- SSRF guard + probe fetch hardening (security audit 2026-10-25) -----------
# The probe fetches a caller-supplied URL from inside our network, so it
# follows the same discipline as StallRow's page fetcher: only http(s),
# the host must resolve exclusively to public addresses, every redirect
# hop is re-checked BEFORE it is fetched (client-level redirect
# following would contact the target first), and the body is read under
# a hard size cap (a 402 challenge is a few KB; an uncapped read lets a
# hostile target OOM the service with one giant response).
_MAX_PROBE_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 5


def ssrf_check(url: str) -> None:
    """Reject non-http(s) URLs and any host resolving to a private,
    loopback, link-local, reserved, or multicast address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"host does not resolve: {host}") from e
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"URL host resolves to a non-public address ({ip})")


class _ProbeRefused(Exception):
    """The probe refused the target (SSRF guard, redirect overflow, or
    an oversized body). Surfaced as a probe error, never a fetch."""


async def _read_capped(resp: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in resp.aiter_bytes():
        total += len(chunk)
        if total > _MAX_PROBE_BYTES:
            raise _ProbeRefused(
                f"target body exceeds the {_MAX_PROBE_BYTES // (1024 * 1024)} MiB probe cap"
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_once(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    timeout: float,
    content: bytes | None = None,
) -> tuple[int, httpx.Headers, bytes]:
    """One probe request with manual redirect following — every hop is
    SSRF-checked before it is fetched."""
    current = url
    for hop in range(_MAX_REDIRECTS + 1):
        await asyncio.to_thread(ssrf_check, current)  # blocking DNS — off the loop
        async with client.stream(
            method,
            current,
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            content=content,
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return resp.status_code, resp.headers, b""
                if hop == _MAX_REDIRECTS:
                    raise _ProbeRefused("target redirected too many times")
                current = urljoin(current, location)
                if resp.status_code == 303:
                    method = "GET"
                    content = None
                continue
            return resp.status_code, resp.headers, await _read_capped(resp)
    raise _ProbeRefused("target redirected too many times")  # pragma: no cover


_shared: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    """One process-wide client for the probe and both catalog lookups.
    Building a fresh AsyncClient per check (the original shape) threw
    away the connection pool every call, so each check paid new
    DNS + TCP + TLS handshakes to the target AND to the CDP and PayAI
    hosts. The shared client keeps connections alive between checks.
    Timeouts are unchanged: _probe passes its explicit per-request
    timeout on every call, and the catalog lookups still fall back to
    the httpx client default (5 s), exactly as on the per-request
    client. Callers must NOT close it. (Same fix as token-verdict's
    shared DEXScreener client, ff05d1c.)"""
    global _shared
    if _shared is None or _shared.is_closed:
        _shared = httpx.AsyncClient(
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=90.0,
            ),
        )
    return _shared


def _reason(name: str, deduction: int, detail: str) -> dict:
    return {"name": name, "deduction": deduction, "detail": detail}


def _comparables(result: dict) -> dict[str, str]:
    terms = result["terms"]
    catalog = result["catalog"]
    return {
        "liveness": "alive" if result["liveness"]["alive"] else "unreachable",
        "price": terms["amount_units"] or "unknown",
        "asset": terms["asset"] or "unknown",
        "pay_to": terms["pay_to"] or "unknown",
        "network": terms["network"] or "unknown",
        "schema_score": (
            str(result["schema_quality"]["score"])
            if result["schema_quality"]["score"] is not None
            else "unknown"
        ),
        "cdp_listing": catalog["cdp_bazaar"]["status"],
        "payai_listing": catalog["payai"]["status"],
    }


def compute_diff(prior: dict | None, current: dict) -> dict:
    """What changed about this resource since its previous check."""
    if prior is None:
        return {
            "prior_check": False,
            "prior_checked_at": None,
            "changes": [],
            "summary": "no prior check on record",
        }
    before, after = _comparables(prior), _comparables(current)
    changes = []
    for field in before:
        if before[field] != after[field]:
            changes.append(
                {
                    "field": field,
                    "before": before[field],
                    "after": after[field],
                    "detail": f"{field} changed: {before[field]} -> {after[field]}.",
                }
            )
    prior_at = prior.get("checked_at")
    if not changes:
        return {
            "prior_check": True,
            "prior_checked_at": prior_at,
            "changes": [],
            "summary": f"no changes since {prior_at}",
        }
    summary = "; ".join(f"{c['field']}: {c['before']} -> {c['after']}" for c in changes)
    return {
        "prior_check": True,
        "prior_checked_at": prior_at,
        "changes": changes,
        "summary": f"{len(changes)} change(s) since {prior_at}: {summary}",
    }


async def _probe(client: httpx.AsyncClient, url: str, timeout: float) -> dict:
    """Unauthenticated probe. Tries GET, then POST {} — whichever answer
    carries a 402 is the one we parse. We never attach a payment header,
    so the target can never charge us."""
    headers = {"user-agent": USER_AGENT}
    error: str | None = None
    chosen: tuple[int, httpx.Headers, bytes] | None = None
    method = "GET"
    latency_ms: int | None = None
    try:
        start = time.monotonic()
        status, resp_headers, body = await _fetch_once(client, "GET", url, headers, timeout)
        latency_ms = int((time.monotonic() - start) * 1000)
        chosen = (status, resp_headers, body)
        if status != 402:
            start = time.monotonic()
            status2, headers2, body2 = await _fetch_once(
                client,
                "POST",
                url,
                {**headers, "content-type": "application/json"},
                timeout,
                content=b"{}",
            )
            latency2 = int((time.monotonic() - start) * 1000)
            if status2 == 402:
                chosen = (status2, headers2, body2)
                method = "POST"
                latency_ms = latency2
    except _ProbeRefused as e:
        error = f"probe refused: {e}"
    except ValueError as e:  # SSRF guard refusal (raised via to_thread)
        error = f"probe refused: {e}"
    except httpx.HTTPError as e:
        error = str(e)
    return {
        "alive": chosen is not None,
        "status": chosen[0] if chosen is not None else None,
        "headers": dict(chosen[1]) if chosen is not None else {},
        "body": chosen[2] if chosen is not None else b"",
        "method": method,
        "latency_ms": latency_ms,
        "error": error,
    }


async def run_check(
    resource_url: str,
    store: CheckStore,
    client: httpx.AsyncClient | None = None,
    check_timeout: float = 10.0,
    now: str | None = None,
) -> dict:
    parsed = urlparse(resource_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("resource_url must be an http(s) URL")

    checked_at = now or datetime.now(timezone.utc).isoformat()
    # Default to the shared process-wide client; a caller-injected
    # client (tests) is used as-is. Either way the client outlives this
    # call — the old per-request client was closed in a finally block,
    # which is precisely the pool-churn this fix removes.
    http = client if client is not None else _shared_client()
    probe = await _probe(http, resource_url, check_timeout)
    parsed_challenge = parse_challenge(probe["status"] or 0, probe["headers"], probe["body"])
    primary = parsed_challenge.primary_accept() if parsed_challenge.valid else None

    terms = {
        "found": bool(primary),
        "price_usdc": format_price(
            primary.amount if primary else None,
            primary.network if primary else None,
            primary.asset if primary else None,
        ),
        "amount_units": primary.amount if primary else None,
        "network": primary.network if primary else None,
        "asset": primary.asset if primary else None,
        "pay_to": primary.pay_to if primary else None,
        "scheme": primary.scheme if primary else None,
        "x402_version": parsed_challenge.x402_version,
    }

    schema_quality = evaluate_schema_quality(
        parsed_challenge.bazaar, parsed_challenge.resource_description
    )

    cdp = await cdp_bazaar_presence(http, terms["pay_to"], resource_url)
    payai = await payai_presence(http, resource_url)

    reasons: list[dict] = []
    score = 100

    def deduct(name: str, points: int, detail: str) -> None:
        nonlocal score
        reasons.append(_reason(name, points, detail))
        score -= points

    if not probe["alive"]:
        deduct(
            "endpoint unreachable",
            100,
            f"No HTTP response at all — probe failed: {probe['error']}.",
        )
    elif not parsed_challenge.valid or not primary:
        deduct(
            "no valid x402 challenge",
            45,
            parsed_challenge.error or "The response is not a parseable x402 payment challenge.",
        )
    else:
        if not schema_quality["extension_present"]:
            deduct(
                "no Bazaar discovery extension",
                15,
                "The 402 challenge carries no extensions.bazaar — agents get no typed contract from this route.",
            )
        elif schema_quality["hollow"]:
            deduct(
                "hollow discovery schema",
                20,
                "The extension's output is example-only ({type, example}) with no typed schema — the shape 87.8% of listings ship.",
            )
        elif schema_quality["score"] is not None and schema_quality["score"] < 100:
            deduct(
                "partial schema quality",
                round((100 - schema_quality["score"]) / 4),
                "Schema-quality sub-score "
                f"{schema_quality['score']}/100: "
                + "; ".join(d["name"] for d in schema_quality["deductions"]),
            )
        if primary.pay_to is None:
            deduct("no payTo in challenge", 15, "The accepts entry names no payTo wallet — money cannot be routed to the seller.")
        if primary.asset is None:
            deduct("no asset in challenge", 5, "The accepts entry names no asset contract.")
        if primary.network is None:
            deduct("no network in challenge", 5, "The accepts entry names no network.")
        if cdp["status"] == "not_listed":
            deduct(
                "not listed in CDP Bazaar",
                10,
                cdp["detail"],
            )
        elif cdp["status"] == "unknown":
            reasons.append(_reason("CDP Bazaar presence unknown", 0, cdp["detail"]))
        if payai["status"] == "not_listed":
            deduct(
                "not listed in PayAI index",
                5,
                payai["detail"],
            )
        elif payai["status"] == "unknown":
            reasons.append(_reason("PayAI presence unknown", 0, payai["detail"]))
        if probe["latency_ms"] is not None and probe["latency_ms"] > 5000:
            deduct("slow response", 5, f"Probe took {probe['latency_ms']} ms — buyers time out.")

    result = {
        "resource_url": resource_url,
        "checked_at": checked_at,
        "verdict": "CAUTION",
        "score": 0.0,
        "reasons": reasons,
        "liveness": {
            "alive": probe["alive"],
            "http_status": probe["status"],
            "latency_ms": probe["latency_ms"],
            "method": probe["method"] if probe["alive"] else None,
            "x402_valid": parsed_challenge.valid,
            "parse_error": parsed_challenge.error,
        },
        "terms": terms,
        "schema_quality": schema_quality,
        "catalog": {"cdp_bazaar": cdp, "payai": payai},
        "diff": {},
    }

    result["diff"] = compute_diff(store.latest(resource_url), result)

    # Prior-driven penalties: the diff is also a finding.
    if result["diff"]["prior_check"]:
        fields = {c["field"]: c for c in result["diff"]["changes"]}
        if "pay_to" in fields:
            deduct(
                "payTo changed since last check",
                15,
                f"The money now goes to a different wallet: {fields['pay_to']['before']} -> {fields['pay_to']['after']}.",
            )
        elif "price" in fields or "asset" in fields:
            deduct(
                "price changed since last check",
                5,
                f"{fields.get('price', fields.get('asset'))['before']} -> "
                f"{fields.get('price', fields.get('asset'))['after']}.",
            )

    score = max(0, score)
    result["score"] = float(score)
    result["verdict"] = (
        "TRUSTED" if score >= 75 else ("CAUTION" if score >= 45 else "AVOID")
    )
    store.save(result)
    return result
