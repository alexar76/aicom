"""CORS allow-origins: production via ``AIFACTORY_CORS_ORIGINS``, dev fallbacks otherwise."""

from __future__ import annotations

import os
from typing import List

# Local dev / docker-compose defaults (same-origin browser → API on another port).
DEFAULT_CORS_ORIGINS: List[str] = [
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:9080",
    "http://127.0.0.1:9080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _dedupe_preserve(seq: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def get_cors_allow_origins() -> List[str]:
    """
    If ``AIFACTORY_CORS_ORIGINS`` is set (comma-separated origins), use that list only.
    Otherwise use dev defaults plus ``NEXT_PUBLIC_SITE_URL`` when set (single-host deploys).
    """
    raw = (os.environ.get("AIFACTORY_CORS_ORIGINS") or "").strip()
    if raw:
        return _dedupe_preserve([x.strip() for x in raw.split(",") if x.strip()])

    out = list(DEFAULT_CORS_ORIGINS)
    site = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if site and site not in out:
        out.append(site)
    return _dedupe_preserve(out)
