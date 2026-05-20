"""
Resolve which HTML file to open in sandbox Live Preview (root vs nested landing paths).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.logging_utils import log_suppressed
from core.paths import code_dir

logger = logging.getLogger(__name__)

# Prefer shallow marketing entrypoints before deep build artifacts.
_STATIC_PREVIEW_CANDIDATES: tuple[str, ...] = (
    "index.html",
    "index.htm",
    "frontend/landing/index.html",
    "frontend/index.html",
    "public/index.html",
    "dist/index.html",
    "frontend/dashboard/dist/index.html",
)


def resolve_static_preview_relpath(code_root: Path) -> Optional[str]:
    """First existing HTML entry relative to the product code root."""
    if not code_root.is_dir():
        return None
    for rel in _STATIC_PREVIEW_CANDIDATES:
        p = code_root / rel
        if p.is_file():
            return rel.replace("\\", "/")
    return None


def static_preview_file(code_root: Path) -> Optional[Path]:
    rel = resolve_static_preview_relpath(code_root)
    if not rel:
        return None
    return code_root / rel


_MIN_STATIC_PREVIEW_BYTES = 400


def storefront_front_page_ready(
    product_id: str,
    *,
    code_root: Path | None = None,
) -> tuple[bool, Optional[str], list[str]]:
    """
    Vitrine «морда»: browser-openable HTML entry (≥400 bytes) that passes demo sandbox_ready.
    """
    root = code_root or code_dir(product_id)
    if not root.is_dir():
        return False, None, ["no_code_dir"]
    rel = resolve_static_preview_relpath(root)
    if not rel:
        return False, None, ["no_front_page_html"]
    try:
        if (root / rel).stat().st_size < _MIN_STATIC_PREVIEW_BYTES:
            return False, rel, ["front_page_too_small"]
    except OSError:
        return False, rel, ["front_page_unreadable"]
    from core.paths import resolve_data_root
    from web.backend.services.demo_quality import assess_product_demo

    dr: str | Path | None = None
    if code_root is not None and code_root.name == product_id and code_root.parent.name == "code":
        dr = code_root.parent.parent
    demo = assess_product_demo(product_id, data_root=dr or resolve_data_root())
    if not demo.get("sandbox_ready"):
        codes = [
            str(i.get("code") or "")
            for i in (demo.get("issues") or [])
            if isinstance(i, dict)
        ]
        return False, rel, ["front_page_not_sandbox_ready", *codes[:5]]
    return True, rel, []


# App-like preview signals for ``full_software`` first storefront listing (not landing-only).
_FULL_SOFTWARE_APP_PREVIEW_PATHS: tuple[str, ...] = (
    "frontend/dashboard/dist/index.html",
    "frontend/dashboard/index.html",
    "dashboard/dist/index.html",
    "dashboard/index.html",
)


def full_software_storefront_preview_capable(
    product_id: str,
    *,
    code_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """
    First-time ``full_software`` vitrine listing: openable HTML plus an app stack
    (compose, FastAPI entry, or dashboard shell) — not a brochure-only tree.
    """
    root = code_root or code_dir(product_id)
    if not root.is_dir():
        return False, ["no_code_dir"]

    rel = resolve_static_preview_relpath(root)
    if not rel:
        return False, ["no_static_preview_html"]
    try:
        if (root / rel).stat().st_size < _MIN_STATIC_PREVIEW_BYTES:
            return False, ["static_preview_too_small"]
    except OSError:
        return False, ["static_preview_unreadable"]

    from web.backend.services.sandbox_compose_preview import find_compose_file
    from web.backend.services.sandbox_preview_api import detect_fastapi_backend

    if find_compose_file(root) is not None:
        return True, []
    if detect_fastapi_backend(root) is not None:
        return True, []
    for app_rel in _FULL_SOFTWARE_APP_PREVIEW_PATHS:
        if (root / app_rel).is_file():
            return True, []

    landing_only = rel.replace("\\", "/") in (
        "frontend/landing/index.html",
        "landing/index.html",
    )
    has_backend = (root / "backend").is_dir() or (root / "server").is_dir()
    if landing_only and has_backend:
        return False, ["full_software_landing_only_no_runnable_preview"]
    if landing_only:
        return False, ["full_software_landing_only_no_app_stack"]

    if has_backend:
        return True, []
    return False, ["full_software_no_app_stack_signal"]


def ensure_storefront_preview_index(product_id: str, *, code_root: Path | None = None) -> Optional[str]:
    """
    Guarantee a browser-openable HTML path for public storefront preview.

    When the repo has no static entry (backend-only WIP), materialize spec landing at
    ``index.html`` so the vitrine never opens a missing root file.
    """
    root = code_root or code_dir(product_id)
    if not root.is_dir():
        return None
    existing = resolve_static_preview_relpath(root)
    if existing:
        return existing
    try:
        from web.backend.services.sandbox_spec_landing import build_spec_landing_html

        built = build_spec_landing_html(product_id)
        if not built:
            return None
        idx = root / "index.html"
        idx.write_text(built, encoding="utf-8")
        logger.info("ensure_storefront_preview_index %s (%d bytes)", product_id, len(built))
        return "index.html"
    except Exception as exc:
        log_suppressed(logger, "ensure_storefront_preview_index", exc_info=exc)
        return None
