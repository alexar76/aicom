"""Admin API: optional PostgreSQL pipeline store and migration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.pipeline_database_admin import (
    migrate_sqlite_to_postgres,
    pipeline_db_status,
    test_postgres_connection,
)

router = APIRouter(prefix="/api/admin/pipeline-database", tags=["admin-pipeline-database"])


def _config(request: Request):
    return request.app.state.config


@router.get("/status")
async def get_pipeline_database_status(
    request: Request,
    _admin: dict = Depends(require_admin_with_rbac),
):
    return pipeline_db_status(_config(request))


@router.post("/test-connection")
async def post_test_postgres_connection(
    request: Request,
    _admin: dict = Depends(require_admin_with_rbac),
):
    body = await request.json()
    url = str(body.get("database_url") or "").strip()
    if not url:
        url = str(_config(request).get("general.pipeline_database_url", "") or "").strip()
    return test_postgres_connection(url)


@router.post("/migrate-sqlite-to-postgres")
async def post_migrate_sqlite_to_postgres(
    request: Request,
    _admin: dict = Depends(require_admin_with_rbac),
):
    body = await request.json()
    url = str(body.get("database_url") or "").strip()
    if not url:
        url = str(_config(request).get("general.pipeline_database_url", "") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="database_url is required (save in Settings first)")
    clear_target = bool(body.get("clear_target", False))
    try:
        result = migrate_sqlite_to_postgres(url, clear_target=clear_target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
