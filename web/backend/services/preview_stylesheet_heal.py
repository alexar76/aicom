"""Pair generated HTML with the CSS that actually styles its classes.

Factory models often emit two landings (root ``index.html`` + ``frontend/index.html``)
and cross-link stylesheets. Sandbox preview then paints browser-default black text
on a white page even though a matching theme file exists next to the HTML.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from core.code_discovery import iter_product_files, should_skip_code_path

logger = logging.getLogger(__name__)

_CLASS_ATTR_RE = re.compile(r"\bclass(?:Name)?\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_ID_ATTR_RE = re.compile(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_CSS_CLASS_RE = re.compile(r"(?<![\w-])\.([A-Za-z_][\w-]*)")
_CSS_ID_RE = re.compile(r"(?<![\w-])#([A-Za-z_][\w-]*)")
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
_HREF_RE = re.compile(r"\bhref\s*=\s*(['\"])([^'\"]+)\1", re.I)
_REL_STYLESHEET_RE = re.compile(r"""\brel\s*=\s*['"][^'"]*stylesheet[^'"]*['"]""", re.I)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_CSS_URL_RE = re.compile(r"url\([^)]*\)", re.I)

_THEME_CSS_NAMES = (
    "style.css",
    "styles.css",
    "main.css",
    "app.css",
    "index.css",
    "theme.css",
)
_FONT_CSS_NAMES = {"fonts.css", "font.css", "typeface.css"}
_REMOTE_PREFIXES = ("http://", "https://", "//", "data:")
_FIT_REWRITE_MARGIN = 3

# Override earlier sandbox candidate only when nested HTML is clearly the styled one.
PREVIEW_FIT_OVERRIDE_MARGIN = 3


def html_style_tokens(html: str) -> set[str]:
    tokens: set[str] = set()
    for m in _CLASS_ATTR_RE.finditer(html or ""):
        for raw in m.group(1).split():
            name = raw.strip().lower()
            if len(name) >= 2:
                tokens.add(f".{name}")
    for m in _ID_ATTR_RE.finditer(html or ""):
        name = (m.group(1) or "").strip().lower()
        if len(name) >= 2:
            tokens.add(f"#{name}")
    return tokens


def css_style_tokens(css: str) -> set[str]:
    cleaned = _CSS_URL_RE.sub("", _CSS_COMMENT_RE.sub("", css or ""))
    tokens = {f".{m.group(1).lower()}" for m in _CSS_CLASS_RE.finditer(cleaned)}
    tokens |= {f"#{m.group(1).lower()}" for m in _CSS_ID_RE.finditer(cleaned)}
    return tokens


def stylesheet_fit(html_tokens: set[str], css: str) -> int:
    if not html_tokens:
        return 0
    return len(html_tokens & css_style_tokens(css))


def is_font_stylesheet(path: Path, css: str) -> bool:
    if path.name.lower() in _FONT_CSS_NAMES:
        return True
    low = (css or "").lower()
    has_font = "@font-face" in low or "fonts.googleapis" in low or "fonts.gstatic" in low
    class_count = sum(1 for t in css_style_tokens(css) if t.startswith("."))
    return has_font and class_count < 4


def _is_remote_href(href: str) -> bool:
    low = (href or "").strip().lower()
    return not low or low.startswith(_REMOTE_PREFIXES) or low.startswith(("mailto:", "javascript:"))


def linked_stylesheet_hrefs(html: str) -> list[str]:
    hrefs: list[str] = []
    for tag in _LINK_TAG_RE.findall(html or ""):
        if not _REL_STYLESHEET_RE.search(tag):
            continue
        hm = _HREF_RE.search(tag)
        if hm:
            hrefs.append(hm.group(2).strip())
    return hrefs


def linked_local_css_paths(html_path: Path, code_root: Path) -> list[Path]:
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[Path] = []
    root = code_root.resolve()
    for href in linked_stylesheet_hrefs(html):
        if _is_remote_href(href):
            continue
        path_part = href.split("#", 1)[0].split("?", 1)[0]
        if not path_part or path_part.endswith("/"):
            continue
        if path_part.startswith("/"):
            candidate = (code_root / path_part.lstrip("/")).resolve()
        else:
            candidate = (html_path.parent / path_part).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    return found


def preview_fit_score(code_root: Path, rel: str) -> int:
    """How well currently *linked* local CSS matches classes/ids in this HTML."""
    html_path = code_root / rel
    if not html_path.is_file():
        return 0
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    tokens = html_style_tokens(html)
    if not tokens:
        return 0
    best = 0
    for css_path in linked_local_css_paths(html_path, code_root):
        try:
            css = css_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_font_stylesheet(css_path, css):
            continue
        if "aicom-autofix static stub" in css:
            continue
        best = max(best, stylesheet_fit(tokens, css))
    return best


def _theme_css_candidates(html_path: Path, code_root: Path) -> list[Path]:
    dirs = [
        html_path.parent,
        code_root,
        code_root / "frontend",
        code_root / "static",
        code_root / "css",
        code_root / "assets",
        code_root / "public",
        code_root / "frontend" / "css",
    ]
    found: list[Path] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for name in _THEME_CSS_NAMES:
            path = directory / name
            if not path.is_file() or path in found:
                continue
            if should_skip_code_path(path):
                continue
            found.append(path)
    return found


def _rel_href(html_path: Path, css_path: Path) -> str:
    return os.path.relpath(css_path, html_path.parent).replace("\\", "/")


def _replace_link_href(html: str, old_href: str, new_href: str) -> str:
    def _repl(tag: str) -> str:
        if not _REL_STYLESHEET_RE.search(tag):
            return tag
        hm = _HREF_RE.search(tag)
        if not hm or hm.group(2).strip() != old_href:
            return tag
        start, end = hm.start(2), hm.end(2)
        return tag[:start] + new_href + tag[end:]

    return _LINK_TAG_RE.sub(lambda m: _repl(m.group(0)), html)


def _append_stylesheet_link(html: str, href: str) -> str:
    snippet = f'<link rel="stylesheet" href="{href}">\n'
    close = re.search(r"</head\s*>", html, re.I)
    if close:
        return html[: close.start()] + snippet + html[close.start() :]
    return snippet + html


def heal_html_stylesheet_links(html_path: Path, code_root: Path) -> bool:
    """Rewrite local stylesheet hrefs when a nearby CSS file fits the markup far better."""
    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    tokens = html_style_tokens(html)
    if len(tokens) < 2:
        return False

    hrefs = linked_stylesheet_hrefs(html)
    linked_theme: list[tuple[str, Path, int]] = []
    keep_hrefs: set[str] = set()
    for href in hrefs:
        if _is_remote_href(href):
            keep_hrefs.add(href)
            continue
        path_part = href.split("#", 1)[0].split("?", 1)[0]
        if path_part.startswith("/"):
            css_path = (code_root / path_part.lstrip("/")).resolve()
        else:
            css_path = (html_path.parent / path_part).resolve()
        try:
            css = css_path.read_text(encoding="utf-8", errors="replace") if css_path.is_file() else ""
        except OSError:
            css = ""
        if css_path.is_file() and is_font_stylesheet(css_path, css):
            keep_hrefs.add(href)
            continue
        fit = stylesheet_fit(tokens, css) if css else 0
        linked_theme.append((href, css_path, fit))

    best_linked = max((fit for _, _, fit in linked_theme), default=0)
    best_path: Path | None = None
    best_fit = best_linked
    for candidate in _theme_css_candidates(html_path, code_root):
        try:
            css = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_font_stylesheet(candidate, css) or "aicom-autofix static stub" in css:
            continue
        fit = stylesheet_fit(tokens, css)
        if fit > best_fit:
            best_fit = fit
            best_path = candidate

    if best_path is None or best_fit < best_linked + _FIT_REWRITE_MARGIN:
        return False
    if best_fit < _FIT_REWRITE_MARGIN:
        return False

    new_href = _rel_href(html_path, best_path)
    already = any(
        (html_path.parent / href).resolve() == best_path.resolve()
        for href in hrefs
        if not _is_remote_href(href)
    )
    if already:
        return False

    updated = html
    weak = [href for href, _, fit in linked_theme if fit <= best_linked]
    if weak:
        updated = _replace_link_href(updated, weak[0], new_href)
    else:
        updated = _append_stylesheet_link(updated, new_href)

    if updated == html:
        return False
    try:
        html_path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        logger.debug("stylesheet heal write failed %s: %s", html_path, exc)
        return False
    logger.info(
        "healed stylesheet %s → %s (fit %d → %d)",
        html_path.name,
        new_href,
        best_linked,
        best_fit,
    )
    return True


def heal_product_stylesheets(code_root: Path) -> list[str]:
    """Heal every HTML file under the product code root. Returns relative paths changed."""
    if not code_root.is_dir():
        return []
    changed: list[str] = []
    for path in iter_product_files(code_root, "*"):
        if path.suffix.lower() not in (".html", ".htm"):
            continue
        if heal_html_stylesheet_links(path, code_root):
            try:
                changed.append(str(path.relative_to(code_root)))
            except ValueError:
                changed.append(path.name)
    return changed
