"""
Optional fixed-corner ""Built with AI-Factory"" badge on generated static HTML.

Configured via ``general.site_badge_*`` in ``/app/config.yaml`` (Admin → Settings).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.paths import config_path
from core.config_merge import load_merged_config

logger = logging.getLogger(__name__)

CONFIG_PATH = config_path()


def _read_general() -> dict[str, Any]:
    try:
        raw = load_merged_config(CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("site_badge: could not read config: %s", e)
        return {}


def badge_snippet(link_url: str) -> str:
    """Inline script appends a fixed bottom-right ""Built with AI-Factory"" link."""
    js_url = json.dumps(link_url)
    return (
        "<!-- AI-Factory site badge -->"
        "<script>"
        "(function(){"
        "var u=" + js_url + ";"
        "if(!u||document.getElementById('aifactory-built-badge'))return;"
        "var a=document.createElement('a');"
        "a.id='aifactory-built-badge';"
        "a.href=u;"
        "a.target='_blank';"
        "a.rel='noopener noreferrer';"
        "a.setAttribute('aria-label','Built with AI-Factory');"
        "a.textContent='Built with AI-Factory';"
        "a.style.cssText="
        "'position:fixed;bottom:14px;right:14px;z-index:2147483647;'"
        "+'font:600 12px/1.35 system-ui,-apple-system,sans-serif;'"
        "+'color:#fff;background:rgba(15,23,42,.78);backdrop-filter:blur(8px);'"
        "+'padding:8px 12px;border-radius:10px;text-decoration:none;'"
        "+'box-shadow:0 2px 12px rgba(0,0,0,.25);transition:opacity .2s';"
        "a.onmouseenter=function(){this.style.opacity='1';};"
        "a.onmouseleave=function(){this.style.opacity='0.92';};"
        "document.body.appendChild(a);"
        "})();"
        "</script>"
    )


def inject_site_badge_if_enabled(data_root: Path, product_id: str) -> None:
    general = _read_general()
    if not general.get("site_badge_enabled"):
        return
    link = str(general.get("site_badge_link_url") or "").strip()
    if not link or not (link.startswith("http://") or link.startswith("https://")):
        logger.debug("site_badge: disabled or invalid site_badge_link_url")
        return

    code_dir = data_root / "code" / product_id
    if not code_dir.is_dir():
        return

    snippet = badge_snippet(link)
    marker = "aifactory-built-badge"

    for html_file in code_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if marker in content:
            continue
        if "</body>" in content:
            content = content.replace("</body>", snippet + "\n</body>", 1)
        else:
            content = content + "\n" + snippet
        try:
            html_file.write_text(content, encoding="utf-8")
        except Exception:
            continue
