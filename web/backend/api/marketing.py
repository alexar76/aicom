"""
Public marketing endpoints: lightweight analytics events and lead capture.
Writes append-only JSONL under /app/data/logs/marketing/
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.config_merge import load_merged_config
from core.ga4_measurement_id import extract_ga4_measurement_id_from_html, normalize_ga4_measurement_id
from core.paths import config_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketing", tags=["marketing"])

from core.paths import marketing_logs_dir

LOG_DIR = marketing_logs_dir()
ANALYTICS_FILE = LOG_DIR / "events.jsonl"
LEADS_FILE = LOG_DIR / "leads.jsonl"

_SAFE_REF = re.compile(r"^[a-zA-Z0-9._\-]{1,64}$")


def _published_site_head_html_for_ga(request: Request) -> str:
    """Prefer in-memory AppConfig; if empty, re-read merged YAML from disk (multi-worker / cold edge)."""
    chunks: list[str] = []
    try:
        cfg = getattr(request.app.state, "config", None)
        if cfg is not None:
            chunks.append(str(cfg.get("general.published_site_head_html") or ""))
    except Exception as exc:
        logger.debug("ga head html: app.state read failed: %s", exc)
    primary = "\n".join(chunks).strip()
    if primary:
        return primary
    try:
        merged = load_merged_config(config_path())
        gen = merged.get("general")
        if isinstance(gen, dict):
            return str(gen.get("published_site_head_html") or "")
    except Exception as exc:
        logger.debug("ga head html: disk merge read failed: %s", exc)
    return ""


class AnalyticsEventBody(BaseModel):
    event: str = Field(..., min_length=1, max_length=64)
    path: Optional[str] = Field(None, max_length=512)
    product_id: Optional[str] = Field(None, max_length=128)
    referral: Optional[str] = Field(None, max_length=64)
    meta: Optional[dict[str, Any]] = None


class LeadBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    idea: str = Field(..., min_length=10, max_length=8000)
    name: Optional[str] = Field(None, max_length=200)
    company: Optional[str] = Field(None, max_length=200)
    source: str = Field(default="lead_page", max_length=64)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


@router.get("/ga-measurement-id")
async def get_ga_measurement_id(request: Request):
    """Public: GA4 id for the Next.js storefront.

    Precedence: ``NEXT_PUBLIC_GA_MEASUREMENT_ID`` in the API process env (Docker / same container),
    else first ``G-…`` measurement id parsed from ``general.published_site_head_html`` (Admin head snippet).
    """
    env_id = normalize_ga4_measurement_id(os.environ.get("NEXT_PUBLIC_GA_MEASUREMENT_ID") or "")
    if env_id:
        return {"measurement_id": env_id, "source": "env"}

    html = _published_site_head_html_for_ga(request)
    extracted = extract_ga4_measurement_id_from_html(html)
    if extracted:
        return {"measurement_id": extracted, "source": "published_site_head_html"}
    if html.strip():
        logger.debug(
            "ga-measurement-id: snippet present (%s chars) but no G-… id matched",
            len(html),
        )
    return {"measurement_id": None, "source": None}


@router.post("/analytics")
async def post_analytics_event(body: AnalyticsEventBody):
    """Record a client-side analytics event (page views, CTAs, shares)."""
    ref = body.referral
    if ref is not None and not _SAFE_REF.match(ref):
        raise HTTPException(status_code=400, detail="Invalid referral format")

    row = {
        "ts": time.time(),
        "event": body.event,
        "path": body.path,
        "product_id": body.product_id,
        "referral": ref,
        "meta": body.meta or {},
    }
    try:
        _append_jsonl(ANALYTICS_FILE, row)
    except Exception as e:
        logger.warning("analytics append failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record event")

    return {"ok": True}


@router.post("/lead")
async def post_lead(body: LeadBody):
    """Capture a public lead (product idea). Stored for manual follow-up / pipeline import."""
    row = {
        "ts": time.time(),
        "email": body.email.strip(),
        "name": (body.name or "").strip(),
        "company": (body.company or "").strip(),
        "idea": body.idea.strip(),
        "source": body.source,
    }
    try:
        _append_jsonl(LEADS_FILE, row)
    except Exception as e:
        logger.warning("lead append failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save lead")

    return {"ok": True, "message": "Thank you — we received your idea."}
