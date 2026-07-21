#!/usr/bin/env python3
"""Replace ``except ...: pass`` with ``log_suppressed`` in production modules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = (
    "orchestrator/",
    "security/",
    "core/",
    "web/backend/",
    "pipeline_worker.py",
    "main.py",
    "llm/",
    "agents/",
    "director/",
)
SKIP_SUFFIX = ("/tests/",)


def _module_message(rel: str) -> str:
    return f"non-fatal ({rel})"


def _ensure_imports(lines: list[str], tree: ast.Module) -> list[str]:
    has_logging = any(
        isinstance(n, ast.Import) and any(a.name == "logging" for a in n.names)
        for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
    )
    has_logger = "logger = logging.getLogger" in "\n".join(lines)
    has_ls = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "core.logging_utils"
        and any(a.name == "log_suppressed" for a in n.names)
        for n in tree.body
        if isinstance(n, ast.ImportFrom)
    )
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")) or line.strip().startswith('"""') or not line.strip():
            insert_at = i + 1
            continue
        break
    additions: list[str] = []
    if not has_logging:
        additions.append("import logging")
    if not has_logger:
        additions.append("")
        additions.append("logger = logging.getLogger(__name__)")
    if not has_ls:
        additions.append("from core.logging_utils import log_suppressed")
    if not additions:
        return lines
    out = lines[:insert_at] + additions + lines[insert_at:]
    return out


def _except_line_indent(lines: list[str], handler: ast.ExceptHandler) -> str:
    line = lines[handler.lineno - 1]
    return line[: len(line) - len(line.lstrip())]


def fix_file(path: Path) -> int:
    rel = str(path.relative_to(ROOT))
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"skip syntax error: {rel}", file=sys.stderr)
        return 0

    lines = source.splitlines()
    handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                handlers.append(node)

    if not handlers:
        return 0

    # Process bottom-up so line numbers stay valid
    handlers.sort(key=lambda h: h.lineno, reverse=True)

    for handler in handlers:
        pass_lineno = handler.body[0].lineno - 1
        indent = lines[pass_lineno][: len(lines[pass_lineno]) - len(lines[pass_lineno].lstrip())]
        exc_lineno = handler.lineno - 1
        exc_line = lines[exc_lineno].rstrip()

        exc_var = handler.name or "_suppressed_exc"
        if handler.name is None and " as " not in exc_line:
            if exc_line.rstrip().endswith(":"):
                exc_line = exc_line[:-1] + f" as {exc_var}:"
                lines[exc_lineno] = exc_line

        msg = _module_message(rel)
        lines[pass_lineno] = (
            f'{indent}log_suppressed(logger, "{msg}", exc_info={exc_var})'
        )

    lines = _ensure_imports(lines, tree)
    path.write_text("\n".join(lines) + ("\n" if source.endswith("\n") else ""), encoding="utf-8")
    return len(handlers)


def main() -> int:
    total = 0
    files = 0
    for py in sorted(ROOT.rglob("*.py")):
        rel = str(py.relative_to(ROOT))
        if rel.startswith("tests/") or rel.startswith("scripts/fix_silent"):
            continue
        if not any(rel.startswith(p) or rel == p for p in PREFIXES):
            continue
        if any(s in rel for s in SKIP_SUFFIX):
            continue
        n = fix_file(py)
        if n:
            print(f"{rel}: {n}")
            total += n
            files += 1
    print(f"fixed {total} handlers in {files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
