"""
Shared rules for scanning generated product source trees.

Excludes sandbox venvs, vendor packages, and other heavy ephemeral dirs so QA,
security scans, and runtime test inference stay on product code only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
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
    """Yield files under *root*, skipping vendor/sandbox directories."""
    if not root.is_dir():
        return
    for fpath in root.rglob(pattern):
        if fpath.is_file() and not should_skip_code_path(fpath):
            yield fpath
