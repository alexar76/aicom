"""Internal markdown links must point at files that exist.

A broken link in published documentation is a small, permanent embarrassment that nobody
notices until a stranger follows it. This guard covers the surfaces we actually publish and
deliberately excludes the ones where a relative path is not meant to resolve on disk.

Scope is a deny-list rather than an allow-list on purpose: a new satellite added tomorrow is
covered without anyone remembering to add it here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".pytest_cache", "site-packages", ".next", "coverage", "lib",
}

# Paths whose relative links are not expected to resolve against the filesystem.
SKIP_PREFIXES = (
    ".claude/",            # worktrees and local agent state
    ".internal/",          # internal notes, not published
    "plans/",              # planning docs use file:line pseudo-links as references
    "wiki/",               # wiki sources: bare page names are links in a wiki, not paths
    "scripts/wiki-",       # ditto
    "contracts/evm/lib/",  # vendored third-party (OpenZeppelin et al.)
    "agents/prompts/",     # prompt templates contain placeholders like README.{code}.md
    "aicom-products/",     # products/<id>/ is materialised at publish time, not in the monorepo
    # Not first-party published documentation, and both are excluded from the public
    # mirror (scripts/aicom_publish_config.py). `independent/` carries whole vendored
    # upstream snapshots under `.upstreams/`: 243 links inside one of them were
    # failing this guard, none of them ours, which is a red gate that says nothing.
    "independent/",
)

#: A vendored snapshot of somebody else's repository, wherever it is checked out.
SKIP_PATH_PARTS = (".upstreams/",)

LINK = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')

EXTERNAL = ("http://", "https://", "mailto:", "tel:", "data:", "#")


def _markdown_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(SKIP_PREFIXES) or "/wiki/" in rel:
                continue
            if any(part in rel for part in SKIP_PATH_PARTS):
                continue
            yield path, rel


def test_internal_markdown_links_resolve():
    broken: list[str] = []
    scanned = 0

    for path, rel in _markdown_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in (LINK, IMAGE):
            for match in pattern.finditer(text):
                target = match.group(2).strip()
                if target.startswith(EXTERNAL):
                    continue
                scanned += 1
                bare = unquote(target.split("#")[0].split("?")[0])
                if not bare:
                    continue
                if (path.parent / bare).resolve().exists():
                    continue
                line = text[: match.start()].count("\n") + 1
                broken.append(f"{rel}:{line} -> {target}")

    assert scanned > 500, f"link scan covered only {scanned} links — the walk is probably broken"
    assert not broken, (
        f"{len(broken)} broken internal markdown link(s):\n  "
        + "\n  ".join(sorted(broken)[:40])
    )
