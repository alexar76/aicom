"""
Corner badge for sandbox previews while a listed product is in pipeline remediation.
"""

from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from web.backend.services.product_followup import (
    STOREFRONT_ESTABLISHED_LISTING_KEY,
    read_followup,
)
from web.backend.services.storefront_visibility import REPAIR_LISTABLE_STATES

DEFAULT_REWORK_ETA_HOURS = max(1, int(os.getenv("AIFACTORY_SANDBOX_REWORK_ETA_HOURS", "24") or "24"))
REMEDIATION_ETA_KEY = "remediation_eta_at"
REMEDIATION_STARTED_KEY = "remediation_started_at"


def _product_state(product_id: str) -> tuple[str, float]:
    from core.pipeline_state_writer import read_pipeline_state

    state_data = read_pipeline_state()
    products = state_data.get("products") if isinstance(state_data, dict) else None
    product = products.get(product_id) if isinstance(products, dict) else None
    if not isinstance(product, dict):
        return "", time.time()
    state = str(product.get("state") or "").upper()
    updated = float(product.get("updated_at") or product.get("created_at") or time.time())
    return state, updated


def ensure_remediation_eta_recorded(product_id: str, *, state_upper: str) -> None:
    """Persist expected return time when a product enters remediation (once per cycle)."""
    if state_upper not in REPAIR_LISTABLE_STATES:
        return
    cur = read_followup(product_id) or {}
    now = time.time()
    changed = False
    if not cur.get(REMEDIATION_STARTED_KEY):
        cur[REMEDIATION_STARTED_KEY] = now
        changed = True
    if not cur.get(REMEDIATION_ETA_KEY):
        cur[REMEDIATION_ETA_KEY] = now + DEFAULT_REWORK_ETA_HOURS * 3600
        changed = True
    if changed:
        from web.backend.services.product_followup import write_followup

        write_followup(product_id, cur)


def _format_eta_local(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%d.%m.%Y %H:%M %Z")


def remediation_badge_active(product_id: str) -> bool:
    raw = read_followup(product_id) or {}
    if raw.get(STOREFRONT_ESTABLISHED_LISTING_KEY) and raw.get("followup") == "planned":
        return True
    if raw.get(REMEDIATION_STARTED_KEY) or raw.get(REMEDIATION_ETA_KEY):
        return True
    state, _ = _product_state(product_id)
    if state in REPAIR_LISTABLE_STATES:
        return True
    return False


def get_remediation_badge_context(product_id: str) -> Optional[dict[str, Any]]:
    if not remediation_badge_active(product_id):
        return None

    raw = read_followup(product_id) or {}
    ensure_remediation_eta_recorded(product_id, state_upper="DEV_FIXING")
    raw = read_followup(product_id) or {}

    eta_ts = float(raw.get(REMEDIATION_ETA_KEY) or 0)
    if eta_ts <= 0:
        base = float(raw.get(REMEDIATION_STARTED_KEY) or raw.get("followup_updated_at") or time.time())
        eta_ts = base + DEFAULT_REWORK_ETA_HOURS * 3600

    return {
        "state": "ДОРАБОТКА",
        "eta_ts": eta_ts,
        "eta_label": _format_eta_local(eta_ts),
        "repair_round": raw.get("quality_repair_round"),
    }


def remediation_badge_markup(product_id: str) -> str:
    ctx = get_remediation_badge_context(product_id)
    if not ctx:
        return ""
    eta_label = html.escape(str(ctx["eta_label"]))
    state = html.escape(str(ctx.get("state") or ""))
    return (
        '<div id="aicom-rework-badge" role="status" aria-live="polite" style="'
        "position:fixed;bottom:1rem;right:1rem;z-index:2147483646;"
        "max-width:min(320px,calc(100vw - 2rem));padding:0.75rem 1rem;border-radius:12px;"
        "background:linear-gradient(135deg,rgba(234,179,8,0.95),rgba(245,158,11,0.92));"
        "color:#1a1200;font-family:system-ui,sans-serif;font-size:0.8125rem;"
        'box-shadow:0 8px 32px rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.35);'
        'pointer-events:none;line-height:1.35;">'
        '<div style="font-weight:700;font-size:0.875rem;margin-bottom:0.25rem">'
        "Отправлен на доработку</div>"
        f'<div style="opacity:0.9">Ожидаемый возврат: <strong>{eta_label}</strong></div>'
        f'<div style="opacity:0.75;font-size:0.7rem;margin-top:0.35rem">'
        f"Статус: {state} · превью доступно</div></div>"
    )


def inject_remediation_badge(html_content: str, product_id: str) -> str:
    badge = remediation_badge_markup(product_id)
    if not badge:
        return html_content
    lower = html_content.lower()
    if "aicom-rework-badge" in lower:
        return html_content
    if "</body>" in lower:
        return re.sub(r"</body>", badge + "\n</body>", html_content, count=1, flags=re.IGNORECASE)
    return html_content + badge
