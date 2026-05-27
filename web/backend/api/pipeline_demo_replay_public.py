"""Public read-only stream for the pipeline demo replay **upload**.

HTML5 ``<video src>`` cannot attach ``Authorization: Bearer``; admin-only
``/api/admin/demo-replay/media/...`` therefore fails in the browser even when
the operator is logged in via localStorage. This route serves the **currently
published** upload (when enabled in config) without auth — same clip the admin
already chose to show on Live Monitor / dashboard payload.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from web.backend.services.pipeline_demo_replay import load_raw_config, resolve_uploaded_media_path

router = APIRouter(tags=["public-pipeline-demo-replay"])


@router.get("/public/pipeline-demo-replay")
async def get_public_pipeline_demo_replay() -> FileResponse:
    cfg = load_raw_config()
    if not cfg.get("enabled"):
        raise HTTPException(status_code=404, detail="Demo replay is not published")
    if str(cfg.get("source") or "") != "upload":
        raise HTTPException(status_code=404, detail="No uploaded demo asset")
    path = resolve_uploaded_media_path(cfg)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    fn = path.name

    if fn.endswith(".webm"):
        mt = "video/webm"
    elif fn.endswith(".mp4"):
        mt = "video/mp4"
    else:
        mt = "video/quicktime"

    return FileResponse(
        path,
        media_type=mt,
        filename=fn,
        headers={
            "Cache-Control": "private, max-age=300",
            "Accept-Ranges": "bytes",
        },
    )
