"""Is an admitted peer still answering? The honest map (owner, 2026-11-08).

``last_crawl`` is written only by a crawl that reached the peer and verified its catalogue
(crawler.py). A peer whose last such crawl is older than ``AIMARKET_PEER_SILENT_DAYS`` (default 7)
is labelled ``silent`` on /hubs and in /federation/peers: the map stops implying that a hub which
has not answered for a week is part of a live federation. Nobody is removed, unpinned or hidden —
a silent peer that answers again is ``live`` on the next crawl, with nothing for anyone to do.
"""

from __future__ import annotations

import calendar
import os
import time
from typing import Any

DEFAULT_SILENT_DAYS = 7


def silent_days() -> int:
    try:
        value = int((os.getenv("AIMARKET_PEER_SILENT_DAYS") or "").strip() or DEFAULT_SILENT_DAYS)
    except ValueError:
        value = DEFAULT_SILENT_DAYS
    return max(1, value)


def _parse(stamp: str) -> float | None:
    text = str(stamp or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return float(calendar.timegm(time.strptime(text[:19] + ("Z" if fmt.endswith("Z") else ""), fmt)))
        except ValueError:
            continue
    return None


def liveness(last_crawl: Any, *, now: float | None = None) -> dict[str, Any]:
    """``{"liveness": "live" | "silent" | "never_crawled", "silent_days": int | None}``."""
    seen = _parse(str(last_crawl or ""))
    if seen is None:
        return {"liveness": "never_crawled", "silent_days": None}
    age_days = ((time.time() if now is None else now) - seen) / 86400
    if age_days > silent_days():
        return {"liveness": "silent", "silent_days": int(age_days)}
    return {"liveness": "live", "silent_days": None}
