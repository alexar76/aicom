"""Best-effort transactional email for funnel events."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def send_funnel_email(*, to_email: str, subject: str, body_plain: str) -> tuple[bool, str]:
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return False, "missing recipient"

    if os.environ.get("AIFACTORY_FUNNEL_NOTIFY_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        logger.info("funnel email skipped (AIFACTORY_FUNNEL_NOTIFY_DISABLE): %s", subject[:80])
        return True, "disabled"

    from web.backend.services.outreach_dispatch import send_smtp

    host = (os.environ.get("OUTREACH_SMTP_HOST") or os.environ.get("AIFACTORY_FUNNEL_SMTP_HOST") or "").strip()
    port_s = (os.environ.get("OUTREACH_SMTP_PORT") or os.environ.get("AIFACTORY_FUNNEL_SMTP_PORT") or "587").strip()
    try:
        port = int(port_s)
    except ValueError:
        port = 587
    user = (os.environ.get("OUTREACH_SMTP_USER") or os.environ.get("AIFACTORY_FUNNEL_SMTP_USER") or "").strip()
    password = (os.environ.get("OUTREACH_SMTP_PASSWORD") or os.environ.get("AIFACTORY_FUNNEL_SMTP_PASSWORD") or "").strip()
    from_addr = (
        os.environ.get("OUTREACH_SMTP_FROM")
        or os.environ.get("AIFACTORY_FUNNEL_SMTP_FROM")
        or "noreply@magic-ai-factory.com"
    ).strip()

    if not host:
        logger.info("funnel email skipped (no SMTP host): to=%s subject=%s", to_email, subject[:60])
        return False, "smtp_not_configured"

    return await send_smtp(
        host=host,
        port=port,
        user=user,
        password=password,
        from_addr=from_addr,
        to_addrs=[to_email],
        subject=subject,
        body_plain=body_plain,
    )
