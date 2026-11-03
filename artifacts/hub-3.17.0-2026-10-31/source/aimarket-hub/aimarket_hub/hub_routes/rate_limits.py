"""Per-caller rate limits for invoke and sign-up, sized per declared worker."""

from __future__ import annotations

import contextlib
import ipaddress
import os
import time
from types import SimpleNamespace

from aimarket_hub import security_posture
from aimarket_hub.channels import _is_production_mode


def register() -> SimpleNamespace:
    """Build the invoke and sign-up rate limiters."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _trim_rate_buckets,
        logger,
    )

    # Per-consumer /invoke rate limit (sliding window). Without it an anonymous
    # caller could hammer a provider — forcing failures to grief its stake and
    # burning its upstream capacity. Mirrors the channels ledger _check_rate.
    #
    # LIMITATION — this window lives in PROCESS memory, not in the ledger DB:
    #   * it resets to empty on every restart/redeploy, so a caller can reset its
    #     own bucket by waiting out a deploy (bounded, acceptable);
    #   * it is NOT shared between processes. With N uvicorn workers behind one
    #     socket, N independent windows exist, so the effective ceiling would be
    #     N x AIMARKET_INVOKE_RATE_PER_MIN — i.e. a multi-worker deploy would be
    #     silently N times more permissive than the operator configured.
    # The second failure mode is closed WHENEVER THE WORKER COUNT IS DECLARED: the
    # configured budget is DIVIDED across it, so the aggregate ceiling matches
    # AIMARKET_INVOKE_RATE_PER_MIN no matter how many workers run. Declare the count
    # with AIMARKET_WORKERS (or the WEB_CONCURRENCY / UVICORN_WORKERS conventions used
    # by the container entrypoints).
    #   RESIDUAL, stated precisely because the fix does NOT cover it: an operator who
    #   scales to N workers WITHOUT declaring the count (or with a malformed value)
    #   still gets the full budget in each worker, i.e. N x the configured aggregate.
    #   That direction is permissive, not restrictive. Nothing in-process can observe
    #   its sibling workers, so the only real fix is a shared counter — which belongs
    #   in the ledger DB alongside channels._check_rate (cross-package note). What we
    #   do here is refuse to be silent about it: production logs a warning at startup.
    _invoke_rate: dict[str, list[float]] = {}
    _INVOKE_RATE_WINDOW_S = 60.0
    # Hard cap on tracked keys: the dict is keyed on client IP, so an attacker rotating
    # source addresses must not be able to grow it without bound (memory DoS). Expired
    # buckets go first; if every bucket is still live we drop the least-recently-active
    # ones, which are the closest to expiring anyway.
    _INVOKE_RATE_MAX_KEYS = 20_000

    def _declared_workers() -> tuple[int, bool]:
        for var in ("AIMARKET_WORKERS", "WEB_CONCURRENCY", "UVICORN_WORKERS"):
            raw = os.environ.get(var, "").strip()
            if not raw:
                continue
            try:
                return max(1, int(raw)), True
            except ValueError:
                logger.warning(
                    "%s=%r is not an integer — assuming 1 worker for the invoke "
                    "rate limiter (per-worker budget stays at the configured value)",
                    var, raw,
                )
                return 1, False
        return 1, False

    _INVOKE_RATE_CONFIGURED = int(os.environ.get("AIMARKET_INVOKE_RATE_PER_MIN", "60"))
    _INVOKE_RATE_WORKERS, _INVOKE_RATE_WORKERS_DECLARED = _declared_workers()
    if _INVOKE_RATE_CONFIGURED <= 0:
        _INVOKE_RATE_MAX = _INVOKE_RATE_CONFIGURED  # <= 0 keeps the documented "disabled"
    else:
        # Integer division floors, so round up to keep at least one request per
        # worker per window (a 1-per-minute budget across 4 workers must not become 0).
        _INVOKE_RATE_MAX = max(1, -(-_INVOKE_RATE_CONFIGURED // _INVOKE_RATE_WORKERS))
    if _INVOKE_RATE_WORKERS > 1:
        logger.info(
            "invoke rate limit: %d/min configured across %d declared worker(s) "
            "→ %d/min per worker (in-memory window)",
            _INVOKE_RATE_CONFIGURED, _INVOKE_RATE_WORKERS, _INVOKE_RATE_MAX,
        )
    elif (
        _INVOKE_RATE_MAX > 0
        and _is_production_mode()
        and not _INVOKE_RATE_WORKERS_DECLARED
    ):
        # The undeclared-worker residual above is invisible from inside the process,
        # so make it loud instead of pretending it does not exist.
        logger.warning(
            "invoke rate limit: no worker count declared (AIMARKET_WORKERS / "
            "WEB_CONCURRENCY / UVICORN_WORKERS) — each worker enforces the full "
            "%d/min, so an N-worker deploy admits N x that in aggregate",
            _INVOKE_RATE_CONFIGURED,
        )

    def _check_invoke_rate(consumer: str) -> bool:
        """Return True if within the per-consumer invoke rate limit, else False."""
        if _INVOKE_RATE_MAX <= 0:
            return True
        now = time.time()
        window = now - _INVOKE_RATE_WINDOW_S
        bucket = [t for t in _invoke_rate.get(consumer, []) if t > window]
        if len(bucket) >= _INVOKE_RATE_MAX:
            _invoke_rate[consumer] = bucket
            return False
        bucket.append(now)
        _invoke_rate[consumer] = bucket
        if len(_invoke_rate) > _INVOKE_RATE_MAX_KEYS:
            _trim_rate_buckets(
                _invoke_rate, window, _INVOKE_RATE_MAX_KEYS, keep=consumer,
            )
        return True

    _signup_rate: dict[str, list[float]] = {}

    def _signup_subnet(client_ip: str) -> str:
        """The /24 of an IPv4 address, the /48 of an IPv6 one, or "" if unparsable."""
        try:
            parsed = ipaddress.ip_address(str(client_ip or "").strip())
        except ValueError:
            return ""
        network = ipaddress.ip_network(f"{parsed}/{24 if parsed.version == 4 else 48}", strict=False)
        return f"net:{network}"

    def _signup_allowed(client_ip: str) -> bool:
        """Cap self-serve account creation per address.

        An open signup that mints rows for free is a write amplifier, and the free grant
        makes each row worth a few cents of invoke — so the door is open but narrow. The
        operator can widen or shut it with AIMARKET_CREDITS_SIGNUPS_PER_HOUR / _OPEN_SIGNUP.
        """
        try:
            limit = int(os.getenv("AIMARKET_CREDITS_SIGNUPS_PER_HOUR", "5"))
        except (TypeError, ValueError):
            limit = 5
        if limit <= 0:
            return False
        now = time.time()
        window = now - 3600.0
        # One address is a weak identity: a residential-proxy pool hands out a
        # fresh one per request. The /24 (or /48) it came from is harder to
        # multiply, so the subnet gets a bucket too, wider than the single host.
        keys = [client_ip, _signup_subnet(client_ip)]
        limits = [limit, max(limit, limit * 4)]
        with contextlib.suppress(ValueError):
            if ipaddress.ip_address(str(client_ip or "").strip()).version == 6:
                # One IPv6 host is handed a whole /64 and a free tunnel a routed /48, so the
                # address is no identity at all and the /48 is what one actor holds: it gets
                # the single-address ceiling, the /64 the same.
                net64 = ipaddress.ip_network(f"{client_ip.strip()}/64", strict=False)
                keys = [f"net:{net64}", _signup_subnet(client_ip)]
                limits = [limit, limit]
        fresh: dict[str, list[float]] = {}
        for key, ceiling in zip(keys, limits):
            if not key:
                continue
            bucket = [t for t in _signup_rate.get(key, []) if t > window]
            if len(bucket) >= ceiling:
                _signup_rate[key] = bucket
                security_posture.record(security_posture.SIGNUP_REFUSED)
                return False
            fresh[key] = bucket
        for key, bucket in fresh.items():
            bucket.append(now)
            _signup_rate[key] = bucket
        if len(_signup_rate) > 2048:
            _trim_rate_buckets(_signup_rate, window, 2048, keep=client_ip)
        return True

    return SimpleNamespace(
        _INVOKE_RATE_WORKERS=_INVOKE_RATE_WORKERS,
        _check_invoke_rate=_check_invoke_rate,
        _signup_allowed=_signup_allowed,
    )
