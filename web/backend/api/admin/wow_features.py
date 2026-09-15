"""Admin API for wow demo features (Factory Floor data, replay, showcase, prompts)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.schemas.api_requests import (
    PipelineReplayForkRequest,
    PromptImprovementApplyRequest,
    ProductShowcaseEnqueueRequest,
)
from web.backend.services.pipeline_replay_timeline import build_replay_timeline, fork_replay_from_frame
from web.backend.services.product_showcase import (
    enqueue_product_showcase,
    get_product_showcase_status,
    list_showcase_gallery,
)
from web.backend.services.prompt_improvement_loop import analyze_failures_and_propose, apply_proposal, list_proposals

router = APIRouter(prefix="/wow", tags=["admin-wow"], dependencies=[Depends(require_admin_with_rbac)])


def _sqlite_path() -> Path:
    from web.backend.api.admin.dashboard import _admin_sqlite_db_path

    return _admin_sqlite_db_path()


def _open_sqlite():
    from orchestrator.sqlite_manager import SQLiteManager

    sm = SQLiteManager(str(_sqlite_path()))
    sm.connect()
    return sm


@router.get("/pipeline/products/{product_id}/replay-timeline")
async def get_replay_timeline(product_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    sm = _open_sqlite()
    try:
        return build_replay_timeline(sm, product_id)
    finally:
        sm.close()


@router.post("/pipeline/products/{product_id}/replay-fork")
async def post_replay_fork(
    product_id: str,
    body: PipelineReplayForkRequest,
    _admin: dict = Depends(require_admin_with_rbac),
):
    _ = _admin
    sm = _open_sqlite()
    try:
        return fork_replay_from_frame(
            sm,
            product_id,
            frame_index=body.frame_index,
            operator_notes=body.operator_notes or "",
            model_override=body.model_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        sm.close()


@router.post("/showcase/enqueue")
async def post_showcase_enqueue(body: ProductShowcaseEnqueueRequest, _admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    return enqueue_product_showcase(body.product_id, base_url=body.base_url)


@router.get("/showcase/gallery")
async def get_showcase_gallery(_admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    return list_showcase_gallery()


@router.get("/showcase/status/{product_id}")
async def get_showcase_status(product_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    try:
        return get_product_showcase_status(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/prompts/analyze")
async def post_prompt_analyze(_admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    sm = _open_sqlite()
    try:
        proposals = analyze_failures_and_propose(sm)
        return {"proposals": proposals, "count": len(proposals)}
    finally:
        sm.close()


@router.get("/prompts/proposals")
async def get_prompt_proposals(_admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    rows = list_proposals()
    return {"proposals": rows, "count": len(rows)}


@router.post("/prompts/apply")
async def post_prompt_apply(body: PromptImprovementApplyRequest, _admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    try:
        return apply_proposal(body.proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
