from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_forge_domain_is_the_hephaestus_landing_not_basanos():
    landing_path = ROOT / "hephaestus/docs/landing/index.html"
    if not landing_path.is_file():
        pytest.skip("hephaestus landing absent (factory trimmed tree)")
    nginx = (ROOT / "deploy/nginx/forge.modelmarket.dev.conf").read_text(encoding="utf-8")
    landing = landing_path.read_text(encoding="utf-8")
    assert "server_name forge.modelmarket.dev" in nginx
    assert "hephaestus/docs/landing" in nginx
    assert "BASANOS" in nginx  # named so operators do not put the touchstone here
    assert "basanos.modelmarket.dev" in nginx
    assert "modelmarket.dev/studio" in nginx
    assert "https://forge.modelmarket.dev/" in landing
    assert "HEPHAESTUS" in landing
    assert "coverListing" not in landing
    assert "basanos.modelmarket.dev" not in landing


def test_basanos_vhost_proxies_loopback_and_is_not_the_forge():
    compose_path = ROOT / "basanos/docker-compose.yml"
    if not compose_path.is_file():
        pytest.skip("basanos compose absent (factory trimmed tree)")
    nginx = (ROOT / "deploy/nginx/basanos.modelmarket.dev.conf").read_text(encoding="utf-8")
    compose = compose_path.read_text(encoding="utf-8")
    assert "server_name basanos.modelmarket.dev" in nginx
    assert "127.0.0.1:9470" in nginx
    assert "forge.modelmarket.dev" in nginx
    assert "127.0.0.1:9470:9470" in compose
    assert "0.0.0.0:9470" not in compose
    dockerfile = (ROOT / "basanos/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --locked" in dockerfile
    assert "docs/landing/stone.js" in dockerfile
