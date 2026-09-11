"""
Canonical resolver for the AIMarket federation hub URL.

Three call sites used to each re-implement this env-var lookup with slightly
different precedence and defaults (web/backend services/ai_market_protocol/config.py,
api/ai_market_protocol_v2.py, services/landing_embeds.py), which drifts. This is
the single source of truth.

Precedence (first http(s) value wins):
  [AIMARKET_HUB_URL] → AIMARKET_FEDERATION_HUB_URL → NEXT_PUBLIC_AIMARKET_HUB_URL → default

AIMARKET_HUB_URL is only consulted when ``include_hub_url_var=True`` (the embed/
widget path historically honoured it; the federation-descriptor path did not).
"""

from __future__ import annotations

import os

DEFAULT_FEDERATION_HUB_URL = "https://modelmarket.dev"


def _normalize_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _is_http_url(url: str) -> bool:
    return (url or "").strip().startswith(("http://", "https://"))


def resolve_federation_hub_url(
    *, default: str = "", include_hub_url_var: bool = False, fallback_on_invalid: bool = True
) -> str:
    """Return the configured federation hub base URL (no trailing slash).

    Args:
        default: value when no env var is set (``""`` means "unconfigured", which
            the federation-descriptor path uses to keep its seed_list empty).
        include_hub_url_var: also consult ``AIMARKET_HUB_URL`` (highest priority).
        fallback_on_invalid: when ``True`` (embed/descriptor paths), a non-http
            env value is ignored and the next key / ``default`` is used. When
            ``False`` (fail-closed callers like the /search,/invoke federation
            proxy), an explicitly-set but non-http value is returned verbatim so
            the caller's own SSRF/safety check rejects it, instead of silently
            forwarding user input to the public default hub.
    """
    keys = (["AIMARKET_HUB_URL"] if include_hub_url_var else []) + [
        "AIMARKET_FEDERATION_HUB_URL",
        "NEXT_PUBLIC_AIMARKET_HUB_URL",
    ]
    for key in keys:
        raw = os.environ.get(key)
        if raw is None:
            continue
        val = _normalize_base(raw)
        if not val:
            continue
        if _is_http_url(val):
            return val
        if not fallback_on_invalid:
            return val  # non-http but explicitly set → hand back for rejection
    return _normalize_base(default)
