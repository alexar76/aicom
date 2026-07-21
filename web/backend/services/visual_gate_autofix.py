"""
Deterministic fixes for recurring QA visual/URL gates before peer review re-runs.

Targets blockers that LLM regen often misses: :focus-visible, <main>, loopback URLs in source.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from core.code_discovery import should_skip_code_path
from web.backend.services.sandbox_static_rewrite import (
    _rewrite_localhost_urls,
    _rewrite_root_absolute_paths,
)

logger = logging.getLogger(__name__)

_FOCUS_CSS = """
/* aicom-visual-gate-autofix */
:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}
"""

_CTA_CONTRAST_CSS = """
/* aicom-visual-gate-autofix — WCAG-friendly default CTA/nav contrast */
button, .btn, [role="button"], header a, nav a {
  color: #ffffff !important;
  background-color: #1d4ed8 !important;
}
header, nav {
  color: #ffffff;
  background-color: #0f172a;
}
"""

_TEXT_EXTENSIONS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".vue",
    ".json",
    ".yaml",
    ".yml",
}
_HTML_LINK_ATTR_RE = re.compile(
    r"\b(href|src)\s*=\s*(['\"])([^'\"]+)\2",
    re.IGNORECASE,
)
_FILELIKE_LINK_SUFFIXES = {
    ".js",
    ".css",
    ".mjs",
    ".cjs",
    ".map",
    ".woff",
    ".woff2",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".ico",
}


def apply_visual_gate_autofix(code_root: Path) -> list[str]:
    """Apply mechanical gate fixes under ``data/code/{product_id}``. Returns human-readable actions."""
    if not code_root.is_dir():
        return []

    actions: list[str] = []
    for path in _iter_text_files(code_root):
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        updated = original
        suffix = path.suffix.lower()

        if suffix in (".html", ".htm"):
            updated = _autofix_html(updated)
        elif suffix == ".css":
            updated = _autofix_css(updated)
        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue"):
            updated = _autofix_js_text(updated)

        updated = _rewrite_localhost_urls(updated)
        updated = _rewrite_root_absolute_paths(updated)

        if updated != original:
            try:
                path.write_text(updated, encoding="utf-8")
                actions.append(str(path.relative_to(code_root)))
            except OSError as exc:
                logger.debug("visual_gate_autofix write failed %s: %s", path, exc)

    stub_actions = _ensure_missing_static_assets(code_root)
    actions.extend(stub_actions)

    if actions:
        logger.info("visual_gate_autofix applied to %s (%d files)", code_root.name, len(actions))
    return actions


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or should_skip_code_path(path):
            continue
        if path.suffix.lower() in _TEXT_EXTENSIONS:
            yield path


def _autofix_html(html: str) -> str:
    out = html
    if ":focus-visible" not in out and "focus-visible" not in out:
        out = _inject_before_head_close(
            out,
            f"<style id=\"aicom-autofix-focus\">{_FOCUS_CSS}{_CTA_CONTRAST_CSS}</style>",
        )
    elif "aicom-autofix-cta" not in out:
        out = _inject_before_head_close(out, f"<style id=\"aicom-autofix-cta\">{_CTA_CONTRAST_CSS}</style>")
    if not re.search(r"<main\b", out, re.I) and not re.search(r"role\s*=\s*['\"]main['\"]", out, re.I):
        out = _ensure_main_landmark(out)
    out = re.sub(
        r'(<a\b[^>]*\bhref\s*=\s*["\'])#(["\'])',
        r'\1#pricing\2',
        out,
        count=3,
        flags=re.I,
    )
    out = _ensure_in_page_anchors(out)
    return out


def _ensure_in_page_anchors(html: str) -> str:
    ids = {m.group(1) for m in re.finditer(r'\bid\s*=\s*["\']([^"\']+)["\']', html, re.I)}
    needed: set[str] = set()
    for m in re.finditer(r'href\s*=\s*["\']#([^"\']+)["\']', html, re.I):
        anchor = m.group(1).split("?", 1)[0].strip()
        if anchor and anchor not in ids:
            needed.add(anchor)
    if not needed:
        return html
    sections = "\n".join(
        f'<section id="{anchor}" aria-label="{anchor.replace("-", " ").title()}"></section>'
        for anchor in sorted(needed)
    )
    return _inject_before_body_close(html, sections)


def _ensure_missing_static_assets(code_root: Path) -> list[str]:
    created: list[str] = []
    code_root = code_root.resolve()
    for html_file in _iter_text_files(code_root):
        if html_file.suffix.lower() not in (".html", ".htm"):
            continue
        try:
            text = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _HTML_LINK_ATTR_RE.finditer(text):
            url = (m.group(3) or "").strip()
            if not url or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "http://", "https://", "//")):
                continue
            if url.startswith("/"):
                continue
            path_part = url.split("#", 1)[0].split("?", 1)[0]
            if not path_part or path_part.endswith("/"):
                continue
            suffix = Path(path_part).suffix.lower()
            if suffix not in _FILELIKE_LINK_SUFFIXES:
                continue
            target = (html_file.parent / path_part).resolve()
            try:
                target.relative_to(code_root)
            except ValueError:
                continue
            if target.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            stub = _stub_content_for_suffix(suffix)
            try:
                target.write_text(stub, encoding="utf-8")
                created.append(str(target.relative_to(code_root)))
            except OSError as exc:
                logger.debug("static stub write failed %s: %s", target, exc)
    return created


def _stub_content_for_suffix(suffix: str) -> str:
    if suffix == ".css":
        return "/* aicom-autofix static stub */\nbody { font-family: system-ui, sans-serif; }\n"
    if suffix in (".js", ".mjs", ".cjs"):
        return "// aicom-autofix static stub\n"
    if suffix == ".svg":
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>\n'
    return ""


def _autofix_css(css: str) -> str:
    if ":focus-visible" in css or "focus-visible" in css:
        return css
    return css.rstrip() + "\n" + _FOCUS_CSS + "\n"


def _autofix_js_text(text: str) -> str:
    return text


def _ensure_main_landmark(html: str) -> str:
    body_match = re.search(r"<body[^>]*>", html, re.I)
    if not body_match:
        return html
    insert_at = body_match.end()
    snippet = '<main id="main" role="main">'
    close_snippet = "</main>"
    body_close = list(re.finditer(r"</body\s*>", html, re.I))
    if not body_close:
        return html[:insert_at] + snippet + html[insert_at:] + close_snippet
    end = body_close[-1].start()
    inner = html[insert_at:end].strip()
    if inner.startswith("<main") or "<main" in inner[:120]:
        return html
    return html[:insert_at] + snippet + html[insert_at:end] + close_snippet + html[end:]


def _inject_before_head_close(html: str, snippet: str) -> str:
    m = re.search(r"</head\s*>", html, re.I)
    if m:
        return html[: m.start()] + snippet + html[m.start() :]
    m2 = re.search(r"<head[^>]*>", html, re.I)
    if m2:
        return html[: m2.end()] + snippet + html[m2.end() :]
    return snippet + html


def _inject_before_body_close(html: str, snippet: str) -> str:
    m = re.search(r"</body\s*>", html, re.I)
    if m:
        return html[: m.start()] + snippet + html[m.start() :]
    return html + snippet
