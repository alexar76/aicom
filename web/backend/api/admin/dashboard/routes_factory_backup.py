"""Admin: full factory data backup and restore (ZIP)."""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from web.backend.core.admin_roles import AdminRole, normalize_role, rank, require_admin_with_rbac
from web.backend.services.factory_backup import (
    build_factory_backup_zip,
    preview_restore,
    restore_factory_from_upload,
    save_restore_upload,
)
from web.backend.services.public_demo_guard import require_not_public_demo

from ._router import router
from .helpers import _unlink_path_quiet

logger = logging.getLogger(__name__)


def _require_admin_owner(admin: dict) -> None:
    role = normalize_role(admin.get("role"))
    if rank(role) < rank(AdminRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail="Factory backup/restore requires admin or super_admin role.",
        )


@router.get("/factory-backup.zip")
async def download_factory_backup_zip(
    background_tasks: BackgroundTasks,
    include_sandboxes: bool = Query(
        False,
        description="Include data/sandboxes (can be very large)",
    ),
    admin: dict = Depends(require_admin_with_rbac),
):
    """ZIP of the entire factory data volume (pipeline, configs, secrets, products, logs)."""
    require_not_public_demo("factory backup download")
    _require_admin_owner(admin)

    try:
        zip_path, filename = build_factory_backup_zip(include_sandboxes=include_sandboxes)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("factory backup failed")
        raise HTTPException(status_code=500, detail=f"Factory backup failed: {e}") from e

    background_tasks.add_task(_unlink_path_quiet, str(zip_path))
    return FileResponse(
        path=str(zip_path),
        filename=filename,
        media_type="application/zip",
    )


@router.post("/factory-backup/preview")
async def factory_restore_preview(
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin_with_rbac),
):
    """Upload a factory backup ZIP and return warnings + current instance stats."""
    require_not_public_demo("factory restore preview")
    _require_admin_owner(admin)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip factory backup file")

    try:
        content = await file.read()
        token, _path = save_restore_upload(content)
        return preview_restore(token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("factory restore preview failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/factory-backup/restore")
async def factory_restore_execute(
    restore_token: str = Form(...),
    confirm_replace_all: bool = Form(False),
    confirm_trusted_backup: bool = Form(False),
    confirm_saved_current_backup: bool = Form(False),
    admin: dict = Depends(require_admin_with_rbac),
):
    """
    Replace the live data volume from a previously previewed upload (full snapshot, not merge).
    """
    require_not_public_demo("factory restore")
    _require_admin_owner(admin)

    if not confirm_replace_all or not confirm_trusted_backup or not confirm_saved_current_backup:
        raise HTTPException(
            status_code=400,
            detail="All confirmation checkboxes are required before restore.",
        )

    try:
        return restore_factory_from_upload(
            restore_token.strip(),
            create_pre_restore_backup=True,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("factory restore failed")
        raise HTTPException(status_code=500, detail=f"Factory restore failed: {e}") from e
