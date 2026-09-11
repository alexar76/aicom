"""Admin product artifact browsing (Files tab, owner ZIP export)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.logging_utils import log_suppressed
from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

_FILES_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "target",
        ".cargo",
        ".eggs",
        "site-packages",
    }
)
_FILES_MAX_PER_CATEGORY = 4000
_FILES_PREVIEW_MAX_CHARS = 5000
_FILES_PREVIEW_READ_BYTES = 262_144
_FILES_PREVIEW_SKIP_BYTES = 8 * 1024 * 1024

_PRODUCT_OWNER_EXPORT_MAX_FILES_PER_CATEGORY = 15_000
_PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES = 512 * 1024 * 1024


def sanitize_admin_product_id(product_id: str) -> str:
    pid = (product_id or "").strip()
    if not pid or len(pid) > 220:
        raise HTTPException(status_code=400, detail="Invalid product id")
    if "/" in pid or "\\" in pid or pid.startswith(".") or ".." in pid:
        raise HTTPException(status_code=400, detail="Invalid product id")
    return pid


def admin_product_artifact_category_dirs(product_id: str) -> dict[str, Path]:
    dr = factory_data_root()
    return {
        "specs": dr / "specs" / product_id,
        "architecture": dr / "arch" / product_id,
        "code": dr / "code" / product_id,
        "bugs": dr / "bugs" / product_id,
        "security": dr / "security" / product_id,
        "marketing": dr / "state" / product_id,
        "telemetry": dr / "telemetry" / product_id,
    }


def walk_artifact_files(
    category_root: Path, *, max_files: int = _FILES_MAX_PER_CATEGORY
) -> tuple[list[Path], bool]:
    """List files under category_root, skipping heavy vendor/tool dirs."""
    if not category_root.exists() or not category_root.is_dir():
        return [], False
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(
        category_root, topdown=True, followlinks=False
    ):
        dirnames[:] = sorted(d for d in dirnames if d not in _FILES_SKIP_DIR_NAMES)
        for name in sorted(filenames):
            if len(out) >= max_files:
                return out, True
            out.append(Path(dirpath) / name)
    return out, False


def unlink_path_quiet(p: str) -> None:
    try:
        Path(p).unlink(missing_ok=True)
    except OSError:
        log_suppressed(logger, "dashboard: temp file cleanup failed", exc_info=True)


def preview_artifact_file(
    fpath: Path, *, size_bytes: int | None = None
) -> tuple[str | None, str | None]:
    """Return (preview, error); exactly one side is set (preview may be empty string)."""
    try:
        size = fpath.stat().st_size if size_bytes is None else size_bytes
    except OSError as e:
        return None, str(e)
    if size == 0:
        return "", None
    if size > _FILES_PREVIEW_SKIP_BYTES:
        return None, "file too large for preview (body not read)"
    try:
        data = fpath.read_bytes()[:_FILES_PREVIEW_READ_BYTES]
    except OSError as e:
        return None, str(e)
    if b"\x00" in data[:8192]:
        return None, "binary file (preview skipped)"
    text = data.decode("utf-8", errors="replace")
    if len(text) > _FILES_PREVIEW_MAX_CHARS:
        return text[:_FILES_PREVIEW_MAX_CHARS] + "\n... (truncated)", None
    if len(data) < size:
        return text + "\n... (truncated; file larger than preview read limit)", None
    return text, None


def build_product_owner_export_zip(
    product_id: str,
    *,
    merged_pipeline_product: dict[str, Any] | None,
) -> tuple[Path, str]:
    """Write a temporary ZIP and return (path, suggested_download_filename)."""
    dirs = admin_product_artifact_category_dirs(product_id)
    skipped_large: list[dict[str, Any]] = []
    truncated_by_category: dict[str, bool] = {}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    safe_slug = product_id.replace("/", "_")[:180]
    filename = f"aicom-product-{safe_slug}-{ts}.zip"

    fd, tmp_path = tempfile.mkstemp(prefix="aicom-owner-export-", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for category, dir_path in dirs.items():
                paths, truncated = walk_artifact_files(
                    dir_path, max_files=_PRODUCT_OWNER_EXPORT_MAX_FILES_PER_CATEGORY
                )
                if truncated:
                    truncated_by_category[category] = True
                for fpath in paths:
                    if not fpath.is_file():
                        continue
                    try:
                        size_bytes = fpath.stat().st_size
                    except OSError:
                        continue
                    if size_bytes > _PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES:
                        skipped_large.append(
                            {
                                "category": category,
                                "path": str(fpath),
                                "size_bytes": size_bytes,
                                "reason": f"file larger than {_PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES} bytes",
                            }
                        )
                        continue
                    try:
                        arc = f"{category}/{fpath.relative_to(dir_path).as_posix()}"
                    except ValueError:
                        arc = f"{category}/{fpath.name}"
                    zf.write(fpath, arcname=arc)

            manifest: dict[str, Any] = {
                "product_id": product_id,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "pipeline_product": merged_pipeline_product,
                "truncated_by_category": truncated_by_category or None,
                "skipped_large_files": skipped_large or None,
                "layout": {
                    "specs": "specs/… (specification and PM artifacts)",
                    "architecture": "architecture/… (from data/arch)",
                    "code": "code/… (generated site / app tree)",
                    "bugs": "bugs/… (QA reports)",
                    "security": "security/…",
                    "marketing": "marketing/… (from data/state — storefront copy, marketing JSON)",
                    "telemetry": "telemetry/…",
                },
            }
            zf.writestr(
                "EXPORT_MANIFEST.json",
                (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            )
            readme = (
                "AI Factory — owner product export (single product, on-disk artifacts).\n"
                "This is not a full factory backup. Folders mirror Admin → Files categories.\n"
                "Open EXPORT_MANIFEST.json for pipeline row snapshot and any skip/truncation notes.\n\n"
                "Экспорт одного продукта для владельца фабрики (артефакты на диске), не бэкап всего инстанса.\n"
            )
            zf.writestr("README_OWNER_EXPORT.txt", readme.encode("utf-8"))
    except Exception:
        unlink_path_quiet(tmp_path)
        raise

    return Path(tmp_path), filename
