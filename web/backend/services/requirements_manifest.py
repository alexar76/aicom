"""Catch requirement lines Vercel/pip cannot parse before they reach --prod.

Measured on Sentinel: the sandbox preview greened because ``pip -r`` failed and the
preview env then installed packages line-by-line (plus a factory bcrypt extra). The
same ``backend/requirements.txt`` contained ``bcrypt==3.2.2==0.110.0``. Vercel
refused to parse it, production deploy failed, and the pipeline recorded
``vercel.ok: false`` while walking to COMPLETED — factory preview ``ok`` was True.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REQ_FILENAMES = ("requirements.txt", "requirements-prod.txt")


def requirement_line_is_valid(line: str) -> bool:
    """True for comments, blanks, pip includes, and PEP 508 requirement strings."""
    s = line.strip()
    if not s or s.startswith("#"):
        return True
    if s.startswith(("-r ", "-r\t", "-e ", "-e\t", "--")):
        return True
    # ``bcrypt==3.2.2==0.110.0`` — two pins, not a version. pip and Vercel both reject it.
    if s.count("==") > 1:
        return False
    try:
        from packaging.requirements import InvalidRequirement, Requirement

        Requirement(s)
        return True
    except ImportError:
        pass
    except Exception:
        return False
    name = s.split("[", 1)[0]
    name = name.split("@", 1)[0]
    for sep in ("===", "==", "!=", "<=", ">=", "~=", ";", "<", ">"):
        name = name.split(sep, 1)[0]
    name = name.strip()
    return bool(name) and name[0].isalnum()


def drop_invalid_requirements(reqs: list[str]) -> tuple[list[str], list[str]]:
    """Keep only parseable requirement strings. Invalid lines are reported, not rewritten."""
    kept: list[str] = []
    invalid: list[str] = []
    for raw in reqs:
        if requirement_line_is_valid(raw):
            kept.append(raw)
        else:
            invalid.append(raw.strip())
    return kept, invalid


def iter_requirement_files(code_dir: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for rel in (
        "backend/requirements.txt",
        "backend/requirements-prod.txt",
        "requirements.txt",
        "requirements-prod.txt",
        "api/requirements.txt",
        "server/requirements.txt",
    ):
        p = code_dir / rel
        if p.is_file():
            key = str(p.resolve()) if p.exists() else str(p)
            if key not in seen:
                seen.add(key)
                found.append(p)
    # Catch a file sitting only under an unusual dir, without walking venvs.
    for name in _REQ_FILENAMES:
        for p in code_dir.rglob(name):
            if any(part in {".venv", "venv", "node_modules", ".aicom_sandbox"} for part in p.parts):
                continue
            try:
                key = str(p.resolve())
            except OSError:
                key = str(p)
            if key not in seen:
                seen.add(key)
                found.append(p)
    return found


def run_requirements_manifest_check(product_id: str, data_root: str | Path | None = None) -> dict[str, Any]:
    """QA gate: source requirements.txt must be installable as a file, not only line-by-line."""
    from core.paths import data_root as _data_root

    root = Path(data_root) if data_root is not None else Path(_data_root())
    code_dir = root / "code" / product_id
    if not code_dir.is_dir():
        return {"passed": True, "skipped": True, "reason": "no_code_dir"}

    issues: list[str] = []
    files: list[str] = []
    for path in iter_requirement_files(code_dir):
        try:
            rel = path.relative_to(code_dir).as_posix()
        except ValueError:
            rel = path.name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            issues.append(f"invalid_requirement:{rel}: cannot read ({exc})")
            files.append(rel)
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if requirement_line_is_valid(line):
                continue
            issues.append(f"invalid_requirement:{rel}:{i}: {line.strip()}")
            if rel not in files:
                files.append(rel)

    return {
        "passed": not issues,
        "skipped": False,
        "issues": issues[:20],
        "files": files,
    }
