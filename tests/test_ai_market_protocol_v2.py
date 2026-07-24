"""Regression tests for AI Market Protocol v2 compatibility layer."""

from __future__ import annotations

from pathlib import Path

V2_PATH = Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "ai_market_protocol_v2.py"


def _v2_source() -> str:
    return V2_PATH.read_text(encoding="utf-8")


def test_v2_reexports_root_routers_for_main():
    src = _v2_source()
    assert "capabilities_router" in src
    assert "wellknown_router" in src
    assert "from web.backend.api.ai_market_protocol_v1 import" in src


def test_v2_router_defines_search_and_invoke():
    src = _v2_source()
    assert 'router = APIRouter(prefix="/v2"' in src or 'prefix="/v2"' in src
    assert "async def search" in src or "def search" in src
    assert "async def invoke" in src or "def invoke" in src


def test_trust_for_state_helper_present():
    src = _v2_source()
    assert "def _trust_for_state" in src
    assert "COMPLETED" in src
