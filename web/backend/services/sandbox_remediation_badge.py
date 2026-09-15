"""
Corner badge for sandbox previews while a listed product is in pipeline remediation.
"""

from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from web.backend.services.product_followup import (
    STOREFRONT_ESTABLISHED_LISTING_KEY,
    read_followup,
)
from web.backend.services.storefront_visibility import REPAIR_LISTABLE_STATES

DEFAULT_REWORK_ETA_HOURS = max(1, int(os.getenv("AIFACTORY_SANDBOX_REWORK_ETA_HOURS", "24") or "24"))
REMEDIATION_ETA_KEY = "remediation_eta_at"
REMEDIATION_STARTED_KEY = "remediation_started_at"

BadgeLocale = str

_BADGE_COPY: dict[BadgeLocale, dict[str, str]] = {
    "en": {
        "title": "Sent for rework",
        "eta": "Expected return: {eta}",
        "status": "Status: {state} · preview available",
        "state": "REWORK",
    },
    "ru": {
        "title": "Отправлен на доработку",
        "eta": "Ожидаемый возврат: {eta}",
        "status": "Статус: {state} · превью доступно",
        "state": "ДОРАБОТКА",
    },
    "es": {
        "title": "Enviado a rework",
        "eta": "Regreso esperado: {eta}",
        "status": "Estado: {state} · vista previa disponible",
        "state": "REWORK",
    },
}


def normalize_remediation_badge_locale(raw: str | None) -> BadgeLocale:
    if not raw:
        return "en"
    value = raw.strip().lower()
    if value in ("ru", "es", "en"):
        return value
    if value.startswith("ru"):
        return "ru"
    if value.startswith("es"):
        return "es"
    return "en"


def resolve_remediation_badge_locale(request: Any | None) -> BadgeLocale:
    """Resolve badge language from ?lang= / ?locale= or Accept-Language (default en)."""
    if request is None:
        return "en"
    query = getattr(request, "query_params", None)
    if query is not None:
        for key in ("lang", "locale"):
            raw = query.get(key)
            if raw:
                return normalize_remediation_badge_locale(str(raw))
    headers = getattr(request, "headers", None)
    if headers is not None:
        accept = headers.get("accept-language") or headers.get("Accept-Language")
        if accept:
            first = str(accept).split(",")[0].strip()
            return normalize_remediation_badge_locale(first)
    return "en"


def _badge_copy(locale: BadgeLocale) -> Mapping[str, str]:
    return _BADGE_COPY.get(locale) or _BADGE_COPY["en"]


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
    eta = cur.get(REMEDIATION_ETA_KEY)
    # Frozen ETA from the first DEV_FIXING cycle showed "16.08" while the
    # product was still in round 5 three days later. Roll forward when past.
    if not eta or float(eta) <= now:
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


def get_remediation_badge_context(product_id: str, *, locale: BadgeLocale = "en") -> Optional[dict[str, Any]]:
    if not remediation_badge_active(product_id):
        return None

    raw = read_followup(product_id) or {}
    ensure_remediation_eta_recorded(product_id, state_upper="DEV_FIXING")
    raw = read_followup(product_id) or {}

    eta_ts = float(raw.get(REMEDIATION_ETA_KEY) or 0)
    if eta_ts <= 0:
        base = float(raw.get(REMEDIATION_STARTED_KEY) or raw.get("followup_updated_at") or time.time())
        eta_ts = base + DEFAULT_REWORK_ETA_HOURS * 3600

    copy = _badge_copy(locale)
    return {
        "state": copy["state"],
        "eta_ts": eta_ts,
        "eta_label": _format_eta_local(eta_ts),
        "repair_round": raw.get("quality_repair_round"),
    }


def remediation_badge_markup(product_id: str, *, locale: BadgeLocale = "en") -> str:
    ctx = get_remediation_badge_context(product_id, locale=locale)
    if not ctx:
        return ""
    copy = _badge_copy(locale)
    eta_label = html.escape(str(ctx["eta_label"]))
    state = html.escape(str(ctx.get("state") or copy["state"]))
    title = html.escape(copy["title"])
    eta_line = (
        html.escape(copy["eta"].format(eta="__ETA__"))
        .replace("__ETA__", f"<strong>{eta_label}</strong>")
    )
    status_line = html.escape(copy["status"].format(state=ctx.get("state") or copy["state"]))
    return (
        '<div id="aicom-rework-badge" role="status" aria-live="polite" style="'
        "position:fixed;bottom:1rem;right:1rem;z-index:2147483646;"
        "max-width:min(320px,calc(100vw - 2rem));padding:0.75rem 1rem;border-radius:12px;"
        "background:linear-gradient(135deg,rgba(234,179,8,0.95),rgba(245,158,11,0.92));"
        "color:#1a1200;font-family:system-ui,sans-serif;font-size:0.8125rem;"
        'box-shadow:0 8px 32px rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.35);'
        'pointer-events:none;line-height:1.35;">'
        f'<div style="font-weight:700;font-size:0.875rem;margin-bottom:0.25rem">{title}</div>'
        f'<div style="opacity:0.9">{eta_line}</div>'
        f'<div style="opacity:0.75;font-size:0.7rem;margin-top:0.35rem">{status_line}</div></div>'
    )


def inject_remediation_badge(
    html_content: str,
    product_id: str,
    *,
    locale: BadgeLocale = "en",
) -> str:
    badge = remediation_badge_markup(product_id, locale=locale)
    if not badge:
        return html_content
    lower = html_content.lower()
    if "aicom-rework-badge" in lower:
        return html_content
    if "</body>" in lower:
        return re.sub(r"</body>", badge + "\n</body>", html_content, count=1, flags=re.IGNORECASE)
    return html_content + badge
