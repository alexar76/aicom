"""SSRF guard tests (security audit 2026-10-25).

The probe fetches caller-supplied URLs from inside the service's
network. These tests pin the refusal behaviour: non-public targets are
never fetched, and an oversized target body cannot exhaust memory.
DNS is stubbed so IP literals resolve to themselves and names to a
public address — the suite tests the guard, not the network.
"""

import asyncio
import ipaddress
import socket

import httpx
import pytest

from app.checker import run_check, ssrf_check
from app.store import CheckStore


def _dns(host, *a, **k):
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    fam = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
    return [(fam, socket.SOCK_STREAM, 6, "", (host, 0))]


@pytest.fixture(autouse=True)
def _literal_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _dns)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://127.0.0.1:8080/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "http://[::1]/",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ],
)
def test_ssrf_guard_rejects_non_public_targets(url):
    with pytest.raises(ValueError):
        ssrf_check(url)


def test_ssrf_guard_allows_public_https():
    ssrf_check("https://example.com/v1/thing")  # must not raise


def test_internal_target_is_never_fetched(tmp_path):
    called_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host)
        return httpx.Response(404, json={"error": "no row"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store = CheckStore(str(tmp_path / "checks.db"))
    result = asyncio.run(
        run_check("http://127.0.0.1:8080/admin", store, client=client)
    )
    assert "127.0.0.1" not in called_hosts
    assert result["liveness"]["alive"] is False
    assert "refused" in (result["liveness"]["parse_error"] or "") or result["reasons"]
    assert result["verdict"] == "AVOID"


def test_oversized_target_body_is_capped(tmp_path):
    big = b"x" * (3 * 1024 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "facilitator.payai.network":
            return httpx.Response(404, json={"error": "no row"})
        return httpx.Response(200, content=big)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store = CheckStore(str(tmp_path / "checks.db"))
    result = asyncio.run(
        run_check("https://target.example.com/big", store, client=client)
    )
    assert result["liveness"]["alive"] is False
    assert result["verdict"] == "AVOID"
