"""The route SKOPOS's remediation conductor calls to get a patch authored.

One endpoint, and it returns a **unified diff** — never an image, never a write to the deployed tree.
The diff goes onto a ``momus/fix-*`` branch, a node agent builds that commit, MOMUS gates the
resulting image, and only then does anything ship. All the authoring logic (and the reasoning behind
each refusal) lives in ``web.backend.services.remediation_fix``.

Two things about the surface are worth stating here, because both were real hazards:

**This route is publicly reachable.** nginx does not proxy ``/api/remediation/*``, but
``web/frontend/next.config.js`` rewrites ``/api/:path*`` to the internal API — so the path is live on
the public host, and ``ApiVersionMiddleware`` makes ``/api/v1/remediation/fix`` an equivalent spelling.
CSRF does not help: it exempts header-token callers by design. So this endpoint carries its own shared
secret, fail-closed in production, and refuses in public-demo mode.

**A refusal answers 200 with ``ok: false``.** That is not sloppiness — the conductor distinguishes
"this patch attempt failed, try again" from "an operator has to fix something" by reading
``config_error`` out of the body, and an HTTP error code would flatten the two into one retry loop.
Authentication failures are the exception and use real status codes, because a caller that is not
authorised has nothing to read.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from web.backend.services.public_demo_guard import require_not_public_demo
from web.backend.services.remediation_fix import (
    ENABLED_ENV,
    KEY_ENV,
    FixRefused,
    author_fix,
    is_enabled,
    scope_map,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remediation", tags=["remediation"])


def _is_production() -> bool:
    return str(os.environ.get("AIFACTORY_PROD", "")).strip().lower() in ("1", "true", "yes", "on")


def _require_conductor(request: Request) -> None:
    """Shared secret with the SKOPOS conductor, compared in constant time.

    Fail-closed in production or whenever autonomous patch authoring is enabled. An unset key is
    allowed only for inspecting the disabled development surface; it must never turn an enabled,
    potentially billable LLM route into an unauthenticated endpoint."""
    expected = str(os.environ.get(KEY_ENV, "")).strip()
    supplied = (request.headers.get("x-remediation-key") or "").strip()
    if not expected:
        if _is_production() or is_enabled():
            raise HTTPException(
                status_code=503,
                detail=f"{KEY_ENV} is unset — refusing enabled patch authoring for an "
                       f"unauthenticated caller.")
        return
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Remediation-Key")


def _is_operator_fault(exc: BaseException) -> bool:
    """Is this an operator's to clear, rather than a patch to re-attempt?

    The distinction is the whole reason a refusal answers 200 with `config_error`. Getting it wrong
    costs three Factory rounds and an escalation that blames the patch — which is what a live ticket
    did on a `ModuleNotFoundError`, and again on a provider answering `402 Payment Required`.

    Provider billing and auth failures arrive as a generic ``RuntimeError`` carrying the upstream
    status in its message, so this reads the message. Matching on text is not elegant, but the
    alternative is retrying an unpaid account three times and calling the patch bad."""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return True
    if type(exc).__name__ in ("PipelineCostBudgetExceeded", "LLMUsageLimitError"):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in (
        "402", "payment required", "401", "403", "insufficient", "quota",
        "no available provider", "invalid api key",
    ))


@router.post("/fix")
async def remediation_fix(request: Request) -> dict[str, Any]:
    """Author a patch for one signed MOMUS remediation ticket.

    Request:  ``{"ticket": {...}}`` — the conductor posts RemediationTicket.to_dict() verbatim.
    Response: ``{"ok": true, "patch": {"diff", "summary", "files", "deployable": false}}``
              or ``{"ok": false, "error": ..., "config_error": bool}``.
    """
    _require_conductor(request)
    require_not_public_demo("autonomous patch authoring")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 - a non-JSON body is a client error, not a crash
        raise HTTPException(status_code=400, detail="Body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    ticket = payload.get("ticket")
    if not isinstance(ticket, dict):
        raise HTTPException(status_code=400, detail="Body must carry a 'ticket' object")

    llm_router = getattr(request.app.state, "llm_router", None)
    try:
        patch = await author_fix(
            ticket, llm_router=llm_router,
            previous_failure=str(payload.get("previous_failure") or ""),
            attempt=int(payload.get("attempt") or 1),
        )
    except FixRefused as exc:
        # Deliberately 200. `config_error` is what tells the conductor to escalate to a human instead
        # of asking for another patch — an HTTP error would erase that distinction.
        logger.warning("remediation fix refused for %s: %s",
                       ticket.get("finding_id"), exc.reason)
        return {"ok": False, "error": exc.reason, "config_error": exc.config_error}
    except Exception as exc:  # noqa: BLE001
        # Includes the budget errors, which MUST reach the caller as a refusal rather than being
        # swallowed into a fabricated patch — the failure mode agents/base_agent.py exhibits.
        logger.exception("remediation fix failed for %s", ticket.get("finding_id"))
        # A missing dependency or an exhausted budget is an OPERATOR's to clear. Returning
        # config_error=False for those made the conductor retry three times and then blame the patch
        # — a live ticket did exactly that on a ModuleNotFoundError.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500],
                "config_error": _is_operator_fault(exc)}

    logger.info("authored a patch for %s (%s): %s file(s), %d bytes of diff",
                patch.finding_id, patch.component, len(patch.files), len(patch.diff))
    return {"ok": True, "patch": patch.to_dict()}


@router.get("/fix/status")
async def remediation_fix_status(request: Request) -> dict[str, Any]:
    """What an operator needs to answer "is this on, and for what?" without posting a ticket."""
    _require_conductor(request)
    return {
        "enabled": is_enabled(),
        "enable_with": f"{ENABLED_ENV}=1",
        "authenticated": bool(str(os.environ.get(KEY_ENV, "")).strip()),
        "production": _is_production(),
        # Which components may be patched, and exactly which files for each. The scope is this
        # host's, never the caller's.
        "scope": scope_map(),
        "llm_router": getattr(request.app.state, "llm_router", None) is not None,
    }
