"""The frontend CSP must allow the stylesheets the site loads — and nothing more.

This started as a one-way check. `styles/globals.css` opened with an
`@import url('https://fonts.googleapis.com/...')` while the default CSP shipped
`style-src 'self' 'unsafe-inline'`, so the browser refused the import on every page and the
whole UI fell back to system fonts, with the reason visible only in the console.

The fonts are now served from `public/fonts/`, so the fix is no longer "allow Google" but
"do not need to". Both halves are worth pinning, because either can regress on its own:

  * a remote `@import` added back without widening the policy renders in fallback fonts;
  * a policy that keeps naming an origin nothing loads from is a standing permission to ship
    a third-party request — the thing self-hosting was meant to remove.

The third check is the one that would have caught a bad self-hosting job: a local `@import`
that points at a file which is not there fails exactly like the blocked remote one did.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "web" / "frontend" / "styles" / "globals.css"
PUBLIC = ROOT / "web" / "frontend" / "public"
HEADERS_TS = ROOT / "web" / "frontend" / "lib" / "securityHeaders.ts"

# `@import url("...")`, remote or root-relative, with or without quotes.
_IMPORT_URL = re.compile(r"@import\s+url\(\s*['\"]?([^'\")\s]+)", re.I)

# Origins that only ever appear here to serve fonts, so their presence in the policy is
# evidence a page still reaches out to them.
THIRD_PARTY_FONT_ORIGINS = ("fonts.googleapis.com", "fonts.gstatic.com")


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


def _imports() -> list[str]:
    return _IMPORT_URL.findall(CSS.read_text())


def _remote_origins() -> set[str]:
    return {"https://" + u.split("/", 3)[2] for u in _imports() if u.startswith("https://")}


@pytest.mark.parametrize("origin", sorted(_remote_origins()) or [None])
def test_style_src_allows_every_remote_stylesheet_the_css_imports(origin):
    if origin is None:
        pytest.skip("globals.css imports nothing remote — nothing to allow")
    style_src = _csp_directive("style-src")
    assert origin in style_src, (
        f"globals.css imports {origin} but style-src is {style_src!r} — the browser blocks the "
        "import and every page renders in fallback fonts"
    )


@pytest.mark.parametrize("host", THIRD_PARTY_FONT_ORIGINS)
def test_policy_does_not_allow_font_origins_nothing_loads_from(host):
    """Permission and use have to stay in step, in the direction that matters for privacy.

    A stale `font-src https://fonts.gstatic.com` does not break rendering, which is why it
    would survive review — and why it needs a test. It leaves the door open for a page to
    start disclosing every visitor's address to Google again without anything failing.
    """
    if any(host in origin for origin in _remote_origins()):
        pytest.skip(f"globals.css genuinely imports from {host}")
    policy = " ".join(_csp_directive(d) for d in ("style-src", "font-src"))
    assert host not in policy, (
        f"nothing in globals.css loads from {host}, but the CSP still allows it — drop it, or a "
        "future edit can reintroduce the third-party font request unnoticed"
    )


@pytest.mark.parametrize("href", [u for u in _imports() if u.startswith("/")] or [None])
def test_locally_imported_stylesheets_exist_on_disk(href):
    """A self-hosted font that 404s looks exactly like a blocked remote one."""
    if href is None:
        pytest.skip("globals.css imports nothing from our own origin")
    target = PUBLIC / href.lstrip("/")
    assert target.is_file(), (
        f"globals.css imports {href} but {target.relative_to(ROOT)} does not exist — every page "
        "renders in fallback fonts, silently"
    )
    faces = re.findall(r"url\(([^)]+\.woff2)\)", target.read_text())
    assert faces, f"{href} declares no woff2 face — the mirror ran but produced nothing"
    missing = [f for f in faces if not (target.parent / f.strip("'\"")).is_file()]
    assert not missing, f"{href} points at font files that are not there: {missing[:3]}"
