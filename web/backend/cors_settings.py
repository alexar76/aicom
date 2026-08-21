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

# Always merged — static ecosystem landing on GitHub Pages / modeldev polls public metrics.
PUBLIC_LANDING_CORS_ORIGINS: List[str] = [
    "https://alexar76.github.io",
    "https://modeldev.modelmarket.dev",
    "https://magic-ai-factory.com",
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
    If ``AIFACTORY_CORS_ORIGINS`` is set (comma-separated origins), start from that list.
    Otherwise use dev defaults plus ``NEXT_PUBLIC_SITE_URL`` when set (single-host deploys).

    ``PUBLIC_LANDING_CORS_ORIGINS`` is always appended so Pages / modeldev can fetch
    ``/api/public/ecosystem-status`` without waiting for a host env edit.
    """
    raw = (os.environ.get("AIFACTORY_CORS_ORIGINS") or "").strip()
    if raw:
        out = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        out = list(DEFAULT_CORS_ORIGINS)
        site = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "").strip().rstrip("/")
        if site:
            out.append(site)
    out.extend(PUBLIC_LANDING_CORS_ORIGINS)
    return _dedupe_preserve(out)
