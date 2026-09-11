"""One place that turns a path named in a finding into a path that exists.

Findings come from many tools and each has its own idea of a working directory. ``tsc`` prints
``src/api/advisory.ts`` from inside ``frontend/``; a Python traceback prints ``app/services/cache.py``
with the ``backend/`` root stripped; a detector prints the repo-relative path. Everything downstream —
the repair scope, the file attachment, the edit applier — needs the one form that resolves against the
product tree, and until now each consumer took whatever it was handed.

The cost, measured in a single round:

    область ремонта: []                                   ← no such file, so no scope at all
    2 edit(s) did not apply: src/api/advisory.ts: no such file — use `files` to create it
                            src/components/Operator/Dashboard.tsx: no such file

No scope means nothing gets attached; nothing attached means the round works from memory; and the
memory reproduces the same unresolvable path. Three of four failing gates sat behind that loop.

Two rules keep this honest:

* **never guess between candidates.** Two files ending ``advisory.ts`` is an ambiguity, and resolving
  it by picking one would land a fix in the wrong file — worse than not resolving at all.
* **an unresolvable path is a pipeline defect.** It is reported, not swallowed, because a finding that
  names a file nobody can open is a finding nobody can act on.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Directory roots that tools commonly print relative to. Order matters only for reporting; resolution
# requires a unique answer, so a candidate matching two prefixes is refused rather than ranked.
COMMON_ROOTS = (
    "frontend",
    "backend",
    "web",
    "server",
    "api",
    "app",
    "src",
    "client",
    "apps/web",
    "packages/web",
)

_SKIP_DIRS = frozenset({".git", "node_modules", ".aicom_sandbox", "dist", "build", ".next", "__pycache__", ".venv", "preview-venv"})


def _index(code_dir: Path) -> list[str]:
    out: list[str] = []
    if not code_dir.is_dir():
        return out
    for path in code_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(code_dir)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return out


@lru_cache(maxsize=32)
def _cached_index(code_dir_str: str, stamp: float) -> tuple[str, ...]:
    return tuple(_index(Path(code_dir_str)))


def product_file_index(code_dir: Path) -> tuple[str, ...]:
    """Every product file, repo-relative. Cached per directory mtime so a round pays for one walk."""
    try:
        stamp = code_dir.stat().st_mtime
    except OSError:
        return ()
    return _cached_index(str(code_dir), stamp)


def resolve_product_path(code_dir: Path, candidate: str) -> str | None:
    """The repo-relative path this candidate means, or ``None`` when that cannot be decided.

    Tried in order, and each step must produce exactly one answer:

    1. the candidate as given;
    2. the candidate under a common tool root (``frontend/src/api/advisory.ts``);
    3. the candidate as a unique path *suffix* of a real file, which catches roots this list has never
       heard of.
    """
    rel = str(candidate or "").strip().lstrip("./").replace("\\", "/")
    if not rel:
        return None
    # Strip a line/column suffix if a raw compiler string arrived: `src/a.ts(24,36)`.
    if "(" in rel and rel.endswith(")"):
        rel = rel[: rel.index("(")]
    if (code_dir / rel).is_file():
        return rel

    index = product_file_index(code_dir)
    if not index:
        return None

    prefixed = [f"{root}/{rel}" for root in COMMON_ROOTS if f"{root}/{rel}" in index]
    if len(prefixed) == 1:
        return prefixed[0]
    if len(prefixed) > 1:
        return None  # two roots both have it; picking one would be a coin flip

    tail = "/" + rel
    suffixed = [p for p in index if p.endswith(tail)]
    if len(suffixed) == 1:
        return suffixed[0]
    return None


def resolve_all(code_dir: Path, candidates) -> tuple[list[str], list[str]]:
    """``(resolved, unresolved)`` — the second list is what to complain about."""
    resolved: list[str] = []
    unresolved: list[str] = []
    for candidate in candidates or []:
        got = resolve_product_path(code_dir, str(candidate))
        if got is None:
            unresolved.append(str(candidate))
        elif got not in resolved:
            resolved.append(got)
    return resolved, unresolved
