"""Anything importing the mcp v1 API must pin below mcp 2.

`mcp` 2.x renamed `FastMCP` to `MCPServer` and replaced `mcp/server/fastmcp.py` with a
stub whose only statement is `raise ModuleNotFoundError(...)` — its own message says
"pin 'mcp<2' to keep running v1 code". Two distributions declared `mcp>=1.6,<4` while
their `stdio_server.py` does `from mcp.server.fastmcp import FastMCP`, so a fresh
`pip install aimarket-oracle-gateway` (or the packager's `[mcp]` extra) resolved mcp 2.x
and the stdio server died on its first import. `aimarket-mcp` had already been fixed in
its `pyproject.toml` and still shipped `<4` in its `requirements-mcp.txt`, which is how a
one-place fix leaves the class alive.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = ("node_modules", ".upstreams", ".venv", ".git", ".claude", "site-packages")

#: The v1-only entry points. `mcp.server.mcpserver` is the v2 name and is fine.
_V1_API = re.compile(r"from\s+mcp\.server\.fastmcp\s+import|from\s+mcp\.server\s+import\s+FastMCP")
#: A declared dependency on `mcp` — the WHOLE constraint, commas included. Stopping at
#: the first comma read `mcp>=1.6,<2` as just `>=1.6` and flagged correct pins as bad.
_DECL = re.compile(r'\bmcp\s*((?:[><=!~]=?\s*[0-9][^,"\'\s\]]*)(?:\s*,\s*[><=!~]=?\s*[0-9][^,"\'\s\]]*)*)')


def _first_party(pattern: str) -> list[Path]:
    return sorted(
        p for p in ROOT.rglob(pattern)
        if not any(part in SKIP_PARTS for part in p.parts)
    )


def _owning_project(py: Path, projects: list[Path]) -> Path | None:
    """The NEAREST pyproject.toml above `py`.

    Attributing a file to every ancestor project made the ROOT pyproject.toml — which is
    the whole monorepo — a "consumer of the mcp v1 API" because a package five levels
    down imports it.
    """
    best = None
    for proj in projects:
        root = proj.parent
        if root == py.parent or root in py.parents:
            if best is None or len(root.parts) > len(best.parent.parts):
                best = proj
    return best


def _packages_using_v1() -> list[Path]:
    """Projects whose OWN code (nearest pyproject wins) imports the v1 API."""
    projects = _first_party("pyproject.toml")
    hits: set[Path] = set()
    for py in _first_party("*.py"):
        # A test that NAMES the api is not a consumer of it — including this file, whose
        # own regex literal made the guard report the root project as a v1 consumer.
        if "tests" in py.parts or py.name.startswith("test_"):
            continue
        if not _V1_API.search(py.read_text(encoding="utf-8", errors="replace")):
            continue
        owner = _owning_project(py, projects)
        if owner is not None:
            hits.add(owner)
    return sorted(hits)


def test_the_sweep_finds_the_packages_it_is_about():
    projects = _packages_using_v1()
    assert projects, "no package imports the mcp v1 API — the walk is broken"


def _mcp_constraints(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not re.search(r"\bmcp\b\s*[><=~]", stripped):
            continue
        m = _DECL.search(stripped)
        if m:
            found.append(m.group(1).strip())
    return found


@pytest.mark.parametrize(
    "proj", _packages_using_v1(), ids=lambda p: p.parent.relative_to(ROOT).as_posix()
)
def test_a_v1_consumer_pins_mcp_below_2(proj: Path):
    tree = proj.parent
    files = [proj] + [
        f for f in sorted(tree.glob("requirements*.txt"))
        if not any(part in SKIP_PARTS for part in f.parts)
    ]
    seen = []
    for f in files:
        for constraint in _mcp_constraints(f.read_text(encoding="utf-8", errors="replace")):
            seen.append((f.relative_to(ROOT).as_posix(), constraint))
    assert seen, f"{tree.name} imports the mcp v1 API but declares no mcp dependency"
    bad = [(where, c) for where, c in seen if "<2" not in c]
    assert not bad, (
        f"{tree.name} imports `mcp.server.fastmcp` but allows mcp 2.x, where that module "
        f"raises ModuleNotFoundError on import:\n  "
        + "\n  ".join(f"{where}: mcp{c}" for where, c in bad)
    )
