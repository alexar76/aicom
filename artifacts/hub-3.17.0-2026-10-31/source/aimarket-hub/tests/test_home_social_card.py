"""A link to the reference home page unfurls with a card; another operator's hub does not show ours.

modelmarket.dev had og:title and og:description but no og:image, so every link to it pasted into
dev.to, X or a chat showed as bare text (2026-10-21 audit). The card names modelmarket.dev, so a
hub that runs this code under its own name drops the image tags rather than advertise ours.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aimarket_hub import api, theme
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer


def _client(tmp_path, name: str = "modelmarket.dev"):
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    config.hub_name = name  # the reference deployment runs as AIMARKET_HUB_NAME=modelmarket.dev
    if name != "modelmarket.dev":
        config.hub_url = "https://hub.example.org"
    app = api.create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    return TestClient(app)


def test_the_reference_home_page_names_its_card_and_serves_it(tmp_path):
    try:
        with _client(tmp_path) as client:
            home = client.get("/").text
            assert '<meta property="og:image" content="https://modelmarket.dev/og-card.png" />' in home
            assert '<meta name="twitter:card" content="summary_large_image" />' in home
            card = client.get("/og-card.png")
            assert card.status_code == 200
            assert card.headers["content-type"] == "image/png"
            assert card.content[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        theme.set_missing_pages(())


def test_another_hub_does_not_unfurl_with_the_modelmarket_card(tmp_path):
    try:
        with _client(tmp_path, name="Example Hub") as client:
            home = client.get("/").text
            assert "Example Hub" in home
            assert "og:image" not in home and "twitter:card" not in home
            assert 'content="https://hub.example.org/"' in home  # og:url still follows the hub
    finally:
        theme.set_missing_pages(())
