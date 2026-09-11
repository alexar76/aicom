"""The site's CSP must allow the remote stylesheets the site itself loads.

`styles/globals.css` starts with an `@import url('https://fonts.googleapis.com/...')` for
Inter, Space Grotesk and JetBrains Mono. The default frontend CSP shipped
`style-src 'self' 'unsafe-inline'`, so the browser refused that import on every page and the
whole UI fell back to system fonts — with the reason visible only in the console. The same
repo already got this right in `web/backend/api/agents_page.py`; only the frontend copy of
the policy was missing the origin.

This scans the CSS for the origins it actually reaches out to and requires the policy to name
them, so adding another remote stylesheet cannot silently break rendering again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "web" / "frontend" / "styles" / "globals.css"
HEADERS_TS = ROOT / "web" / "frontend" / "lib" / "securityHeaders.ts"

# `@import url("https://host/...")`, with or without quotes.
_IMPORT_URL = re.compile(r"@import\s+url\(\s*['\"]?(https://[^'\")\s]+)", re.I)


def _csp_directive(name: str) -> str:
    """Pull one directive out of DEFAULT_FRONTEND_CSP without executing TypeScript."""
    text = HEADERS_TS.read_text()
    block = text[text.index("DEFAULT_FRONTEND_CSP") :]
    block = block[: block.index("].join(")]
    # Drop whole-line comments so a directive quoted in prose cannot satisfy the assertion.
    # Splitting on "//" anywhere would truncate every https:// URL in the policy — which is
    # exactly the value being checked.
    lines = [ln for ln in block.splitlines() if not ln.lstrip().startswith("//")]
    for line in lines:
        # The directive VALUE contains single quotes ('self', 'unsafe-inline'), so the closing
        # delimiter has to be the same double quote that opened it — a generic ["'] class
        # stops at 'self' and reports the directive as empty.
        m = re.search(r'"' + re.escape(name) + r'\s+([^"]*)"', line)
        if m:
            return m.group(1)
    raise AssertionError(f"{name} not found in DEFAULT_FRONTEND_CSP")


def _remote_stylesheet_origins() -> set[str]:
    origins = set()
    for url in _IMPORT_URL.findall(CSS.read_text()):
        origins.add("https://" + url.split("/", 3)[2])
    return origins


def test_globals_css_still_imports_remote_fonts():
    """Guard the premise: if the import is gone, this whole test should be revisited."""
    assert _remote_stylesheet_origins(), (
        "globals.css no longer imports a remote stylesheet — the fonts may now be self-hosted, "
        "in which case the CSP allowance below can be dropped rather than maintained"
    )


@pytest.mark.parametrize("origin", sorted(_remote_stylesheet_origins()))
def test_style_src_allows_every_stylesheet_the_css_imports(origin):
    style_src = _csp_directive("style-src")
    assert origin in style_src, (
        f"globals.css imports {origin} but style-src is {style_src!r} — the browser blocks the "
        "import and every page renders in fallback fonts"
    )


def test_font_src_allows_the_files_google_fonts_serves():
    """A googleapis stylesheet is useless without the gstatic origin it points at."""
    if "https://fonts.googleapis.com" not in _remote_stylesheet_origins():
        pytest.skip("no Google Fonts stylesheet imported")
    font_src = _csp_directive("font-src")
    assert "https://fonts.gstatic.com" in font_src, (
        f"font-src is {font_src!r} — the stylesheet loads but the font files it references "
        "are blocked, which looks identical to no webfonts at all"
    )
