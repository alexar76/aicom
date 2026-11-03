"""The `<link rel="canonical">` every HTML page of the hub carries.

Search engines indexed the reference hub under three names: modelmarket.dev,
www.modelmarket.dev and uni.modelmarket.dev all served the same title with no canonical, and
?utm_ and ?ref= links made more copies of each page. The canonical names the page under the
operator's public address (AIMARKET_HUB_URL) and keeps only ?lang=, because each language is
a page of its own. A hub without a public https address gets none: pointing search engines
at http://localhost would be worse than saying nothing.
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urlparse

# The languages the hub pages translate into; English is the page without ?lang=.
LANGS = ("ru", "es", "fr", "zh")

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_HEAD_END = re.compile(rb"</head\s*>", re.IGNORECASE)
_HAS_CANONICAL = re.compile(rb"""<link[^>]+rel=["']?canonical""", re.IGNORECASE)


def canonical_base(hub_url: str) -> str | None:
    """The public origin (and path prefix) pages are canonical under, or None."""
    parsed = urlparse((hub_url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in _LOCAL_HOSTS:
        return None
    return f"https://{parsed.netloc}{parsed.path.rstrip('/')}"


def canonical_href(base: str, path: str, lang: str | None = None) -> str:
    """The canonical URL of ``path`` on this hub; any query but a known ?lang= is dropped."""
    href = base + quote(path or "/", safe="/-._~!$&'()*+,;=:@%")
    if lang in LANGS:
        href += f"?lang={lang}"
    return href


def with_canonical(page: bytes, href: str) -> bytes:
    """``page`` with the canonical link before ``</head>``; unchanged if it has one or no head."""
    if _HAS_CANONICAL.search(page):
        return page
    match = _HEAD_END.search(page)
    if not match:
        return page
    tag = f'<link rel="canonical" href="{html.escape(href, quote=True)}">'.encode()
    return page[: match.start()] + tag + page[match.start():]
