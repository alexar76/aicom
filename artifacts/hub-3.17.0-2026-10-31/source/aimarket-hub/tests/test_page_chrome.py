"""The public HTML pages must look like one site, and must not hand out unowned pip names.

Two things drifted before this file existed:

* `/developers`, `/examples` and `/plugins/demo` each carried a private stylesheet, so following
  a link off the terminal home page landed on a page in a different visual language entirely.
  `theme.py` is now the one source of that chrome, and the checks below are about the pages
  actually using it — a page that stops linking `/assets/site.css` renders unstyled, and nothing
  else in the suite would notice.

* `plugins-demo.html` printed `pip install <plugin name>` for every plugin the hub had loaded,
  built from the live catalogue. Ten of those names are unpublished, and one of them is the bare
  word `provenance`, which belongs to a stranger. `test_landing_install_lines.py` guards the same
  class of bug on the landing page; this guards the demo page, where the command is generated at
  runtime instead of written in the HTML.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import theme
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.landing import DOCS_HTML, INTEGRATION_EXAMPLES_HTML
from aimarket_hub.signing import Signer
from tests.test_landing_install_lines import PUBLISHED

HUB_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGINS_DEMO = HUB_ROOT / "plugins-demo.html"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("hub-chrome")
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    app = create_app(
        config=config,
        db=HubDatabase(root / "hub.db"),
        signer=Signer(root / "key"),
    )
    with TestClient(app) as c:
        yield c


def test_stylesheet_is_served(client):
    r = client.get("/assets/site.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert "--cyan: #38e0ff" in r.text, "the shared palette is gone from the served stylesheet"


@pytest.mark.parametrize("path", ["/start", "/developers", "/examples", "/plugins/demo", "/operator"])
def test_every_page_wears_the_shared_chrome(client, path):
    body = client.get(path).text
    assert '<link rel="stylesheet" href="/assets/site.css">' in body, (
        f"{path} does not link the shared stylesheet — it will render unstyled"
    )
    # The brand is the operator's, not a literal: `theme.configure` fills it from
    # HubConfig, so this fixture's hub shows the default "AIMarket Hub". Asserting a
    # specific domain here is what let a stranger's deployment ship someone else's name.
    assert 'class="brand"' in body and str(theme.BRAND["name"]) in body, (
        f"{path} lost the site nav"
    )
    assert "<footer>" in body, f"{path} lost the site footer"


def test_static_demo_page_has_no_leftover_placeholders(client):
    """The markers are inert comments in the file; the route is what fills them."""
    for path in ("/start", "/plugins/demo", "/operator"):
        body = client.get(path).text
        for marker in ("<!--HEAD-->", "<!--NAV-->", "<!--FOOTER-->", "<!--BACKDROP-->"):
            assert marker not in body, f"{marker} reached the browser unsubstituted on {path}"


def test_nav_points_only_at_pages_that_exist(client):
    for href, label, _key in theme.NAV_ITEMS:
        if href.startswith("http"):
            continue
        r = client.get(href, follow_redirects=True)
        # Optional mounts: Studio needs HEPHAESTUS dist; Widget needs the sibling
        # aimarket-widget package. Satellite CI has neither — the hub answers with an
        # explicit "not built/not found" page rather than a naked miss.
        if r.status_code == 503 and "studio" in href:
            assert "not built" in r.text.lower() or "hephaestus" in r.text.lower()
            continue
        if r.status_code == 404 and "widget" in href:
            assert "widget demo not found" in r.text.lower()
            continue
        assert r.status_code == 200, f"nav item {label!r} → {href} returned {r.status_code}"


def _demo_published_names() -> list[str]:
    text = PLUGINS_DEMO.read_text()
    m = re.search(r"var PUBLISHED = (\[[^\]]*\]);", text)
    assert m, "the plugin demo no longer declares which names are published"
    return json.loads(m.group(1))


def test_demo_page_only_offers_pip_install_for_names_we_own():
    unowned = sorted(set(_demo_published_names()) - PUBLISHED)
    assert not unowned, (
        f"the plugin demo offers `pip install` for {unowned}, which this project has not "
        f"published. Anyone can register those names on PyPI and have their setup.py run by "
        f"people following our own demo page."
    )


def test_demo_page_falls_back_to_a_repository_path():
    """Everything not in the published list must resolve to a path inside the repo."""
    text = PLUGINS_DEMO.read_text()
    assert 'cmd: "pip install -e plugins/"' in text, (
        "the unpublished branch no longer installs from the repository"
    )
    assert "not on PyPI yet" in text, "unpublished plugins are no longer labelled as such"


def test_shell_snippets_survive_python_string_parsing():
    """A `\\` at end of line inside a non-raw Python string is a line continuation, and the curl
    examples were being served as one unreadable line because of it."""
    assert "\\\n" in INTEGRATION_EXAMPLES_HTML, (
        "the multi-line shell examples lost their backslash continuations — the HTML body is "
        "probably no longer a raw string"
    )


def test_developer_page_leads_with_the_free_doors():
    """The onboarding ladder is the point of the page: two doors that cost nothing come before
    the one that spends money."""
    order = [DOCS_HTML.index(x) for x in ("aimarket-mcp", "AIMarketAgent")]
    assert order == sorted(order), "the paid SDK path now comes before the free MCP path"
    assert 'href="#start"' in DOCS_HTML
    assert "use.modelmarket.dev" in DOCS_HTML, "the use-case links are gone from /developers"


def test_operator_desk_is_a_login_wall(client):
    r = client.get("/operator")
    assert r.status_code == 200
    body = r.text
    assert 'id="unlock"' in body
    assert "AIMARKET_ADMIN_TOKEN" in body
    assert "Approve &amp; crawl" in body
    assert "Run assay" in body
    assert r.headers.get("cache-control") == "no-store"
    denied = client.get("/ai-market/v2/federation/inbound")
    assert denied.status_code in (401, 403, 503)
