#!/usr/bin/env python3
"""Repair module layout after fix_silent_except_pass (imports vs docstring / __future__)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LS_IMPORT = "from core.logging_utils import log_suppressed"


def repair(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if LS_IMPORT not in text:
        return False

    lines = text.splitlines(keepends=True)
    # Strip misplaced log_suppressed lines
    filtered: list[str] = []
    removed = False
    for line in lines:
        if line.strip() == LS_IMPORT:
            removed = True
            continue
        filtered.append(line)
    if not removed:
        return False
    lines = filtered

  # Find end of module docstring (if any)
    idx = 0
    if lines and lines[0].strip().startswith('"""'):
        if lines[0].strip().count('"""') >= 2:
            idx = 1
        else:
            for i in range(1, len(lines)):
                if '"""' in lines[i]:
                    idx = i + 1
                    break

    # Skip blank lines after docstring
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    # __future__ block must stay first after docstring
    future_end = idx
    while future_end < len(lines) and lines[future_end].strip().startswith("from __future__"):
        future_end += 1

    # Find last import line
    import_end = future_end
    i = future_end
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith(("import ", "from ")) and not s.startswith("from ."):
            import_end = i + 1
            i += 1
            continue
        if s.startswith("from ."):
            import_end = i + 1
            i += 1
            continue
        if not s or s.startswith("#"):
            i += 1
            continue
        break

    insert_line = LS_IMPORT + "\n"
    if insert_line not in lines:
        lines.insert(import_end, insert_line)

    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> None:
    targets = list(ROOT.rglob("*.py"))
    n = 0
    for py in targets:
        if repair(py):
            rel = py.relative_to(ROOT)
            if str(rel).startswith(("orchestrator/", "security/", "core/", "web/backend/", "main.py", "pipeline_worker")):
                print(rel)
                n += 1
    print(f"repaired {n} files")


if __name__ == "__main__":
    main()
