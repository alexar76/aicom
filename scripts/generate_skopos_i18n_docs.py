#!/usr/bin/env python3
"""Render SKOPOS in-app guides (20 languages) from docs/i18n/guides.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKOPOS_PKG = ROOT / "skopos"
DOCS = SKOPOS_PKG / "docs"
I18N = DOCS / "i18n"
GUIDE_DIR_NAME = "guide"

sys.path.insert(0, str(SKOPOS_PKG))
from skopos.docs_i18n_render import render_all_guides  # noqa: E402
from skopos.docs_i18n_translations import LANG_OVERLAYS  # noqa: E402
from skopos.docs_i18n_ui import UI_STRINGS  # noqa: E402


def main() -> None:
    guides = render_all_guides(LANG_OVERLAYS)
    out_json = I18N / "guides.json"
    out_json.write_text(json.dumps(guides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for lang, sections in guides.items():
        base = DOCS / lang / GUIDE_DIR_NAME
        base.mkdir(parents=True, exist_ok=True)
        for slug, body in sections.items():
            (base / f"{slug}.md").write_text(body.rstrip() + "\n", encoding="utf-8")
        print(f"  {lang}: {len(sections)} sections")

    print(f"Wrote {len(guides)} languages → {DOCS}/{{lang}}/{GUIDE_DIR_NAME}/")

    ui_json = I18N / "ui.json"
    ui_json.write_text(json.dumps(UI_STRINGS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(UI_STRINGS)} UI locales → {ui_json}")


if __name__ == "__main__":
    main()
