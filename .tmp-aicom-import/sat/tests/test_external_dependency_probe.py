"""The pipeline must not select for deleting a call because its dependency is down.

Sentinel (prod-bdb1634806de) spent 12 days and 38 reverted rounds proving this gap exists. Its
advisory endpoint is meant to call ATLAS, and the product carried two addresses for it:

    backend/app/services/aimarket_participant.py:29   https://atlas.modelmarket.dev   (answers 200)
    backend/app/config.py:9                           http://localhost:8001           (nothing there)

Every round that restored the real call produced `demo_journey_unreachable:/api/advisory:timed
out` — one high finding, weight 3, taking the score from 9 to 12 — and the guard reverted the
whole round. The only edit the gate would ever accept was replacing the call with a static
placeholder, and that is the edit the developer eventually made: the finding went away and the
product's reason to exist went with it. The pipeline was not failing to fix a hard bug, it was
selecting for the wrong fix.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from web.backend.services.product_demo_journey import (
    _declared_external_urls,
    probe_external_dependencies,
)


def _product(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


def test_it_finds_the_address_and_names_the_line_to_edit():
    """A finding without a file:line is not actionable in one round."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            "backend/app/config.py": '''
                class Settings:
                    atlas_base_url: str = "http://localhost:8001"
                    hub_url: str = "https://modelmarket.dev/api"
            ''',
        })
        found = {e["url"]: e["source"] for e in _declared_external_urls(code)}
        assert "http://localhost:8001" in found
        assert found["http://localhost:8001"].startswith("backend/app/config.py:")
        # The path is stripped: only the base is probed, because a health path is a guess and a
        # 404 on the wrong path does not mean the service is down.
        assert "https://modelmarket.dev" in found


def test_the_products_own_port_is_not_an_external_dependency():
    """The journey boots the app and talks to it on loopback; that is not a dependency."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            # Deliberately NOT named self_url/public_url: there is a separate name-based rule
            # for those, and a fixture that trips both cannot tell which one is under test.
            "app/config.py": 'api_url = "http://127.0.0.1:8099/health"\n',
        })
        assert _declared_external_urls(code, own_port=8099) == []
        assert [e["url"] for e in _declared_external_urls(code, own_port=1234)] == [
            "http://127.0.0.1:8099"
        ]


def test_commented_out_addresses_are_ignored():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            "app/config.py": '# old: atlas = "http://localhost:9999"\natlas = "http://localhost:8001"\n',
        })
        urls = [e["url"] for e in _declared_external_urls(code)]
        assert urls == ["http://localhost:8001"]


def test_a_dead_address_is_reported_and_a_live_one_is_not():
    """Any HTTP answer at all — including 404 — proves something is listening, which is the only
    thing this check claims. Only a transport failure counts."""
    import http.server
    import tempfile
    import threading

    class Quiet(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(404)
            self.end_headers()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Quiet)
    live_port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as td:
            code = _product(Path(td), {
                "app/config.py": (
                    f'live = "http://127.0.0.1:{live_port}"\n'
                    'dead = "http://127.0.0.1:1"\n'
                ),
            })
            dead = probe_external_dependencies(code, timeout=3.0)
            urls = [d["url"] for d in dead]
            assert f"http://127.0.0.1:{live_port}" not in urls, "a 404 is not a dead service"
            assert "http://127.0.0.1:1" in urls
            assert dead[0]["source"].startswith("app/config.py:")
    finally:
        server.shutdown()


def test_a_product_with_no_config_has_no_dependencies():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        assert probe_external_dependencies(Path(td)) == []


def test_a_products_own_public_url_is_not_a_dependency():
    """Measured on Sentinel: `sentinel_public_url = "http://localhost:8000"` was reported next to
    its two genuinely dead dependencies. A finding that names a non-problem beside real ones is
    how a gate teaches people to skim it. Keyed on the setting NAME, because the port a product
    runs on inside the sandbox is not the port its config remembers."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            "app/config.py": (
                'sentinel_public_url: str = "http://localhost:8000"\n'
                'atlas_base_url: str = "http://localhost:8001"\n'
                'oauth_callback_url: str = "http://127.0.0.1:8000/cb"\n'
            ),
        })
        urls = [e["url"] for e in _declared_external_urls(code)]
        assert urls == ["http://localhost:8001"], urls


def test_a_vite_cors_origin_is_not_a_dependency():
    """Relay ``.env.example`` declares ``CORS_ORIGIN=http://localhost:5173`` for the Vite
    dev server. That is an allowlist the browser sends, not a URL the sandbox should GET.
    Probing it scored a high Config finding and parked the repair loop at plateau."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            ".env.example": (
                "CORS_ORIGIN=http://localhost:5173\n"
                "VITE_API_URL=http://localhost:5173\n"
                'atlas_base_url = "http://localhost:8001"\n'
            ),
        })
        urls = [e["url"] for e in _declared_external_urls(code)]
        assert urls == ["http://localhost:8001"], urls


def test_a_remote_url_is_never_treated_as_self():
    """The exclusion is for loopback only — a public hostname is always a dependency, whatever
    the setting is called."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        code = _product(Path(td), {
            "app/config.py": 'site_url: str = "https://sentinel.example.com"\n',
        })
        assert [e["url"] for e in _declared_external_urls(code)] == [
            "https://sentinel.example.com"
        ]
