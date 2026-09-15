"""Normalize generated web products so sandbox preview and QA find index.html."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from core.paths import data_root
from web.backend.services.sandbox_static_entry import _STATIC_PREVIEW_CANDIDATES

logger = logging.getLogger(__name__)

_ASSET_ATTR_RE = re.compile(
    r"""\b(href|src)\s*=\s*(['"])(?!https?:|//|#|mailto:|tel:|data:|javascript:)(\./)?([^'"]+)\2""",
    re.I,
)


def _rewrite_copied_html(html: str, src_rel_dir: str) -> str:
    """Point relative assets at the original nested folder after copying HTML to root."""
    prefix = src_rel_dir.replace("\\", "/").strip("/")
    if not prefix or prefix == ".":
        return html

    def _repl(m: re.Match[str]) -> str:
        attr, quote, _dot, path = m.group(1), m.group(2), m.group(3), m.group(4)
        if path.startswith("/") or path.startswith("../"):
            return m.group(0)
        return f"{attr}={quote}{prefix}/{path}{quote}"

    return _ASSET_ATTR_RE.sub(_repl, html)


def ensure_web_entrypoint_at_product_root(product_id: str) -> bool:
    """
    Copy nested index.html to product root when developers placed it under frontend/ etc.
    Rewrites relative CSS/JS hrefs so the copy still loads the nested theme.
    Updates code_manifest.json when a copy is made.
    """
    code_dir = data_root() / "code" / product_id
    if not code_dir.is_dir():
        return False
    root_index = code_dir / "index.html"
    if root_index.is_file():
        return False
    src: Path | None = None
    for rel in _STATIC_PREVIEW_CANDIDATES:
        if rel in ("index.html", "index.htm"):
            continue
        candidate = code_dir / rel
        if candidate.is_file():
            src = candidate
            break
    if src is None:
        return False
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
        src_dir = str(src.parent.relative_to(code_dir)).replace("\\", "/")
        text = _rewrite_copied_html(text, src_dir)
        root_index.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("ensure_web_entrypoint copy failed for %s: %s", product_id, exc)
        return False

    manifest_path = code_dir / "code_manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files")
            if isinstance(files, list):
                has_root = any(
                    isinstance(f, dict)
                    and str(f.get("path") or f.get("file_path") or "") in ("index.html", "/index.html")
                    for f in files
                )
                if not has_root:
                    files.append({"path": "index.html", "role": "entrypoint", "copied_from": str(src.relative_to(code_dir))})
                    manifest["files"] = files
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("manifest patch after entrypoint copy failed for %s: %s", product_id, exc)

    logger.info("Copied %s → index.html for %s", src.relative_to(code_dir), product_id)
    return True
