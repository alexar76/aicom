"""Where a hub says its own providers can be reached.

A provider is registered with the address the HUB dials, which on a single-host deploy is a
compose hostname. `hub.attestedmemory.net` therefore published Memory Market, Truth Layer
and Provenance Ledger as `http://memory-market:8810`, `http://truth-layer:8811` and
`http://provenance-ledger:8812` — and every monitor drew three nodes whose only address is
meaningless outside that one host. There was an env var for their NAMES
(`AIMARKET_ECOSYSTEM_LABELS`) and none for their addresses.

`independentai.network/hub` had it right the whole time (AEGIS, KOVA and its echo provider
all publish public URLs), which is what made the gap look like a per-deployment mistake
rather than a missing mechanism.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def wk(monkeypatch, tmp_path):
    """The well-known document of a hub whose three providers are compose-hosted."""
    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.models import Capability
    from aimarket_hub.signing import Signer

    counter = {"n": 0}

    def build(env: dict[str, str]) -> dict:
        # Built AFTER the env is applied: create_app snapshots several vars into closure
        # state, so an app built first is testing the previous configuration.
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        counter["n"] += 1
        root = tmp_path / f"hub-{counter['n']}"
        root.mkdir(parents=True, exist_ok=True)
        config = HubConfig()
        config.db_path = str(root / "hub.db")
        config.signing_key_path = str(root / "key")
        db = HubDatabase(root / "hub.db")
        for publisher, port, count in (
            ("memory-market", 8810, 5), ("truth-layer", 8811, 4),
            ("provenance-ledger", 8812, 3),
        ):
            for i in range(count):
                db.upsert_capability(Capability(
                    capability_id=f"{publisher}.cap{i}@v1", product_id=publisher,
                    name=f"{publisher} {i}", publisher_id=publisher,
                    invoke_url=(
                        f"http://{publisher}:{port}"
                        f"/capabilities/{publisher}/cap{i}/invoke"
                    ),
                ))
        app = create_app(config=config, db=db, signer=Signer(root / "key"))
        with TestClient(app) as client:
            return client.get("/.well-known/ai-market.json").json()

    return build


def _nodes(document: dict) -> dict[str, dict]:
    eco = document.get("ecosystem") or {}
    return {n["id"]: n for n in (eco.get("nodes") or [])}


class TestDeclaredUrls:
    def test_without_the_env_the_compose_hostname_leaks(self, wk):
        """The behaviour that produced the bug — pinned, so the fix cannot silently lapse."""
        nodes = _nodes(wk({"AIMARKET_ECOSYSTEM_URLS": ""}))
        assert nodes["memory-market"]["url"] == "http://memory-market:8810"

    def test_the_operator_can_say_where_a_provider_lives(self, wk):
        nodes = _nodes(wk({
            "AIMARKET_ECOSYSTEM_URLS":
                "memory-market=https://memory.attestedmemory.net,"
                "truth-layer=https://truth.attestedmemory.net/,"
                "provenance-ledger=https://provenance.attestedmemory.net",
        }))
        assert nodes["memory-market"]["url"] == "https://memory.attestedmemory.net"
        # trailing slash normalised away
        assert nodes["truth-layer"]["url"] == "https://truth.attestedmemory.net"
        assert nodes["provenance-ledger"]["url"] == "https://provenance.attestedmemory.net"

    def test_a_provider_without_an_entry_keeps_its_derived_address(self, wk):
        nodes = _nodes(wk({
            "AIMARKET_ECOSYSTEM_URLS": "memory-market=https://memory.attestedmemory.net",
        }))
        assert nodes["memory-market"]["url"] == "https://memory.attestedmemory.net"
        assert nodes["truth-layer"]["url"] == "http://truth-layer:8811"

    @pytest.mark.parametrize("bad", [
        "memory-market=not-a-url",
        "memory-market=ftp://memory.example",
        "memory-market",            # no separator
        "=https://memory.example",  # no publisher
    ])
    def test_a_malformed_entry_is_ignored_not_published(self, wk, bad):
        nodes = _nodes(wk({"AIMARKET_ECOSYSTEM_URLS": bad}))
        assert nodes["memory-market"]["url"] == "http://memory-market:8810"

    def test_names_and_addresses_are_independent(self, wk):
        nodes = _nodes(wk({
            "AIMARKET_ECOSYSTEM_LABELS": "memory-market:Memory Market",
            "AIMARKET_ECOSYSTEM_URLS": "memory-market=https://memory.attestedmemory.net",
        }))
        assert nodes["memory-market"]["name"] == "Memory Market"
        assert nodes["memory-market"]["url"] == "https://memory.attestedmemory.net"
