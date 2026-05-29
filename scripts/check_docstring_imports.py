#!/usr/bin/env python3
"""
Fail CI when executable import statements appear inside a module docstring.

This catches a recurring refactor bug: moving ``import logging`` or
``from core.logging_utils import log_suppressed`` into the opening triple-quoted block
makes the name undefined at runtime while the file still parses.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {
    ".git",
    ".venv",
    ".test-venv",
    "venv",
    "test-venv",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
}
_IMPORT_LINE = re.compile(
    r"^\s*("
    r"import\s+[\w.]+(?:\s*,\s*[\w.]+)*(?:\s+as\s+\w+)?"
    r"|from\s+[\w.]+\s+import\s+.+"
    r")\s*$"
)


def _module_docstring_body(source: str) -> tuple[str, int] | None:
    text = source.lstrip("\ufeff")
    triple_d = '"""'
    triple_s = "'''"
    if not (text.startswith(triple_d) or text.startswith(triple_s)):
        return None
    quote = triple_d if text.startswith(triple_d) else triple_s
    end = text.find(quote, 3)
    if end == -1:
        return None
    body = text[3:end]
    # Line number of first import inside docstring (1-based, relative to file)
    return body, 1


def find_violations(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    parsed = _module_docstring_body(source)
    if parsed is None:
        return []
    body, _ = parsed
    if not body.strip():
        return []
    rel = path.relative_to(_REPO_ROOT)
    hits: list[str] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _IMPORT_LINE.match(line):
            hits.append(f"{rel}:{lineno}: import inside module docstring: {line.strip()}")
    return hits


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def main(argv: list[str] | None = None) -> int:
    roots = [Path(a) for a in (argv or sys.argv[1:])] or [_REPO_ROOT]
    violations: list[str] = []
    for root in roots:
        for path in iter_python_files(root):
            violations.extend(find_violations(path))
    if violations:
        print("Docstring import guard failed:", file=sys.stderr)
        for v in sorted(violations):
            print(f"  {v}", file=sys.stderr)
        print(
            f"\n{len(violations)} file(s) have imports trapped in module docstrings.",
            file=sys.stderr,
        )
        return 1
    print("Docstring import guard: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
