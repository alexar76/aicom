"""`/hubs`: the federation for a person to read, and the way to run the next hub.

Every name and address on the page was written by a peer — a stranger can announce itself
with no credential — so the page is a stored-XSS surface by construction and is tested as one.
"""
from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "hub"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


def test_lists_admitted_and_knocking_hubs_and_how_to_run_one(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_HUB_NAME="Example Hub",
              AIMARKET_HUB_URL="https://hub.example.org") as client:
        client.hub_db.upsert_peer(Peer(url="https://peer.example", name="Peer Hub", trusted=True),
                                  status="active")
        client.hub_db.upsert_peer(Peer(url="https://knocker.example", name="k", trusted=False),
                                  status="pending")
        resp = client.get("/hubs")
        assert resp.status_code == 200
        body = resp.text
        assert "Peer Hub" in body and "https://peer.example" in body
        assert "https://knocker.example" in body
        assert "/ai-market/v2/federation/assay?url=https%3A%2F%2Fknocker.example" in body
        assert 'id="run-your-own"' in body and "aimarket quickstart" in body
        assert "<footer>" in body and "/hubs#run-your-own" in body


def test_a_peers_words_are_escaped_and_a_non_http_address_is_not_a_link(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        client.hub_db.upsert_peer(
            Peer(url="javascript:alert(1)", name="<script>alert(1)</script>", trusted=True),
            status="active",
        )
        body = client.get("/hubs").text
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body
        assert 'href="javascript:' not in body


def test_every_page_footer_points_at_running_your_own(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        assert "/hubs#run-your-own" in client.get("/start").text
