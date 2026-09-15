"""Bridge surrogate reviewer into existing human gate channels."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from agents.surrogate_reviewer import SurrogateReviewer
from core.autonomy_mode import is_full_autonomy
from core.surrogate_review import append_surrogate_audit, write_ai_review_feedback
from web.backend.services.product_followup import record_post_devops_human_review_approval

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def _track_decision(product: dict[str, Any], verdict_dict: dict[str, Any]) -> None:
    hist = product.setdefault("surrogate_decisions", [])
    if isinstance(hist, list):
        hist.append(verdict_dict)


async def resolve_human_gate_async(
    product: dict[str, Any],
    *,
    point: str,
    data_root: Path,
    context: dict[str, Any] | None = None,
    llm_router: Any = None,
) -> str | None:
    """
    Run surrogate at a human gate. Returns new product state if resolved, else None
    (supervised — caller keeps HUMAN_REVIEW_PENDING).
    """
    if not is_full_autonomy():
        return None
    pid = str(product.get("id") or "")
    reviewer = SurrogateReviewer(data_root, llm_router=llm_router)
    verdict = await reviewer.decide(point, product, context or {})
    append_surrogate_audit(data_root, verdict)
    _track_decision(product, verdict.to_dict())

    if verdict.decision == "approve":
        if point == "post_devops_gate":
            await asyncio.to_thread(
                record_post_devops_human_review_approval,
                pid, note=f"ai_review: {verdict.rationale[:500]}",
            )
            return "SALES_ACTIVE"
        if point in ("qa_repair_exhausted", "security_repair_exhausted"):
            product.pop("human_review_kind", None)
            product.pop("human_review_reason", None)
            product["quality_repair_round"] = 0
            product["surrogate_repair_hint"] = verdict.rationale
            return "BUG_FOUND"
        if point == "human_review_stream":
            write_ai_review_feedback(
                data_root,
                product_id=pid,
                review_decision="approve",
                rationale=verdict.rationale,
                point=point,
                confidence=verdict.confidence,
            )
            return None
        return "SALES_ACTIVE"

    # block — and any degenerate "fill" verdict at an approve/block gate falls through
    # here: fail closed, never park the product (full autonomy must always resolve).
    # Director-decision fills are handled separately in resolve_director_pending().
    write_ai_review_feedback(
        data_root,
        product_id=pid,
        review_decision="block",
        rationale=verdict.rationale,
        point=point,
        confidence=verdict.confidence,
    )
    if point in ("qa_repair_exhausted", "security_repair_exhausted", "post_devops_gate"):
        return "FAILED"
    return "BUG_FOUND"


def resolve_human_gate_sync(
    product: dict[str, Any],
    *,
    point: str,
    data_root: Path,
    context: dict[str, Any] | None = None,
) -> str | None:
    """Sync wrapper for state_machine / sync orchestrator paths."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            resolve_human_gate_async(product, point=point, data_root=data_root, context=context)
        )
    # Called from async context — schedule is unsafe; use nest pattern via new task
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            asyncio.run,
            resolve_human_gate_async(product, point=point, data_root=data_root, context=context),
        )
        return fut.result(timeout=180)


async def resolve_director_pending(data_root: Path, llm_router: Any = None) -> int:
    """Auto-resolve pending Director decisions via surrogate in full autonomy mode."""
    if not is_full_autonomy():
        return 0
    try:
        import json

        from core.paths import director_decisions_path

        fp = director_decisions_path()
        if not fp.is_file():
            return 0
        payload = json.loads(fp.read_text(encoding="utf-8"))
        pending = list(payload.get("pending") or [])
        if not pending:
            return 0
        resolved = 0
        still_pending: list[dict] = []
        for decision in pending:
            product = {"id": "director", "idea": decision.get("message") or ""}
            verdict = await SurrogateReviewer(data_root, llm_router=llm_router).decide(
                "director_decision",
                product,
                {"decision": decision},
            )
            append_surrogate_audit(data_root, verdict)
            if verdict.decision in ("approve", "fill"):
                decision["status"] = "approved"
                decision["approved_at"] = __import__("time").time()
                decision["requires_approval"] = False
                decision["surrogate_rationale"] = verdict.rationale
                payload.setdefault("applied", []).append(decision)
                resolved += 1
            else:
                still_pending.append(decision)
        payload["pending"] = still_pending
        fp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return resolved
    except Exception as exc:
        logger.warning("resolve_director_pending failed: %s", exc)
        return 0
