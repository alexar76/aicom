"""
Feedback digest
===============
Build a small, privacy-safe digest of recent user feedback and support sessions.
This is used as a loop-back signal into spec_compiler / PM and hardening prompts.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


def _load_recent_feedback(window_hours: int = 168, limit: int = 2000) -> list[dict[str, Any]]:
    from core.paths import feedback_dir

    fb_dir = feedback_dir()
    if not fb_dir.exists():
        return []
    now = time.time()
    cutoff = now - (window_hours * 3600)
    items: list[dict[str, Any]] = []
    for p in sorted(fb_dir.glob("fb-*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if float(row.get("created_at") or 0) < cutoff:
            continue
        items.append(row)
        if len(items) >= limit:
            break
    return items


def build_feedback_digest(window_hours: int = 168) -> dict[str, Any]:
    items = _load_recent_feedback(window_hours=window_hours)
    by_class = Counter(str(x.get("classification") or "unknown") for x in items)
    ratings = [int(x.get("rating") or 0) for x in items if isinstance(x.get("rating"), int)]
    avg_rating = (sum(ratings) / max(1, len(ratings))) if ratings else 0.0

    # Collect top short "signals" (no PII): (classification, tag, journey_step)
    tags = []
    steps = []
    for x in items:
        if isinstance(x.get("tags"), list):
            tags.extend([str(t)[:40] for t in x.get("tags")[:8]])
        if x.get("journey_step"):
            steps.append(str(x.get("journey_step"))[:40])
    top_tags = [t for t, _ in Counter(tags).most_common(10)]
    top_steps = [s for s, _ in Counter(steps).most_common(10)]

    # Sample a few recent "useful" comments for qualitative grounding
    samples = []
    for x in items:
        if float(x.get("usefulness_score") or 0) < 0.6:
            continue
        c = str(x.get("comment") or "").strip()
        if not c:
            continue
        samples.append(
            {
                "product_id": x.get("product_id"),
                "classification": x.get("classification"),
                "rating": x.get("rating"),
                "comment": c[:500],
            }
        )
        if len(samples) >= 8:
            break

    return {
        "source": "feedback_digest_v1",
        "window_hours": window_hours,
        "count": len(items),
        "avg_rating": round(avg_rating, 2),
        "by_classification": dict(by_class),
        "top_tags": top_tags,
        "top_journey_steps": top_steps,
        "high_signal_samples": samples,
        "generated_at": time.time(),
    }

