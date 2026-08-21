"""Admin API — view and edit Marketing launch blog posts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.schemas.api_requests import BlogPostBackfillRequest, BlogPostUpdateRequest, BlogScreenshotRequest
from web.backend.services.product_blog import (
    backfill_launch_posts,
    get_blog_post,
    list_blog_posts,
    regenerate_post_screenshot,
    update_blog_post,
)

router = APIRouter(prefix="/blog", tags=["admin-blog"], dependencies=[Depends(require_admin_with_rbac)])


@router.get("/posts")
async def admin_list_blog_posts(_admin: dict = Depends(require_admin_with_rbac)) -> dict[str, Any]:
    _ = _admin
    summaries = list_blog_posts(include_drafts=True)
    return {"posts": summaries, "count": len(summaries)}


@router.get("/posts/{slug}")
async def admin_get_blog_post(slug: str, _admin: dict = Depends(require_admin_with_rbac)) -> dict[str, Any]:
    _ = _admin
    post = get_blog_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.put("/posts/{slug}")
async def admin_update_blog_post(
    slug: str,
    body: BlogPostUpdateRequest,
    admin: dict = Depends(require_admin_with_rbac),
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return update_blog_post(slug, patch, edited_by=str(admin.get("username") or "admin"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/posts/backfill")
async def admin_backfill_blog_posts(
    body: BlogPostBackfillRequest,
    _admin: dict = Depends(require_admin_with_rbac),
) -> dict[str, Any]:
    _ = _admin
    return backfill_launch_posts(
        only_missing=body.only_missing,
        capture_screenshots=body.capture_screenshots,
        base_url=body.base_url,
        overwrite=body.overwrite,
    )


@router.post("/posts/{slug}/screenshot")
async def admin_regenerate_screenshot(
    slug: str,
    body: BlogScreenshotRequest | None = None,
    _admin: dict = Depends(require_admin_with_rbac),
) -> dict[str, Any]:
    _ = _admin
    base_url = body.base_url if body else None
    try:
        return regenerate_post_screenshot(slug, base_url=base_url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
