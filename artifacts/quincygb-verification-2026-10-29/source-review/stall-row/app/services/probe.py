"""One-link probe: the free single-route form of Fleet Check.

POST /v1/probe takes ONE full route URL (or one stall origin) and
answers the question the public checker page asks — is this route
answering with a healthy 402 challenge right now? — using Fleet
Check's own machinery end to end: the same definition validation
(SSRF guard included), the same unpaid sweep, the same _classify
defect classes. There is deliberately no second classifier here;
a verdict this page gives is the verdict a paid Fleet Check sweep
would give for the same route.

Free and unpriced by design: this module has no price, is absent
from config.PRICE_UNITS and every discovery surface, and the
priced route count does not move. The abuse brakes are a per-IP
in-memory rate limit (mirroring the nudge inbox's limiter shape)
and the SSRF guard Fleet Check already runs; a restart resets
the window.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from urllib.parse import urlsplit

import httpx

from . import fleetcheck as fleetcheck_svc

# One probe may expand an origin to several priced routes and each
# route is probed with retries — cap the whole thing so a slow
# target cannot hold a checker request open.
PROBE_TIMEOUT_S = 20.0


# --- rate limiting -------------------------------------------------------------
# Per-client-IP sliding window, mirroring nudge._RateLimiter:
# in-process, thread-guarded, env-tunable.

def rate_limit_per_min() -> int:
    try:
        return max(1, int(os.environ.get("STALLROW_PROBE_RATE_PER_MIN", "10")))
    except ValueError:
        return 10


class _RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if t > now - 60]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


RATE_LIMITER = _RateLimiter()


# --- the probe -------------------------------------------------------------------

def _is_bare_origin(url: str) -> bool:
    parts = urlsplit(url)
    return parts.path in ("", "/") and not parts.query


async def probe_one(client: httpx.AsyncClient, url: str) -> dict:
    """Probe one URL with Fleet Check's sweep and fold the result
    into the checker's single-answer shape. A full route URL is
    probed as a one-resource fleet; a bare origin is expanded from
    its own /.well-known/x402 (priced resources only), exactly
    like a sweep — the top-level answer is then the worst row's
    verdict, with every row carried under `resources`.

    Raises ValueError for targets the SSRF guard refuses (the
    handler's 422, before anything is probed)."""
    url = url.strip()
    if _is_bare_origin(url):
        definition = await fleetcheck_svc.validate_definition([], [url])
    else:
        definition = await fleetcheck_svc.validate_definition([url], [])
    try:
        result = await asyncio.wait_for(
            fleetcheck_svc.sweep(client, definition),
            timeout=PROBE_TIMEOUT_S,
        )
    except (asyncio.TimeoutError, TimeoutError):
        return {
            "url": url,
            "status": "defect",
            "observed_status": None,
            "defect_class": "unreachable",
            "detail": f"probe timed out after {int(PROBE_TIMEOUT_S)}s",
            "checked_at": fleetcheck_svc._now_iso(),
            "verdict": "DOWN",
            "defects": [
                {
                    "code": "unreachable",
                    "detail": f"probe timed out after {int(PROBE_TIMEOUT_S)}s",
                }
            ],
            "accepts": [],
        }
    rows = result["resources"]
    if not rows:
        return {
            "url": url,
            "status": "defect",
            "observed_status": None,
            "defect_class": "no_priced_routes",
            "detail": (
                "the origin publishes no priced resources in its "
                "/.well-known/x402, so there is no route to probe — "
                "paste a full route URL instead"
            ),
            "checked_at": result["checked_at"],
            "verdict": "DOWN",
            "defects": [],
            "accepts": [],
            "resources": [],
        }
    rank = {"OK": 0, "DEGRADED": 1, "DOWN": 2}
    worst = max(rows, key=lambda r: rank.get(r["verdict"], 1))
    first_defect = worst["defects"][0] if worst["defects"] else None
    out = {
        "url": url,
        "status": "ok" if all(r["verdict"] == "OK" for r in rows) else "defect",
        "observed_status": worst["http_status"],
        "defect_class": first_defect["code"] if first_defect else None,
        "detail": (
            first_defect["detail"]
            if first_defect
            else "answers 402 with a parseable x402 challenge"
        ),
        "checked_at": result["checked_at"],
        "verdict": worst["verdict"],
        "defects": worst["defects"],
        "accepts": worst["accepts"],
    }
    if len(rows) > 1:
        out["resources"] = rows
        out["summary"] = result["summary"]
        if out["status"] == "ok":
            out["detail"] = (
                f"all {len(rows)} priced routes answer 402 with "
                "parseable x402 challenges"
            )
    return out
