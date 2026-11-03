"""The bridge wired into the hub's request path.

Two things are tested here, and the first matters more: with no bridge env vars set the
hub behaves exactly as it did before — the escrow seams are inert, not merely unused. The
second is that when the bridge IS on, each seam fails closed rather than open.

The bridge's own correctness lives in the other test_escrow_bridge_* files; this file is
about the wiring, which is where the previous attempt at this feature (and the shared
deposit registry before it) actually broke: code present, never called.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "escrow-admin-token"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
_ESCROW_CHANNEL = "0x" + "11" * 32


@pytest.fixture
def hub(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_DB_PATH", str(tmp_path / "bridge.db"))
    for var in ("AIMARKET_ESCROW_BRIDGE_ENABLED", "AIMARKET_ESCROW_CONTRACT",
                "AIMARKET_ESCROW_HUB_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "hub.db")
        config.signing_key_path = str(Path(tmp) / "key")
        app = create_app(
            config=config, db=HubDatabase(config.db_path),
            signer=Signer(config.signing_key_path),
        )
        with TestClient(app) as client:
            yield client


class TestTheHubIsUnchangedWhileTheBridgeIsOff:
    """The property an operator who never opts in is entitled to."""

    def test_channel_open_ignores_an_escrow_id_it_was_not_asked_to_honour(self, hub):
        """A stray field must not silently change how a deposit is verified."""
        resp = hub.post("/ai-market/v2/channel/open", json={
            "deposit_usd": 5.0, "wallet": "0x" + "aa" * 20,
            "escrow_channel_id": _ESCROW_CHANNEL,
        })
        # Refused because the bridge is off — NOT credited through the escrow path.
        assert resp.status_code == 400
        assert "disabled" in resp.json().get("error", "").lower()

    def test_a_normal_channel_open_still_works(self, hub):
        """The transfer path must be untouched by the escrow branch existing."""
        resp = hub.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0})
        assert resp.status_code == 200, resp.text
        channel = resp.json()["channel"]
        assert channel["balance_usd"] == 5.0
        assert channel.get("channel_secret")
        # No escrow binding, so nothing about the settlement model changed.
        assert not channel.get("escrow_channel")

    def test_an_invoke_is_not_asked_for_an_authorization(self, hub):
        """A transfer-funded channel must never be told it needs an on-chain signature."""
        opened = hub.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()
        channel = opened["channel"]
        resp = hub.post(
            "/ai-market/v2/invoke",
            json={"product_id": "nope", "capability_id": "nope", "source_hub": "local",
                  "input": {}},
            headers={"X-Payment-Channel": channel["channel_id"],
                     "X-Payment-Channel-Secret": channel["channel_secret"]},
        )
        # 404 for the unknown capability — the point is that it is NOT 402
        # payment_authorization_required.
        assert resp.status_code == 404
        assert "payment_authorization" not in resp.text


class TestTheAdminSurfaceIsGatedAndReadOnly:
    @pytest.mark.parametrize("path", ["/ai-market/v2/escrow/status", "/ai-market/v2/escrow/plan"])
    def test_it_requires_the_admin_token(self, hub, path):
        assert hub.get(path).status_code in (401, 403)
        assert hub.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 403

    def test_status_works_on_a_hub_that_never_enabled_the_bridge(self, hub):
        resp = hub.get("/ai-market/v2/escrow/status", headers=ADMIN)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["config"]["enabled"] is False
        assert payload["signer"] == "plan"
        assert payload["queue"] == []

    def test_status_does_not_create_the_store(self, hub, tmp_path):
        hub.get("/ai-market/v2/escrow/status", headers=ADMIN)
        assert not (tmp_path / "bridge.db").exists()

    def test_status_never_reports_key_material(self, hub, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "ab" * 32)
        resp = hub.get("/ai-market/v2/escrow/status", headers=ADMIN)
        assert "ab" * 32 not in resp.text
        assert resp.json()["config"]["private_key_set"] is True

    def test_plan_refuses_while_the_bridge_is_disabled(self, hub):
        """Plan is harmless, but running it on a disabled bridge would be misleading."""
        resp = hub.get("/ai-market/v2/escrow/plan", headers=ADMIN)
        assert resp.status_code == 409
        assert "disabled" in resp.text.lower()

    def test_there_is_no_route_that_broadcasts(self, hub):
        """Submission is a CLI action; nothing reachable over HTTP may move funds."""
        paths = {
            route.path for route in hub.app.routes if hasattr(route, "path")
        }
        assert not any("submit" in p and "escrow" in p for p in paths)


class TestEscrowModeFailsClosed:
    """No signature verification happens on these paths, so they need no crypto backend:
    the chain reads are stubbed and the refusals come from contract STATE, not from a
    recovered signer. That is why this class is not skipped on the hub's own venv."""

    @pytest.fixture(autouse=True)
    def bridge_on(self, hub, monkeypatch):
        # Depends on `hub` so it runs AFTER it: the hub fixture clears the bridge vars to
        # build a default-off app, and an autouse fixture would otherwise be undone by it.
        monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", "0x" + "ee" * 20)
        monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", "0x" + "cc" * 20)

    def test_an_unreadable_chain_refuses_the_open_rather_than_falling_back(self, hub, monkeypatch):
        """A caller naming an escrow channel must never be credited via the transfer path."""
        from aimarket_hub.escrow_bridge import chain

        def _boom(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(chain, "_pool", _boom)
        resp = hub.post("/ai-market/v2/channel/open", json={
            "deposit_usd": 5.0, "wallet": "0x" + "aa" * 20,
            "escrow_channel_id": _ESCROW_CHANNEL,
        })
        assert resp.status_code == 400
        body = resp.json()["error"].lower()
        # Specifically an unreadable-chain refusal — asserting merely "escrow" would also
        # be satisfied by the bridge-disabled message, i.e. it would pass for the wrong
        # reason if the fixture ordering ever regressed.
        assert "unavailable" in body or "failed" in body or "chainid" in body
        assert "disabled" not in body

    def test_a_channel_that_does_not_exist_on_chain_is_refused(self, hub, monkeypatch):
        from aimarket_hub.escrow_bridge import chain

        empty = chain.EscrowChannel(
            channel_id=_ESCROW_CHANNEL, depositor="0x" + "00" * 20, hub="0x" + "00" * 20,
            token="0x" + "00" * 20, deposit_amount=0, balance=0, used_amount=0,
            expires_at=0, nonce=0, status=0,
        )
        monkeypatch.setattr(chain, "chain_id", lambda: 8453)
        monkeypatch.setattr(chain, "escrow_address", lambda: "0x" + "ee" * 20)
        monkeypatch.setattr(chain, "read_channel", lambda cid, address=None: empty)
        resp = hub.post("/ai-market/v2/channel/open", json={
            "deposit_usd": 5.0, "wallet": "0x" + "aa" * 20,
            "escrow_channel_id": _ESCROW_CHANNEL,
        })
        assert resp.status_code == 400
        assert "no escrow channel" in resp.json()["error"].lower()
