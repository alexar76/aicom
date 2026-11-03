"""A stranger's deployment must describe the stranger's hub.

Every page the hub serves used to be branded for one specific deployment: the nav said
`modelmarket.dev`, the footer linked that operator's escrow contract on Basescan as if it
were the page's own settlement proof, and every copy-pasteable sample in /developers and
/examples told the reader to curl `https://modelmarket.dev`. On anyone else's hub the last
of those is not cosmetic — a visitor who follows the documentation calls somebody else's
hub, which is the opposite of what a storefront is for.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import theme
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    app = create_app(config=config, db=HubDatabase(root / "hub.db"), signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


PAGES = ("/developers", "/examples")
# Pages that must not link the reference ecosystem; /start builds its URLs in the browser.
LINKED_PAGES = PAGES + ("/start",)


class TestAStrangersHub:
    @pytest.mark.parametrize("path", PAGES)
    def test_code_samples_name_this_hub(self, monkeypatch, tmp_path, path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_HUB_NAME="Example Hub",
        ) as client:
            body = client.get(path).text
            assert "https://hub.example.org/.well-known/ai-market.json" in body
            assert "https://modelmarket.dev" not in body, (
                f"{path} still tells the reader to call another operator's hub"
            )

    @pytest.mark.parametrize("path", LINKED_PAGES)
    def test_no_links_to_the_reference_ecosystem(self, monkeypatch, tmp_path, path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_HUB_NAME="Example Hub",
        ) as client:
            body = client.get(path).text
            for host in ("use.modelmarket.dev", "atlas.modelmarket.dev", "edu.modelmarket.dev",
                         "modelmarket.dev/tools/", "modelmarket.dev/blog/"):
                assert host not in body, f"{path} advertises {host}"

    def test_the_nav_carries_the_operators_name(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_HUB_NAME="Example Hub",
        ) as client:
            body = client.get("/developers").text
            assert 'class="brand"' in body and "Example Hub" in body

    def test_no_escrow_link_when_this_hub_has_no_escrow(self, monkeypatch, tmp_path):
        """A hard-coded Basescan address is a stranger's contract presented as your proof."""
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_ESCROW_EVM_ADDRESS="",
        ) as client:
            assert "basescan.org" not in client.get("/developers").text

    def test_the_escrow_link_is_this_hubs_own_contract(self, monkeypatch, tmp_path):
        mine = "0x1111111111111111111111111111111111111111"
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_ESCROW_EVM_ADDRESS=mine,
        ) as client:
            body = client.get("/developers").text
            assert f"https://basescan.org/address/{mine}" in body
            assert "0x0606983c" not in body


class TestTheReferenceDeployment:
    """The default must not change for the hub this was all written on."""

    def test_ecosystem_links_stay_on_for_modelmarket(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://modelmarket.dev",
            AIMARKET_HUB_NAME="modelmarket.dev",
        ) as client:
            body = client.get("/developers").text
            assert "use.modelmarket.dev" in body
            assert "https://modelmarket.dev/.well-known/ai-market.json" in body
            # Newcomers on the key page are pointed at the lesson that walks the same loop.
            assert "https://edu.modelmarket.dev/ai-pays-ai/" in client.get("/start").text

    def test_the_free_check_pages_are_linked_from_the_nav_footer_and_llms_txt(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://modelmarket.dev",
            AIMARKET_HUB_NAME="modelmarket.dev",
        ) as client:
            home = client.get("/").text
            docs = client.get("/developers").text
            llms = client.get("/llms.txt").text
        assert '<a href="https://modelmarket.dev/tools/" data-i18n="nav_tools">' in home
        # Its own page, not another site: no new tab from the nav.
        assert '<a href="https://modelmarket.dev/tools/">Free tools</a>' in docs
        assert docs.count("https://modelmarket.dev/tools/") >= 2, "nav and footer"
        assert "https://modelmarket.dev/tools/x402-check" in llms

    def test_the_blog_is_linked_from_the_reference_nav_and_footer(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://modelmarket.dev",
            AIMARKET_HUB_NAME="modelmarket.dev",
        ) as client:
            home = client.get("/").text
            docs = client.get("/developers").text
        assert '<a href="https://modelmarket.dev/blog/" data-i18n="nav_blog">Blog</a>' in home
        assert '<a href="https://modelmarket.dev/blog/">Blog</a>' in docs
        assert docs.count("https://modelmarket.dev/blog/") >= 2, "nav and footer"

    def test_an_operator_can_force_the_links_either_way(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://modelmarket.dev",
            AIMARKET_ECOSYSTEM_LINKS="0",
        ) as client:
            assert "use.modelmarket.dev" not in client.get("/developers").text


def test_dropping_a_card_leaves_the_markup_intact(monkeypatch, tmp_path):
    """Off-site cards are removed whole; the section around them must survive."""
    from aimarket_hub import landing

    with_links = landing.docs_html("https://hub.example.org", ecosystem_links=True)
    without = landing.docs_html("https://hub.example.org", ecosystem_links=False)
    assert without.count('<div class="card">') < with_links.count('<div class="card">')
    assert without.count("<section") == with_links.count("<section")
    assert without.count("</section>") == with_links.count("</section>")
    # Balanced divs: card removal must not leave an orphan closer behind.
    assert without.count("<div") - without.count("</div>") == (
        with_links.count("<div") - with_links.count("</div>")
    )


def test_brand_is_rebindable_between_apps(monkeypatch, tmp_path):
    """Two hubs in one process (every test session) must not inherit each other's brand."""
    with _hub(monkeypatch, tmp_path, AIMARKET_HUB_NAME="First Hub") as client:
        assert "First Hub" in client.get("/developers").text
    with _hub(monkeypatch, tmp_path, AIMARKET_HUB_NAME="Second Hub") as client:
        body = client.get("/developers").text
        assert "Second Hub" in body and "First Hub" not in body
    assert str(theme.BRAND["name"]) == "Second Hub"


class TestTheHomePageAndTheWidget:
    def test_the_home_page_wears_the_operators_name(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://hub.example.org",
            AIMARKET_HUB_NAME="Example Hub",
        ) as client:
            body = client.get("/").text
            assert "<title>Example Hub — AI Economy Protocol</title>" in body
            assert "<title>modelmarket.dev" not in body
            assert 'content="https://hub.example.org/"' in body
            # Nor its link to the reference deployment's free check pages.
            assert "modelmarket.dev/tools/" not in body

    def test_the_home_page_is_untouched_on_the_reference_hub(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_HUB_URL="https://modelmarket.dev",
            AIMARKET_HUB_NAME="modelmarket.dev",
        ) as client:
            assert "<title>modelmarket.dev — AI Economy Protocol</title>" in client.get("/").text

    def test_the_widget_allowlists_this_hub_not_a_stranger(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path, AIMARKET_HUB_URL="https://hub.example.org",
        ) as client:
            r = client.get("/widget/widget.js")
            if r.status_code == 404:
                pytest.skip("widget package not bundled in this checkout")
            assert 'HUB_ALLOW_SUFFIXES = ["hub.example.org"]' in r.text
            assert '["modelmarket.dev"]' not in r.text
