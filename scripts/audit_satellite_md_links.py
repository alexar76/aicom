#!/usr/bin/env python3
"""Audit markdown for satellite links that 404 on alexar76/aicom factory mirror."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Fallback only — the real list comes from satellite-map.yaml via
# aicom_publish_config.py so new satellites (atlas, gaia, metis, …) are covered
# the moment they are registered instead of silently escaping the audit.
FALLBACK_SATELLITES = (
    "aimarket-hub",
    "aimarket-protocol",
    "aimarket-sdks",
    "aimarket-widget",
    "aimarket-agent",
    "ai-service-mesh",
    "alien-monitor",
    "oracles",
    "lottery",
    "argus",
    "acex",
    "desktop-integrations",
    "apps/pulse-terminal",
    "plugins",
)


def mirror_excluded_paths() -> tuple[str, ...]:
    """Paths stripped from the public alexar76/aicom mirror (→ links 404)."""
    script = ROOT / "scripts" / "aicom_publish_config.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script), "list-excludes"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
    except Exception as exc:  # pragma: no cover - config script is optional
        print(f"warn: falling back to the built-in satellite list ({exc})", file=sys.stderr)
        return FALLBACK_SATELLITES
    paths = {line.strip().strip("/") for line in out.splitlines() if line.strip()}
    paths.discard("")
    if not paths:
        return FALLBACK_SATELLITES
    # Longest first: "apps/pulse-terminal" must win over "apps".
    return tuple(sorted(paths, key=lambda p: (-len(p), p)))


ROOT_SATELLITES = mirror_excluded_paths()
ROOT_SAT_RE = "|".join(re.escape(s) for s in ROOT_SATELLITES)

SATellite_RE = re.compile(
    rf"\]\(\.\./(\.\./)?(\.\./)?({ROOT_SAT_RE})(?:/|#|\))"
)

AICOM_STALE = re.compile(
    r"https://github\.com/alexar76/aicom/(?:blob|tree)/main/(?:" + ROOT_SAT_RE + r")(?:/|\)|#|\s|$)"
)

SKIP_DIRS = {
    ".git",
    # Agent-runtime git worktrees: copies of this repo, not the source of truth.
    ".claude",
    "node_modules",
    ".venv",
    "venv",
    "data",
    "web/frontend/test-results",
}


def should_scan(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(rel == s or rel.startswith(s + "/") for s in SKIP_DIRS):
        return False
    # A file that is itself stripped from the factory mirror cannot carry a link
    # that 404s there — and inside its own satellite export the relative link is
    # usually the correct one. Judge those in the satellite, not here.
    return not any(rel.startswith(s + "/") for s in ROOT_SATELLITES)


def main() -> int:
    only_docs = "--docs-only" in sys.argv
    fail = 0
    rel_hits: dict[str, list[str]] = {}
    stale_hits: dict[str, list[str]] = {}

    glob_root = ROOT / "docs" if only_docs else ROOT
    for md in sorted(glob_root.rglob("*.md")):
        if not should_scan(md):
            continue
        if only_docs and not md.is_relative_to(ROOT / "docs"):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        rel = md.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if SATellite_RE.search(line):
                rel_hits.setdefault(rel, []).append(f"  L{i}: {line.strip()[:120]}")
            if AICOM_STALE.search(line):
                stale_hits.setdefault(rel, []).append(f"  L{i}: {line.strip()[:120]}")

    print("=== Relative satellite links (404 on factory mirror) ===")
    if rel_hits:
        for f, lines in sorted(rel_hits.items()):
            print(f"FAIL {f} ({len(lines)})")
            for ln in lines[:3]:
                print(ln)
            if len(lines) > 3:
                print(f"  ... +{len(lines) - 3} more")
            fail += 1
    else:
        print("OK — none found")

    print("\n=== Stale aicom/blob/main/<satellite> URLs ===")
    if stale_hits:
        for f, lines in sorted(stale_hits.items()):
            print(f"FAIL {f} ({len(lines)})")
            for ln in lines[:2]:
                print(ln)
            if len(lines) > 2:
                print(f"  ... +{len(lines) - 2} more")
            fail += 1
    else:
        print("OK — none found")

    # ── The reverse direction ────────────────────────────────────────────────
    # The two checks above look OUT of the factory tree. This one looks out of a
    # SATELLITE: each satellite folder is rsynced to its repo root, so a link that
    # normalises above that folder has no target in the published repo. 157 such
    # links were live on GitHub — every one of them resolving fine in the monorepo,
    # which is exactly why nobody saw them.
    # Excluded from the factory mirror AND published to no satellite repo: these
    # trees exist only in the monorepo, where a relative link resolves, so there is
    # no published copy for it to 404 in. Reporting them made the audit red over
    # links that are correct everywhere they are ever read.
    monorepo_only = {"wiki", "independent", "pantheon"}
    print("\n=== Links escaping their satellite root (404 in the satellite repo) ===")
    escape_hits: dict[str, list[str]] = {}
    link_re = re.compile(r"\]\((?!https?://|mailto:|#|/)([^)\s]+?)(?:#[^)]*)?\)")
    for md in sorted(glob_root.rglob("*.md")):
        rel = md.relative_to(ROOT).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in SKIP_DIRS):
            continue
        home = next((s for s in ROOT_SATELLITES if rel.startswith(s + "/")), None)
        if not home or home in monorepo_only:
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for m in link_re.finditer(line):
                target = (md.parent / m.group(1)).resolve()
                try:
                    t = target.relative_to(ROOT).as_posix()
                except ValueError:
                    continue
                if t == home or t.startswith(home + "/"):
                    continue
                escape_hits.setdefault(rel, []).append(f"  L{i}: {m.group(1)}")
    if escape_hits:
        for f, lines in sorted(escape_hits.items()):
            print(f"FAIL {f} ({len(lines)})")
            for ln in lines[:3]:
                print(ln)
            if len(lines) > 3:
                print(f"  ... +{len(lines) - 3} more")
            fail += 1
    else:
        print("OK — none found")

    if fail:
        print(f"\n{fail} file(s) with issues.")
        print("Fix with: python3 scripts/fix_whitepaper_satellite_links.py")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
