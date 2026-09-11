#!/usr/bin/env python3
"""Generate the aimarket-plugins repo-root README from plugins/README.md.

The monorepo `plugins/README.md` is the single source of truth for the plugin
catalog. Its links are relative to the `plugins/` directory (e.g. `aimarket-tee/`).

In the published `aimarket-plugins` satellite the catalog lives at the REPO
ROOT, while the plugin packages sit one level down under `plugins/`. So the
catalog's links must be rewritten to be root-relative (e.g. `plugins/aimarket-tee/`)
before the file becomes the repo-root README.

Keeping a single source avoids the root README drifting from the per-folder
catalog. The repo-root README is intentionally MCP-forward so the Glama registry
— which indexes the repo-root README alongside `glama.json` + `Dockerfile` —
still surfaces the `aimarket-mcp-packager` MCP server.

Usage:
    build_plugins_root_readme.py <src plugins/README.md> <dst repo-root README.md>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Literal link rewrites — order matters: more specific patterns first.
LITERAL_REWRITES: list[tuple[str, str]] = [
    # provenance is vendored from aimarket-hub into plugins/aimarket-provenance
    (
        "](../aimarket-hub/plugins/aimarket-provenance/)",
        "](plugins/aimarket-provenance/)",
    ),
    # the hub's plugin loader dir lives in a different repo
    (
        "](../aimarket-hub/plugins/)",
        "](https://github.com/alexar76/aimarket-hub/tree/main/plugins/)",
    ),
    # ecosystem-wide killer-features doc lives in the aicom monorepo
    (
        "](../docs/killer-features.md)",
        "](https://github.com/alexar76/aicom/blob/main/docs/killer-features.md)",
    ),
    # plugins/docs/* — repo root is one level up from the catalog
    ("](docs/", "](plugins/docs/"),
]

# Plugin folder links: `](aimarket-foo/...)` -> `](plugins/aimarket-foo/...)`.
# Runs AFTER the literal rewrites so already-prefixed `](plugins/aimarket-...)`
# targets (e.g. provenance) are left untouched.
PLUGIN_LINK = re.compile(r"\]\((aimarket-[a-z0-9-]+/)")


def transform(text: str) -> str:
    for old, new in LITERAL_REWRITES:
        text = text.replace(old, new)
    return PLUGIN_LINK.sub(r"](plugins/\1", text)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {Path(argv[0]).name} <src> <dst>", file=sys.stderr)
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    dst.write_text(transform(src.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
