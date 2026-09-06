"""
Public marketing endpoints: analytics, lead capture, funnel growth.
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
from pydantic import BaseModel, Field, field_validator

from core.config_merge import load_merged_config
from core.ga4_measurement_id import extract_ga4_measurement_id_from_html, normalize_ga4_measurement_id
from core.paths import config_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketing", tags=["marketing"])

from web.backend.http.client_ip import client_ip

# Per-IP rate limits for the public, unauthenticated write endpoints. /lead in
# particular auto-starts a billable LLM pipeline build (AIFACTORY_LEAD_AUTO_PIPELINE),
# so without this a scripted caller could enqueue unbounded paid builds — the
# global firewall floor (~100/min) is a DoS backstop, not a per-cost control.
_LEAD_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_MARKETING_LEAD_MAX_PER_HOUR", "5"))
_WRITE_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_MARKETING_WRITE_MAX_PER_HOUR", "30"))
_RL_WINDOW_SEC = 3600.0


def _enforce_marketing_rate_limit(request: Request, bucket: str, max_per_hour: int) -> None:
    from web.backend.services.shared_rate_limit import enforce_shared_rate_limit

    ip = client_ip(request)
    enforce_shared_rate_limit(
        f"marketing:{bucket}:{ip}",
        max_hits=max_per_hour,
        window_seconds=_RL_WINDOW_SEC,
        detail="Too many requests. Please try again later.",
    )


from core.paths import marketing_logs_dir

LOG_DIR = marketing_logs_dir()
ANALYTICS_FILE = LOG_DIR / "events.jsonl"
LEADS_FILE = LOG_DIR / "leads.jsonl"

_SAFE_REF = re.compile(r"^[a-zA-Z0-9._\-]{1,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    referral: Optional[str] = Field(None, max_length=64)


class WaitlistBody(BaseModel):
    product_id: str = Field(..., min_length=8, max_length=128)
    email: str = Field(..., min_length=3, max_length=320)
    name: Optional[str] = Field(None, max_length=200)
    meta: Optional[dict[str, Any]] = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        e = v.strip()
        if not _EMAIL_RE.match(e):
            raise ValueError("invalid email")
        return e


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


@router.get("/ga-measurement-id")
async def get_ga_measurement_id(request: Request):
    """Public: GA4 id for the Next.js storefront."""
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
async def post_lead(body: LeadBody, request: Request):
    """Capture a public lead and auto-start pipeline when enabled."""
    _enforce_marketing_rate_limit(request, "lead", _LEAD_MAX_PER_HOUR)
    ref = body.referral
    if ref is not None and not _SAFE_REF.match(ref):
        raise HTTPException(status_code=400, detail="Invalid referral format")

    from web.backend.services.prompt_safety import (
        prepare_untrusted_plain_text,
        rejection_reason_if_blocked,
    )

    idea_raw = body.idea.strip()
    blocked = rejection_reason_if_blocked(idea_raw, context="customer_idea")
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    idea_clean = prepare_untrusted_plain_text(idea_raw, max_len=8000)
    if len(idea_clean) < 8:
        raise HTTPException(status_code=422, detail="Idea is too short.")

    row = {
        "ts": time.time(),
        "email": body.email.strip(),
        "name": (body.name or "").strip(),
        "company": (body.company or "").strip(),
        "idea": idea_clean,
        "source": body.source,
        "referral": ref,
    }
    try:
        _append_jsonl(LEADS_FILE, row)
    except Exception as e:
        logger.warning("lead append failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save lead")

    from web.backend.services.funnel_leads import create_lead_and_maybe_start_pipeline

    return create_lead_and_maybe_start_pipeline(
        email=body.email.strip(),
        idea=idea_clean,
        name=(body.name or "").strip(),
        company=(body.company or "").strip(),
        source=body.source,
        referral=ref,
    )


@router.get("/lead/status/{token}")
async def get_lead_status(token: str):
    from web.backend.services.funnel_leads import public_lead_status

    status = public_lead_status(token.strip())
    if not status:
        raise HTTPException(status_code=404, detail="Lead not found")
    return status


@router.post("/waitlist")
async def post_waitlist(body: WaitlistBody, request: Request):
    """Capture waitlist signups from generated landing pages."""
    _enforce_marketing_rate_limit(request, "waitlist", _WRITE_MAX_PER_HOUR)
    from web.backend.services.funnel_store import append_waitlist_entry

    row = append_waitlist_entry(
        product_id=body.product_id.strip(),
        email=body.email.strip(),
        name=(body.name or "").strip(),
        meta=body.meta,
    )
    _append_jsonl(
        ANALYTICS_FILE,
        {
            "ts": row["ts"],
            "event": "waitlist_submit",
            "product_id": body.product_id.strip(),
            "meta": {"email_domain": body.email.split("@")[-1] if "@" in body.email else ""},
        },
    )
    return {"ok": True, "message": "Thanks — you're on the waitlist."}


@router.get("/trust-metrics")
async def get_trust_metrics():
    from web.backend.services.funnel_analytics import public_trust_metrics

    return public_trust_metrics()


@router.get("/funnel")
async def get_public_funnel(window_hours: int = 168):
    from web.backend.services.funnel_analytics import build_funnel_metrics

    return build_funnel_metrics(window_hours=max(1, min(window_hours, 720)))


@router.get("/waitlist.js")
async def waitlist_embed_js():
    """Embed script for generated landing waitlist forms."""
    from fastapi.responses import PlainTextResponse

    js = """
(function(){
  var pid = document.currentScript && document.currentScript.getAttribute('data-product-id');
  if (!pid) {
    var m = /\\/product\\/([^/?#]+)/.exec(location.pathname);
    pid = m && m[1];
  }
  if (!pid) return;
  document.querySelectorAll('form[data-aifactory-waitlist]').forEach(function(form){
    if (form.dataset.aifactoryBound) return;
    form.dataset.aifactoryBound = '1';
    form.addEventListener('submit', function(ev){
      var emailEl = form.querySelector('[name=email], [type=email]');
      var email = emailEl && emailEl.value ? emailEl.value.trim() : '';
      if (!email) return;
      ev.preventDefault();
      fetch('/api/marketing/waitlist', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({product_id: pid, email: email, name: (form.querySelector('[name=name]')||{}).value||''})
      }).then(function(r){ return r.json(); }).then(function(){
        form.innerHTML = '<p>Thanks — you\\'re on the waitlist.</p>';
      }).catch(function(){ form.innerHTML = '<p>Thanks — received.</p>'; });
    });
  });
})();
""".strip()
    return PlainTextResponse(js, media_type="application/javascript")
