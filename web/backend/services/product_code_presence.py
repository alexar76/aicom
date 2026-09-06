"""Whether a factory product tree has shippable generated code on disk.

Used by the public storefront grid, sandbox listing, and policy audit. A repair
round that only documents a mesh/schema fix used to rewrite ``code_manifest.json``
with ``\"files\": []``, which made ``_product_has_code`` false even though the
full backend/frontend tree was still on disk — detail stayed up (no code gate)
while the витрина card disappeared. Prefer the manifest when it lists existing
paths; otherwise scan the tree for real source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

# Shippable source — not README/md alone, not the manifest itself.
_SOURCE_SUFFIXES = frozenset({
    ".html",
    ".htm",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".vue",
    ".svelte",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".cs",
    ".rb",
    ".php",
})


def _entry_rel_path(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("path") or entry.get("file_path") or "").strip().lstrip("/")


def code_tree_has_source_files(product_code_dir: Path) -> bool:
    """True if the product code directory contains at least one source file."""
    if not product_code_dir.is_dir():
        return False
    try:
        for path in iter_product_files(product_code_dir):
            if path.name.startswith(".") or path.name == "code_manifest.json":
                continue
            if path.suffix.lower() in _SOURCE_SUFFIXES:
                return True
    except OSError:
        return False
    return False


def product_has_code(product_code_dir: Path) -> bool:
    """True when the product has generated code: listed manifest paths, or source on disk.

    An empty ``files`` list in ``code_manifest.json`` is not proof of an empty
    tree — patch rounds that write zero files still overwrite the manifest.
    """
    if not product_code_dir.is_dir():
        return False
    manifest_path = product_code_dir / "code_manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files", []) if isinstance(manifest, dict) else []
            if isinstance(files, list):
                for entry in files:
                    rel = _entry_rel_path(entry)
                    if rel and (product_code_dir / rel).is_file():
                        return True
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return code_tree_has_source_files(product_code_dir)


def preserve_manifest_file_entries(
    previous_files: list[Any] | None,
    *,
    deleted_paths: set[str] | frozenset[str] | None = None,
) -> list[dict[str, str]]:
    """Keep path entries from a prior manifest when this round wrote nothing new."""
    deleted = {str(p).strip().lstrip("/") for p in (deleted_paths or ()) if p}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in previous_files or []:
        rel = _entry_rel_path(entry)
        if not rel or rel in deleted or rel in seen:
            continue
        seen.add(rel)
        out.append({"path": rel, "preserved": True})
    return out
