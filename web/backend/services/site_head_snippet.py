"""
Optional extra markup in ``<head>`` of generated static HTML (GA, Yandex.Metrica, etc.).

Configured via ``general.published_site_head_html`` in ``config.yaml`` (Admin → Settings).
Injected when Developer completes — same hook as ``site_badge``.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))
MARKER_BEGIN = "aifactory-published-site-head begin"
MARKER_END = "aifactory-published-site-head end"
MAX_SNIPPET_CHARS = 100_000


def _read_general() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.is_file():
            return {}
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("site_head_snippet: could not read config: %s", e)
        return {}


def _wrap_snippet(snippet: str) -> str:
    body = snippet.strip()
    return (
        f"<!-- {MARKER_BEGIN} -->\n"
        f"{body}\n"
        f"<!-- {MARKER_END} -->\n"
    )


def inject_published_site_head_if_configured(data_root: Path, product_id: str) -> None:
    general = _read_general()
    raw = str(general.get("published_site_head_html") or "")
    snippet = raw.strip()
    if not snippet:
        return
    if len(snippet) > MAX_SNIPPET_CHARS:
        logger.warning("site_head_snippet: snippet exceeds max length, truncating")
        snippet = snippet[:MAX_SNIPPET_CHARS]

    block = _wrap_snippet(snippet)
    code_dir = data_root / "code" / product_id
    if not code_dir.is_dir():
        return

    close_head = re.compile(r"</head\s*>", re.IGNORECASE)
    open_head = re.compile(r"<head[^>]*>", re.IGNORECASE)

    for html_file in code_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER_BEGIN in content:
            continue
        m_close = close_head.search(content)
        if m_close:
            new_content = content[: m_close.start()] + block + content[m_close.start() :]
        else:
            m_open = open_head.search(content)
            if not m_open:
                logger.debug("site_head_snippet: no <head> in %s, skip", html_file)
                continue
            new_content = content[: m_open.end()] + "\n" + block + content[m_open.end() :]
        try:
            html_file.write_text(new_content, encoding="utf-8")
        except Exception:
            continue
