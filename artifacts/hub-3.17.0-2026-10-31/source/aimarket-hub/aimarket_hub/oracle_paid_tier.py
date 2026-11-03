"""Operator-scoped paid-tier grants, issued only after the hub funds a call.

Credentials are selected by exact invoke URL, never by a buyer header, a hostname
suffix or a peer's manifest. See docs/oracle-paid-tier.md for configuration.
"""
from __future__ import annotations

import json
import math
import os
import re
from urllib.parse import urlsplit

HEADER = "X-AIMarket-Paid-Tier"
CONFIG_ENV = "AIMARKET_ORACLE_PAID_TIER_CREDENTIALS"


def funded(*, price: float, sandbox: bool, reserved: bool, hold_rail: str,
           x402_accepted: dict | None) -> bool:
    """A paid reservation or verified payment, not a price tag or routing fee."""
    return bool(
        not sandbox and math.isfinite(price) and price > 0
        and ((reserved and hold_rail in {"channel", "credits"})
             or (x402_accepted and x402_accepted.get("ok") is True))
    )


def _endpoint(url: str) -> bool:
    # Exact ASCII URLs avoid normalization, path traversal and authority aliases.
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        return False
    if any(c in url for c in ("\\", "%", "?", "#")):
        return False
    try:
        parts = urlsplit(url)
        return bool(
            parts.scheme in {"http", "https"} and parts.hostname
            and parts.username is None and parts.password is None
            and parts.port != 0 and parts.path.startswith("/")
            and not {".", ".."}.intersection(parts.path.split("/"))
        )
    except ValueError:
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration key")
        result[key] = value
    return result


def headers_for(url: str, *, transport_url: str, admitted: bool) -> dict[str, str]:
    """Fail closed on missing/malformed config; never expose values in errors.

    Gateway rewrites require BOTH exact URLs to explicitly name the same secret.
    HTTP is allowed only with allow_http=true on the actual destination's entry.
    """
    if not admitted or not _endpoint(url) or not _endpoint(transport_url):
        return {}
    try:
        config = json.loads(os.environ.get(CONFIG_ENV) or "{}", object_pairs_hook=_unique_object)
    except (ValueError, TypeError):
        return {}
    if not isinstance(config, dict):
        return {}
    source, target = config.get(url), config.get(transport_url)
    if not isinstance(source, dict) or not isinstance(target, dict):
        return {}
    name = source.get("secret_env")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        return {}
    if target.get("secret_env") != name:
        return {}
    if urlsplit(transport_url).scheme != "https" and target.get("allow_http") is not True:
        return {}
    secret = (os.environ.get(name) or "").strip()
    if not secret or any(ord(c) < 32 or ord(c) >= 127 for c in secret):
        return {}
    return {HEADER: secret}
