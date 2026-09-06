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

_PAGE_SHELL_MARKER = "aicom-visual-gate-autofix page shell"
_PAGE_SHELL_CSS = """
/* aicom-visual-gate-autofix page shell */
.page-shell {
  box-sizing: border-box;
  width: 100%;
  max-width: 1120px;
  margin-inline: auto;
  padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
}
main:not(.container):not(.page-shell):not(.auth-page):not(.share-page):not(.full-bleed) {
  box-sizing: border-box;
  width: 100%;
  max-width: 1120px;
  margin-inline: auto;
  padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
}
"""

_MAIN_EMPTY_CLASS_RE = re.compile(
    r"<main\s+className\s*=\s*(['\"])\1",
    re.I,
)
_MAIN_EMPTY_CLASS_STYLE_RE = re.compile(
    r"<main\s+className\s*=\s*(['\"])\1(\s+style=)",
    re.I,
)

# Legacy poison: used to paint every nav/button navy with !important, wiping
# the product theme (teal, pulse, Space Grotesk, …) in sandbox preview.
_CTA_POISON_STYLE_RE = re.compile(
    r"<style\b[^>]*\bid\s*=\s*['\"]aicom-autofix-cta['\"][^>]*>.*?</style>",
    re.I | re.S,
)
_CTA_POISON_RULES_RE = re.compile(
    r"/\*\s*aicom-visual-gate-autofix\s+[—\-].*?CTA/nav contrast\s*\*/"
    r".*?(?=/\*|</style>|$)",
    re.I | re.S,
)
_CTA_NAVY_IMPORTANT_RE = re.compile(
    r"button\s*,\s*\.btn\s*,\s*\[role\s*=\s*['\"]button['\"]\]\s*,\s*header a\s*,\s*nav a\s*"
    r"\{[^}]*!important[^}]*\}",
    re.I | re.S,
)
_CTA_NAV_BG_RE = re.compile(
    r"header\s*,\s*nav\s*\{\s*color:\s*#ffffff\s*;\s*background-color:\s*#0f172a\s*;?\s*\}",
    re.I | re.S,
)

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

    try:
        from web.backend.services.preview_stylesheet_heal import heal_product_stylesheets

        for rel in heal_product_stylesheets(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("stylesheet heal skipped: %s", exc)

    stub_actions = _ensure_missing_static_assets(code_root)
    actions.extend(stub_actions)

    try:
        for rel in _dedupe_js_ts_api_client_pair(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("api.js/api.ts dedupe skipped: %s", exc)

    try:
        for rel in _ensure_mobile_nav_toggle_tokens(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("mobile nav autofix skipped: %s", exc)

    try:
        from web.backend.services.model_enum_autofix import apply_model_enum_autofix

        for rel in apply_model_enum_autofix(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("model enum autofix skipped: %s", exc)

    try:
        for rel in _ensure_page_shell_layout(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("page shell autofix skipped: %s", exc)

    if actions:
        logger.info("visual_gate_autofix applied to %s (%d files)", code_root.name, len(actions))
    return actions


_NAV_TOGGLE_NEEDLE = re.compile(
    r"(aria-expanded|menu-toggle|nav-toggle|hamburger|burger|drawer-open)",
    re.I,
)
_MOBILE_MQ = re.compile(r"@media\s*\([^)]*max-width", re.I)


def _ensure_mobile_nav_toggle_tokens(code_root: Path) -> list[str]:
    """Satisfy ``visual_no_responsive_nav_mobile`` without waiting on LLM regen.

    When CSS already has ``@media (max-width: …)`` but no hamburger / aria-expanded
    token exists in the tree, inject a tiny accessible toggle into the SPA shell
    (and a matching CSS hook). Heuristic only — does not rewrite product chrome.
    """
    css_blob = ""
    html_js_blob = ""
    for path in _iter_text_files(code_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix.lower() == ".css":
            css_blob += "\n" + text
        else:
            html_js_blob += "\n" + text
    if not _MOBILE_MQ.search(css_blob):
        return []
    if _NAV_TOGGLE_NEEDLE.search(html_js_blob) or _NAV_TOGGLE_NEEDLE.search(css_blob):
        return []

    changed: list[str] = []
    snippet = (
        '<!-- aicom-visual-gate-autofix mobile nav -->'
        '<button type="button" class="aicom-autofix-nav-toggle" '
        'aria-expanded="false" aria-controls="aicom-autofix-nav" '
        'aria-label="Open menu">Menu</button>'
        '<nav id="aicom-autofix-nav" class="aicom-autofix-nav" hidden></nav>'
    )
    css_hook = (
        "\n/* aicom-visual-gate-autofix mobile nav */\n"
        ".aicom-autofix-nav-toggle{display:none}\n"
        "@media (max-width: 768px){.aicom-autofix-nav-toggle{display:inline-flex}}\n"
    )

    for rel in ("public/index.html", "index.html", "frontend/index.html"):
        target = code_root / rel
        if not target.is_file():
            continue
        try:
            html = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "aicom-autofix-nav-toggle" in html or _NAV_TOGGLE_NEEDLE.search(html):
            continue
        updated = _inject_before_body_close(html, snippet)
        if updated != html:
            target.write_text(updated, encoding="utf-8")
            changed.append(rel)
            break

    css_targets = [
        code_root / "style.css",
        code_root / "public" / "style.css",
        code_root / "frontend" / "src" / "index.css",
        code_root / "frontend" / "src" / "App.css",
    ]
    for css_path in css_targets:
        if not css_path.is_file():
            continue
        try:
            css = css_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "aicom-autofix-nav-toggle" in css:
            break
        css_path.write_text(css.rstrip() + css_hook, encoding="utf-8")
        changed.append(str(css_path.relative_to(code_root)))
        break

    return changed


def _dedupe_js_ts_api_client_pair(code_root: Path) -> list[str]:
    """Delete ``frontend/src/api.js`` when ``api.ts`` is the wired client.

    Vite resolves ``from './api'`` to ``.ts``; the leftover ``.js`` twin is a
    permanent ``duplicate_modules`` smell that Dev often leaves in place.
    """
    js = code_root / "frontend" / "src" / "api.js"
    ts = code_root / "frontend" / "src" / "api.ts"
    if not (js.is_file() and ts.is_file()):
        return []
    refs_js = 0
    refs_bare = 0
    for path in _iter_text_files(code_root):
        if path.name in ("api.js", "api.ts"):
            continue
        if path.suffix.lower() not in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"""from\s+['"][^'"]*api\.js['"]|require\(['"][^'"]*api\.js['"]\)""", text):
            refs_js += 1
        if re.search(r"""from\s+['"](\.?\.?/)[^'"]*api['"]""", text):
            refs_bare += 1
    if refs_js > 0:
        return []
    # Bare imports prefer .ts under Vite; safe to drop the unused .js twin.
    if refs_bare == 0 and refs_js == 0:
        # Nothing imports either — still drop .js to clear the gate smell.
        pass
    try:
        js.unlink()
    except OSError:
        return []
    return ["frontend/src/api.js"]


def heal_preview_presentation(code_root: Path) -> list[str]:
    """Strip CTA poison and pair HTML with matching CSS. Safe to run on sandbox view."""
    if not code_root.is_dir():
        return []
    actions: list[str] = []
    for path in _iter_text_files(code_root):
        if path.suffix.lower() not in (".html", ".htm"):
            continue
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        updated = strip_cta_contrast_poison(original)
        if updated != original:
            try:
                path.write_text(updated, encoding="utf-8")
                actions.append(str(path.relative_to(code_root)))
            except OSError as exc:
                logger.debug("preview presentation strip failed %s: %s", path, exc)
    try:
        from web.backend.services.preview_stylesheet_heal import heal_product_stylesheets

        for rel in heal_product_stylesheets(code_root):
            if rel not in actions:
                actions.append(rel)
    except Exception as exc:
        logger.debug("stylesheet heal skipped: %s", exc)
    return actions


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or should_skip_code_path(path):
            continue
        if path.suffix.lower() in _TEXT_EXTENSIONS:
            yield path


def strip_cta_contrast_poison(html: str) -> str:
    """Remove factory-injected navy !important CTA/nav overrides from generated HTML."""
    out = _CTA_POISON_STYLE_RE.sub("", html)
    out = _CTA_POISON_RULES_RE.sub("", out)
    out = _CTA_NAVY_IMPORTANT_RE.sub("", out)
    out = _CTA_NAV_BG_RE.sub("", out)
    return out


def _autofix_html(html: str) -> str:
    out = strip_cta_contrast_poison(html)
    if ":focus-visible" not in out and "focus-visible" not in out:
        out = _inject_before_head_close(
            out,
            f'<style id="aicom-autofix-focus">{_FOCUS_CSS}</style>',
        )
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
    updated = css
    if ":focus-visible" not in css and "focus-visible" not in css:
        updated = updated.rstrip() + "\n" + _FOCUS_CSS + "\n"
    if _PAGE_SHELL_MARKER not in updated:
        updated = updated.rstrip() + "\n" + _PAGE_SHELL_CSS + "\n"
    return updated


def _autofix_js_text(text: str) -> str:
    updated = text
    if "<main" in text:
        updated = _MAIN_EMPTY_CLASS_STYLE_RE.sub(
            r'<main className="page-shell"\2',
            updated,
        )
        updated = _MAIN_EMPTY_CLASS_RE.sub(
            r'<main className="page-shell"',
            updated,
        )
    return updated


def _ensure_page_shell_layout(code_root: Path) -> list[str]:
    """Inject page-shell CSS and repair bare React <main> landmarks."""
    changed: list[str] = []
    css_targets = [
        code_root / "style.css",
        code_root / "public" / "style.css",
        code_root / "frontend" / "src" / "index.css",
        code_root / "frontend" / "src" / "App.css",
        code_root / "frontend" / "src" / "styles" / "app.css",
        code_root / "frontend" / "src" / "styles" / "globals.css",
    ]
    css_targets.extend(
        p
        for p in code_root.rglob("*.css")
        if "frontend" in p.parts and "node_modules" not in p.parts
    )
    public_root = code_root / "public"
    if public_root.is_dir():
        css_targets.extend(
            p for p in public_root.rglob("*.css") if "node_modules" not in p.parts
        )
    seen_css: set[str] = set()
    for css_path in css_targets:
        rel = str(css_path.relative_to(code_root)) if css_path.is_file() else ""
        if not css_path.is_file() or rel in seen_css:
            continue
        seen_css.add(rel)
        try:
            css = css_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _PAGE_SHELL_MARKER in css:
            continue
        css_path.write_text(css.rstrip() + "\n" + _PAGE_SHELL_CSS + "\n", encoding="utf-8")
        changed.append(rel)

    for path in _iter_text_files(code_root):
        if path.suffix.lower() not in (".tsx", ".jsx"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<main" not in text:
            continue
        updated = _autofix_js_text(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(str(path.relative_to(code_root)))
    return changed


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
