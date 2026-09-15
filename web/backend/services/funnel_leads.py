"""Lead capture → pipeline auto-start → status tracking → completion notify."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from web.backend.services.funnel_store import (
    create_lead_record,
    get_lead_by_product,
    get_lead_by_token,
    update_lead,
)
from web.backend.services.pipeline_enqueue import append_product_to_pipeline_state

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _auto_pipeline_enabled() -> bool:
    return _truthy("AIFACTORY_LEAD_AUTO_PIPELINE", "1")


def create_lead_and_maybe_start_pipeline(
    *,
    email: str,
    idea: str,
    name: str = "",
    company: str = "",
    source: str = "lead_page",
    referral: str | None = None,
) -> dict[str, Any]:
    """Persist lead; optionally enqueue a marketing_landing pipeline product."""
    product_id: str | None = None
    pipeline_started = False
    pipeline_error: str | None = None

    if _auto_pipeline_enabled() and len(idea.strip()) >= 10 and source != "verify_script":
        try:
            product_id = _start_lead_pipeline(
                email=email,
                idea=idea,
                name=name,
                company=company,
                source=source,
                referral=referral,
            )
            pipeline_started = bool(product_id)
        except Exception as e:
            logger.exception("lead auto-pipeline failed")
            pipeline_error = str(e)[:500]

    lead = create_lead_record(
        email=email,
        idea=idea,
        name=name,
        company=company,
        source=source,
        referral=referral,
        product_id=product_id,
    )

    return {
        "ok": True,
        "lead_id": lead["id"],
        "status_token": lead["status_token"],
        "status_url": f"/status/{lead['status_token']}",
        "product_id": product_id,
        "pipeline_started": pipeline_started,
        "pipeline_error": pipeline_error,
        "message": (
            "Pipeline started — track progress on your status page."
            if pipeline_started
            else "Thank you — we received your idea."
        ),
    }


def _start_lead_pipeline(
    *,
    email: str,
    idea: str,
    name: str,
    company: str,
    source: str,
    referral: str | None,
) -> str:
    from agents.product_profile import MARKETING_LANDING, infer_delivery_profile, normalize_delivery_profile
    from marketplace_taxonomy import slug_to_marketplace_category
    from web.backend.services.desktop_product import infer_category_for_new_product

    idea_stripped = idea.strip()
    dprof = normalize_delivery_profile(
        infer_delivery_profile(
            f"Public funnel lead. Contact: {email}. Company: {company or 'n/a'}.",
            idea_stripped,
        )
    )
    if source in ("lead_page", "hero", "homepage") and "full" not in idea_stripped.lower():
        dprof = MARKETING_LANDING

    category = infer_category_for_new_product(idea_stripped, "", dprof)
    mapped = slug_to_marketplace_category(category)
    if mapped:
        category = mapped

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product: dict[str, Any] = {
        "id": product_id,
        "idea": idea_stripped,
        "admin_instructions": (
            f"Funnel lead from {source}. Owner email: {email}. "
            f"Name: {name or 'n/a'}. Company: {company or 'n/a'}. "
            "Ship a show-ready marketing landing aligned with the brief."
        ),
        "delivery_profile": dprof,
        "production_mode": False,
        "category": category,
        "tags": ["funnel-lead", source],
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "owner_email": email,
        "funnel_lead_source": source,
        "funnel_referral": referral,
        "landing_fast_path": dprof == MARKETING_LANDING,
    }
    append_product_to_pipeline_state(product)
    try:
        from web.backend.services.admin_action_log import log_admin_action

        log_admin_action(
            actor_username="system",
            action="product_created",
            resource=f"pipeline/{product_id}",
            details={"source": source, "owner_email": email, "idea_preview": idea_stripped[:120]},
            actor_type="system",
        )
    except Exception:
        pass
    return product_id


def public_lead_status(token: str) -> dict[str, Any] | None:
    lead = get_lead_by_token(token)
    if not lead:
        return None
    product_id = lead.get("product_id")
    product_state = None
    product_name = None
    sandbox_ready = False
    storefront_url = None

    if product_id:
        prod = _load_product(product_id)
        if prod:
            product_state = str(prod.get("state") or "")
            product_name = str(prod.get("idea") or "")[:120]
            sandbox_ready = product_state in (
                "SANDBOX_RUNNING",
                "TELEMETRY_COLLECTING",
                "EVOLUTION_ANALYZING",
                "COMPLETED",
                "DEPLOYED_PRODUCTION",
                "SALES_ACTIVE",
            )
            from core.public_site_url import resolve_public_site_url

            base = resolve_public_site_url()
            storefront_url = f"{base}/product/{product_id}"

    status = str(lead.get("status") or "received")
    if product_state in ("COMPLETED", "DEPLOYED_PRODUCTION") and status != "completed":
        status = "completed"
    elif product_state == "FAILED":
        status = "failed"
    elif product_id and status == "received":
        status = "pipeline_started"

    return {
        "lead_id": lead.get("id"),
        "status": status,
        "email": _mask_email(str(lead.get("email") or "")),
        "idea_preview": str(lead.get("idea") or "")[:200],
        "product_id": product_id,
        "product_state": product_state,
        "product_name": product_name,
        "sandbox_ready": sandbox_ready,
        "storefront_url": storefront_url,
        "created_at": lead.get("created_at"),
        "updated_at": lead.get("updated_at"),
        "completed_at": lead.get("completed_at"),
    }


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def _load_product(product_id: str) -> dict[str, Any] | None:
    try:
        from core.pipeline_state_writer import read_pipeline_state
        from core.paths import pipeline_json_path

        state = read_pipeline_state(json_path=pipeline_json_path())
        prod = (state.get("products") or {}).get(product_id)
        return prod if isinstance(prod, dict) else None
    except Exception:
        logger.debug("funnel status product load failed for %s", product_id, exc_info=True)
        return None


def on_product_state_change(product_id: str, product: dict[str, Any]) -> None:
    """Sync lead record when linked product reaches terminal states."""
    lead = get_lead_by_product(product_id)
    if not lead:
        return
    st = str(product.get("state") or "").upper()
    if st in ("COMPLETED", "DEPLOYED_PRODUCTION"):
        update_lead(
            lead["id"],
            status="completed",
            completed_at=time.time(),
        )
    elif st == "FAILED":
        update_lead(lead["id"], status="failed")


async def notify_lead_product_completed(product_id: str, product: dict[str, Any]) -> None:
    """Email lead owner when their product ships (best-effort)."""
    lead = get_lead_by_product(product_id)
    if not lead:
        owner_email = str(product.get("owner_email") or "").strip()
        if not owner_email:
            return
        lead = {"email": owner_email, "id": None, "status_token": None}
    elif lead.get("notify_sent_at"):
        return

    from core.public_site_url import resolve_public_site_url
    from web.backend.services.funnel_notify import send_funnel_email

    base = resolve_public_site_url()
    product_url = f"{base}/product/{product_id}"
    status_url = f"{base}/status/{lead.get('status_token')}" if lead.get("status_token") else product_url
    idea = str(product.get("idea") or lead.get("idea") or "your product")[:120]

    subject = f"Your AI Factory build is ready: {idea[:60]}"
    body = (
        f"Hi,\n\n"
        f"Your product has completed the pipeline.\n\n"
        f"Idea: {idea}\n"
        f"Preview & checkout: {product_url}\n"
        f"Track status: {status_url}\n\n"
        f"— AI Factory\n"
    )
    ok, detail = await send_funnel_email(
        to_email=str(lead.get("email") or product.get("owner_email") or ""),
        subject=subject,
        body_plain=body,
    )
    if ok and lead.get("id"):
        update_lead(lead["id"], notify_sent_at=time.time(), status="completed", completed_at=time.time())
    elif not ok:
        logger.warning("funnel lead notify failed for %s: %s", product_id, detail)
