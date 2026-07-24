#!/usr/bin/env python3
"""Audit markdown for satellite links that 404 on alexar76/aicom factory mirror."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROOT_SATELLITES = (
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
ROOT_SAT_RE = "|".join(re.escape(s) for s in ROOT_SATELLITES)

SATellite_RE = re.compile(
    rf"\]\(\.\./(\.\./)?(\.\./)?({ROOT_SAT_RE})(?:/|#|\))"
)

AICOM_STALE = re.compile(
    r"https://github\.com/alexar76/aicom/blob/main/"
    r"(aimarket-|plugins/|argus/|oracles/|lottery/|acex/|"
    r"ai-service-mesh/|alien-monitor/|desktop-integrations/)"
)

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "data",
    "web/frontend/test-results",
}


def should_scan(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return not any(rel == s or rel.startswith(s + "/") for s in SKIP_DIRS)


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

    if fail:
        print(f"\n{fail} file(s) with issues.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
