"""Every hub HTML page names its canonical URL under AIMARKET_HUB_URL.

modelmarket.dev, www.modelmarket.dev and uni.modelmarket.dev were indexed with the same
title and no canonical, and ?utm_/?ref= links made more copies of each page.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.canonical import canonical_base, canonical_href, with_canonical
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer


def _client(hub_url: str):
    tmp = tempfile.TemporaryDirectory()
    config = HubConfig()
    config.hub_url = hub_url
    config.db_path = str(Path(tmp.name) / "t.db")
    config.signing_key_path = str(Path(tmp.name) / "k")
    app = create_app(config=config, db=HubDatabase(Path(tmp.name) / "t.db"), signer=Signer(Path(tmp.name) / "k"))
    return tmp, TestClient(app)


@pytest.fixture
def reference():
    tmp, client = _client("https://modelmarket.dev")
    with tmp, client:
        yield client


@pytest.mark.parametrize("path", ["/", "/start", "/developers", "/examples"])
def test_pages_name_themselves_under_the_hub_url(reference, path):
    r = reference.get(path, headers={"Host": "www.modelmarket.dev"})
    assert r.status_code == 200
    expected = "https://modelmarket.dev/" if path == "/" else f"https://modelmarket.dev{path}"
    assert f'<link rel="canonical" href="{expected}">' in r.text
    assert r.text.count('rel="canonical"') == 1
    assert int(r.headers["content-length"]) == len(r.content)


def test_tracking_queries_fold_and_languages_stay(reference):
    assert '<link rel="canonical" href="https://modelmarket.dev/start">' in reference.get(
        "/start?utm_source=devto&ref=x"
    ).text
    assert '<link rel="canonical" href="https://modelmarket.dev/start?lang=zh">' in reference.get(
        "/start?lang=zh&utm_source=devto"
    ).text
    assert '<link rel="canonical" href="https://modelmarket.dev/start">' in reference.get("/start?lang=en").text


def test_json_is_left_alone(reference):
    r = reference.get("/.well-known/ai-market.json")
    assert r.headers["content-type"].startswith("application/json")
    assert 'rel="canonical"' not in r.text
    r.json()


def test_the_security_headers_survive_the_rewrite(reference):
    r = reference.get("/start")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_a_hub_without_a_public_https_address_says_nothing():
    tmp, client = _client("http://localhost:9083")
    with tmp, client:
        assert 'rel="canonical"' not in client.get("/start").text


def test_a_second_hub_is_canonical_under_its_own_name():
    tmp, client = _client("https://uni.modelmarket.dev/")
    with tmp, client:
        assert '<link rel="canonical" href="https://uni.modelmarket.dev/developers">' in client.get(
            "/developers"
        ).text


class TestHelpers:
    def test_base_keeps_a_path_prefix(self):
        assert canonical_base("https://independentai.network/hub/") == "https://independentai.network/hub"

    @pytest.mark.parametrize("url", ["", "http://modelmarket.dev", "https://localhost:9083", "https://127.0.0.1"])
    def test_base_refuses_non_public_addresses(self, url):
        assert canonical_base(url) is None

    def test_href_ignores_unknown_languages(self):
        assert canonical_href("https://h.example", "/start", "xx") == "https://h.example/start"

    def test_href_escapes_markup_in_the_path(self):
        page = with_canonical(b"<html><head></head></html>", canonical_href("https://h.example", '/a"><x'))
        assert b'"><x' not in page

    def test_an_existing_canonical_wins(self):
        page = b'<head><link rel="canonical" href="https://a.example/"></head>'
        assert with_canonical(page, "https://b.example/") == page

    def test_a_page_without_head_is_unchanged(self):
        assert with_canonical(b"<p>fragment</p>", "https://h.example/") == b"<p>fragment</p>"
