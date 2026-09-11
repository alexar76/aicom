"""GitHub catalog gate activates only when Settings + GH_PAT are ready."""

from core.github_catalog import (
    github_catalog_armed,
    github_catalog_ready,
    github_house_gate_active,
    github_pat_configured,
)


def test_house_gate_off_without_catalog(monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    g = {"product_catalog_enabled": False, "product_catalog_require_github_house": True}
    assert github_house_gate_active(g) is False
    assert github_catalog_ready(g) is False


def test_house_gate_off_without_pat_even_if_catalog_on(monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    g = {"product_catalog_enabled": True, "product_catalog_require_github_house": True}
    assert github_pat_configured() is False
    assert github_catalog_armed(g) is True
    assert github_house_gate_active(g) is False
    assert github_catalog_ready(g) is False


def test_house_gate_on_when_catalog_and_pat(monkeypatch):
    monkeypatch.setenv("GH_PAT", "test-token-not-real")
    g = {"product_catalog_enabled": True, "product_catalog_require_github_house": True}
    assert github_pat_configured() is True
    assert github_house_gate_active(g) is True
    assert github_catalog_ready(g) is True


def test_house_gate_respects_require_flag(monkeypatch):
    monkeypatch.setenv("GH_PAT", "test-token-not-real")
    g = {"product_catalog_enabled": True, "product_catalog_require_github_house": False}
    assert github_house_gate_active(g) is False
