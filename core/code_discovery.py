"""
Shared rules for scanning generated product source trees.

Excludes sandbox venvs, vendor packages, and other heavy ephemeral dirs so QA,
security scans, and runtime test inference stay on product code only.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

PRODUCT_CODE_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "preview-venv",
        ".aicom_sandbox",
        "site-packages",
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
    }
)


def should_skip_code_path(path: Path) -> bool:
    """True when *path* lives under a vendor/sandbox/tooling directory."""
    return any(part in PRODUCT_CODE_SKIP_DIR_NAMES for part in path.parts)


def copytree_ignore(_directory: str, names: list[str]) -> list[str]:
    """``shutil.copytree(..., ignore=copytree_ignore)`` helper."""
    return [name for name in names if name in PRODUCT_CODE_SKIP_DIR_NAMES]


def iter_product_files(root: Path, pattern: str = "*") -> Iterator[Path]:
    """Yield files under *root*, skipping vendor/sandbox directories.

    Uses ``os.walk`` with directory pruning so ``.aicom_sandbox`` / venvs are not
    traversed (rglob + post-filter still stats tens of thousands of vendor files).
    """
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in PRODUCT_CODE_SKIP_DIR_NAMES]
        for name in filenames:
            if pattern != "*" and not fnmatch(name, pattern):
                continue
            fpath = Path(dirpath) / name
            if should_skip_code_path(fpath):
                continue
            yield fpath
