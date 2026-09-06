"""Every browser POST must go out with the CSRF header the middleware demands.

`web/backend/middleware/csrf.py` keys enforcement on the CREDENTIAL, not the path: any
request carrying an `access_token` / `aif_admin_session` cookie must present
`X-CSRF-Token`. `lib/api.ts` does that for unsafe methods; `lib/analytics.ts` used a raw
`fetch` and did not. Both of its calls therefore worked for anonymous visitors and returned
403 for anyone with a session — and on the public-demo host every visitor who clicks
"Open demo" gets one. The analytics post failed silently behind `.catch(() => {})`; the lead
form failed visibly with "Failed to submit".

This scans the frontend for raw `fetch` POSTs to our own API and requires each to send the
header, so the next helper written outside the API client cannot reintroduce it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "web" / "frontend"
SEARCH_DIRS = [ROOT / "lib", ROOT / "components", ROOT / "app"]

# A raw fetch to our own API: fetch('/api/...', { ... }) — capture the options object.
_RAW_FETCH = re.compile(
    r"fetch\(\s*[`'\"](?P<url>/api/[^`'\"]*)[`'\"]\s*,\s*\{(?P<opts>.*?)\n\s*\}\s*\)",
    re.S,
)
_UNSAFE = re.compile(r"method:\s*['\"](POST|PUT|PATCH|DELETE)['\"]", re.I)


def _sources() -> list[Path]:
    out: list[Path] = []
    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for p in list(d.rglob("*.ts")) + list(d.rglob("*.tsx")):
            if ".next" in p.parts or "node_modules" in p.parts:
                continue
            out.append(p)
    return sorted(out)


def _unsafe_raw_fetches() -> list[tuple[Path, str, str]]:
    found = []
    for p in _sources():
        text = p.read_text()
        for m in _RAW_FETCH.finditer(text):
            opts = m.group("opts")
            if _UNSAFE.search(opts):
                found.append((p, m.group("url"), opts))
    return found


def test_the_scan_finds_something():
    """Guard the premise — a regex that matches nothing would pass vacuously."""
    assert _unsafe_raw_fetches(), (
        "no raw unsafe fetch found; if every caller now goes through lib/api.ts this test can "
        "be deleted, but a silently-matching-nothing regex must not be mistaken for a pass"
    )


@pytest.mark.parametrize(
    "case",
    _unsafe_raw_fetches(),
    ids=lambda c: f"{c[0].name}:{c[1]}",
)
def test_raw_unsafe_fetch_sends_the_csrf_header(case):
    path, url, opts = case
    text = path.read_text()
    sends_header = "X-CSRF-Token" in opts or "csrfHeaders()" in opts
    # Importing the shared helper counts — that module is what actually sets the header, and
    # one shared definition is the point (three separate raw fetches is how this broke).
    if not sends_header and "lib/csrf" in text:
        sends_header = "csrfHeaders" in text
    assert sends_header, (
        f"{path.name} POSTs to {url} with a raw fetch and no X-CSRF-Token. The CSRF "
        "middleware enforces on the presence of a session cookie, so this call returns 403 "
        "for every logged-in visitor. Route it through lib/api.ts or attach the header."
    )
