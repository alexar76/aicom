"""
import logging

logger = logging.getLogger(__name__)
Extract GA4 measurement id (``G-…``) from arbitrary HTML / admin head snippets.

Used by the public marketing API so the Next.js storefront can load gtag without a separate env var.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Final
from core.logging_utils import log_suppressed

# GA4 property / data stream ids: G- + alphanumeric (length varies; allow generous upper bound).
_GA4_TAIL: Final[str] = r"[A-Za-z0-9]{4,32}"
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Standard loader URL: …/gtag/js?id=G-…
    re.compile(
        rf"googletagmanager\.com/gtag/js\?[^\"'\s<>]{{0,512}}id=(G-{_GA4_TAIL})",
        re.IGNORECASE,
    ),
    re.compile(
        rf'''gtag\s*\(\s*["']config["']\s*,\s*["'](G-{_GA4_TAIL})["']''',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(rf'"measurement_id"\s*:\s*"(G-{_GA4_TAIL})"', re.IGNORECASE),
    re.compile(rf"'measurement_id'\s*:\s*'(G-{_GA4_TAIL})'", re.IGNORECASE),
    # Broad: first G- token (covers minified bundles, odd spacing).
    re.compile(rf"\b(G-{_GA4_TAIL})\b", re.IGNORECASE),
)


def normalize_ga4_measurement_id(raw: str) -> str | None:
    s = (raw or "").strip().upper()
    if not s.startswith("G-"):
        return None
    tail = s[2:]
    if not tail.isalnum() or not (4 <= len(tail) <= 32):
        return None
    return f"G-{tail}"


def extract_ga4_measurement_id_from_html(blob: str) -> str | None:
    """Return first plausible GA4 measurement id found in ``blob``."""
    if not (blob or "").strip():
        return None
    # Strip BOM / ZWSP; unescape minimal entities so id=G-… inside &quot;…&quot; still matches.
    text = re.sub(r"[\ufeff\u200b\u200c\u200d]", "", blob)
    try:
        text = html_lib.unescape(text)
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (core/ga4_measurement_id.py)", exc_info=_suppressed_exc)

    for pat in _PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1) if m.lastindex else m.group(0)
            if not raw:
                continue
            nid = normalize_ga4_measurement_id(raw)
            if nid:
                return nid
    return None
