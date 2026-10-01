"""Factory /agents HTML roster — styled shell + live JSON poll."""

from __future__ import annotations

import asyncio

import pytest

from web.backend.api import agents_page
from web.backend.services import agent_registry


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AIFACTORY_AGENT_REGISTRY_KEY", raising=False)
    yield


def test_agents_page_is_styled_and_bootstraps_json():
    agent_registry.record_heartbeat(
        {
            "agent_id": "demo-1",
            "name": "Demo Agent",
            "product_id": "prod-demo",
            "sdk": "aimarket-agent@2.2.0",
            "stats": {"invokes_total": 3, "spend_usd_total": 0.5},
            "capabilities_used": ["atlas.situation.brief@v1"],
        }
    )

    resp = asyncio.run(agents_page.agents_roster_page())
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    csp = resp.headers.get("content-security-policy") or ""
    assert "default-src 'self'" in csp
    assert "style-src" in csp and "unsafe-inline" in csp
    assert "script-src" in csp
    assert "default-src 'none'" not in csp
    body = resp.body.decode("utf-8") if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
    assert "Factory agents" in body
    assert "Syne" in body or "IBM Plex" in body
    assert "/api/agents" in body
    assert 'id="boot"' in body
    assert "demo-1" in body
    assert "Demo Agent" in body  # server-painted first paint, not only boot JSON
    assert "loading…" not in body
    assert "setInterval(poll" in body
    assert "backdrop-filter" in body


def test_agents_page_csp_is_not_api_lockdown():
    """Regression: API middleware default-src 'none' used to blank the roster UI."""
    assert "unsafe-inline" in agents_page.AGENTS_PAGE_CSP
    assert "default-src 'none'" not in agents_page.AGENTS_PAGE_CSP


def test_agents_page_serves_its_own_fonts():
    """The page's webfonts come from this host, and the policy is what keeps it that way.

    This used to assert the opposite — that the CSP allowed fonts.googleapis.com — because the
    page linked its stylesheet from there. It no longer does, and the allowance had to go with
    it: left in place it is a standing permission for a future edit to start disclosing every
    visitor to Google again, with nothing failing to signal it.
    """
    assert "fonts.googleapis.com" not in agents_page.AGENTS_PAGE_CSP
    assert "fonts.gstatic.com" not in agents_page.AGENTS_PAGE_CSP
    assert "/fonts/fonts.css" in agents_page._PAGE
    assert "fonts.googleapis.com" not in agents_page._PAGE
