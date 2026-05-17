"""Admin API: demo replay video shown on Live Monitor."""

from __future__ import annotations

import time
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from web.backend.schemas.api_requests import DemoReplayPatchRequest
from fastapi.responses import FileResponse

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.pipeline_demo_replay import (
    ALLOWED_EXT,
    FILENAME_SAFE,
    MAX_UPLOAD_BYTES,
    admin_public_config,
    load_raw_config,
    safe_remove_media,
    save_config,
    upload_dir,
    validate_external_url,
)

router = APIRouter(tags=["admin-demo-replay"], dependencies=[Depends(require_admin_with_rbac)])


@router.get("/demo-replay")
async def get_demo_replay(_admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    return admin_public_config()


@router.patch("/demo-replay")
async def patch_demo_replay(body: DemoReplayPatchRequest, _admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    cfg = load_raw_config()

    if body.enabled is not None:
        cfg["enabled"] = body.enabled

    if body.title is not None:
        cfg["title"] = body.title

    if "video_url" in body.model_fields_set:
        vu = body.video_url
        if vu is None:
            if cfg.get("source") == "external_url":
                cfg["source"] = "none"
                cfg["video_url"] = None
        else:
            if not validate_external_url(vu):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid video_url (use https://, http://, or same-origin path)",
                )
            cfg["video_url"] = vu
            cfg["source"] = "external_url"
            old_fn = cfg.get("media_filename")
            cfg["media_filename"] = None
            if isinstance(old_fn, str) and old_fn:
                safe_remove_media(old_fn)

    save_config(cfg)
    return admin_public_config()


@router.post("/demo-replay/upload")
async def upload_demo_replay_video(
    file: UploadFile = File(...),
    _admin: dict = Depends(require_admin_with_rbac),
):
    _ = _admin
    cfg = load_raw_config()
    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Allowed extensions: .webm, .mp4, .mov")

    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    upload_dir().mkdir(parents=True, exist_ok=True)
    safe_name = f"demo_{int(time.time())}{ext}"
    path = upload_dir() / safe_name
    path.write_bytes(body)

    old_fn = cfg.get("media_filename")
    if isinstance(old_fn, str) and old_fn and old_fn != safe_name:
        safe_remove_media(old_fn)

    cfg["media_filename"] = safe_name
    cfg["source"] = "upload"
    cfg["video_url"] = None
    cfg["enabled"] = True
    save_config(cfg)
    return admin_public_config()


@router.get("/demo-replay/media/{filename}")
async def demo_replay_media(filename: str, _admin: dict = Depends(require_admin_with_rbac)):
    """Serve uploaded demo video (requires admin cookie or bearer — same as dashboard)."""
    _ = _admin
    if not FILENAME_SAFE.match(filename):
        raise HTTPException(status_code=404, detail="Not found")
    cfg = load_raw_config()
    if cfg.get("source") != "upload" or cfg.get("media_filename") != filename:
        raise HTTPException(status_code=404, detail="Not found")
    path = upload_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    if filename.endswith(".webm"):
        mt = "video/webm"
    elif filename.endswith(".mp4"):
        mt = "video/mp4"
    else:
        mt = "video/quicktime"

    return FileResponse(path, media_type=mt, filename=filename)
