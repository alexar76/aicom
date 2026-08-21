"""A public manifest must not advertise an address only this machine can reach.

Found live on 2026-08-16: magic-ai-factory.com published
``mcp_endpoint: http://localhost:9080/ai-market/mcp`` to the whole internet, because a
stale ``AIFACTORY_PUBLIC_URL=http://localhost:9080`` outranked the correct
``NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com`` purely by being checked first. Any
federated peer that honoured the advertisement dialled its own machine, so the factory was
unroutable to the mesh while looking perfectly healthy from outside.

The rule these tests pin: a routable candidate beats an unroutable one whatever the order.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "web" / "backend" / "services" / "ai_market_protocol" / "config.py"


def _load_config():
    """Load config.py as a standalone module, not through its package.

    Importing `web.backend.services...` normally drags in the whole API tree, which cannot
    be built under the root venv's fastapi/starlette skew — the URL logic would then be
    untestable for a reason that has nothing to do with it. The file imports only `os` and
    `typing`, so loading it directly is faithful.
    """
    spec = importlib.util.spec_from_file_location("_ai_market_config_under_test", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def config(monkeypatch):
    """A freshly loaded config module — the URL is read at call time, not import."""
    for var in ("AIFACTORY_PUBLIC_URL", "NEXT_PUBLIC_SITE_URL"):
        monkeypatch.delenv(var, raising=False)
    return _load_config()


def test_a_routable_candidate_beats_a_loopback_one_whatever_the_order(config, monkeypatch):
    """The exact live shape: the wrong variable was set, and it was checked first."""
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://localhost:9080")
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    assert config.base_public_url() == "https://magic-ai-factory.com"


def test_the_preferred_variable_still_wins_when_both_are_routable(config, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "https://factory.example")
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://other.example")
    assert config.base_public_url() == "https://factory.example"


def test_a_purely_local_setup_keeps_the_address_it_configured(config, monkeypatch):
    """Every candidate loopback means someone is developing locally; do not override them."""
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://localhost:9080")
    assert config.base_public_url() == "http://localhost:9080"


def test_nothing_configured_falls_back(config):
    assert config.base_public_url() == "http://127.0.0.1:9080"


def test_trailing_slashes_are_stripped(config, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "https://factory.example/")
    assert config.base_public_url() == "https://factory.example"


@pytest.mark.parametrize("url,loopback", [
    ("http://localhost:9080", True),
    ("http://127.0.0.1:9080", True),
    ("https://[::1]:9080", True),
    ("http://10.1.2.3:9080", True),
    ("http://192.168.1.10", True),
    ("http://172.17.0.1:9080", True),
    ("https://magic-ai-factory.com", False),
    ("https://203.0.113.80:9083", False),
    ("", False),
])
def test_loopback_detection(config, url, loopback):
    assert config._is_loopback_url(url) is loopback


def test_the_manifest_carries_the_routable_base(config, monkeypatch):
    """The field that actually leaked: peers read mcp_endpoint out of this document.

    Skipped where the root venv's fastapi/starlette skew cannot build the app — importing
    the manifest module drags in the whole API tree. The logic above is the substance of
    the fix; this asserts it reaches the document a peer actually reads.
    """
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://localhost:9080")
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    try:
        wellknown = importlib.import_module("web.backend.services.ai_market_protocol.wellknown")
    except (ImportError, TypeError) as exc:  # TypeError: Router.__init__ on the skewed venv
        pytest.skip(f"app tree not importable in this interpreter: {exc}")
    doc = wellknown.build_well_known()
    assert doc["mcp_endpoint"] == "https://magic-ai-factory.com/ai-market/mcp"
    assert "localhost" not in doc["manifest_url"]
