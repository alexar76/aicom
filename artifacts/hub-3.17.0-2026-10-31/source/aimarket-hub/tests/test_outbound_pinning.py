"""SSRF DNS-rebinding pin for outbound_http (_pin_target)."""

import socket

import pytest

from aimarket_hub import outbound_http as oh


def _fake_gai(ip):
    def gai(host, port, *a, **k):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]
    return gai


def test_pin_http_public_rewrites_to_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("93.184.216.34"))
    target, headers, ext = oh._pin_target("http://example.com/x")
    assert target == "http://93.184.216.34/x"
    assert headers == {"Host": "example.com"}
    assert ext == {}  # no SNI for plain http


def test_pin_https_adds_sni(monkeypatch):
    if not oh._HTTPS_PIN_OK:
        pytest.skip("httpx too old to pin https safely")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("93.184.216.34"))
    target, headers, ext = oh._pin_target("https://example.com/x")
    assert target == "https://93.184.216.34/x"
    assert headers == {"Host": "example.com"}
    assert ext == {"sni_hostname": "example.com"}  # cert validated against hostname


def test_pin_blocks_rebind_to_private(monkeypatch):
    # Hostname that (post-validation) resolves to a private IP must be rejected.
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("10.1.2.3"))
    with pytest.raises(ValueError):
        oh._pin_target("http://rebind.example/latest/meta-data/")


@pytest.mark.parametrize("ip", ["198.18.0.10", "192.0.2.7", "240.0.0.1", "2001:db8::1"])
def test_pin_refuses_what_validation_refuses(monkeypatch, ip):
    # The pin is the answer actually connected to: a name that answered a public address to
    # the validation lookup and a benchmark, documentation or reserved one now is refused here.
    from aimarket_hub import crawler

    assert crawler._is_private_url(f"http://[{ip}]/x" if ":" in ip else f"http://{ip}/x")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai(ip))
    with pytest.raises(ValueError, match="blocked network"):
        oh._pin_target("https://rebind.example/x")


def test_async_callers_resolve_off_the_event_loop(monkeypatch):
    import asyncio
    import threading
    import time

    loop_thread = []

    def slow(host, port, *a, **k):
        loop_thread.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.4)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", slow)
    ticks = 0

    async def ticker():
        nonlocal ticks
        end = time.monotonic() + 0.35
        while time.monotonic() < end:
            await asyncio.sleep(0.01)
            ticks += 1

    async def go():
        beat = asyncio.create_task(ticker())
        with pytest.raises(ValueError):
            await oh.safe_post_capped("https://slow-dns.example/x", json={}, max_bytes=10)
        await beat

    asyncio.run(go())
    assert loop_thread and not any(loop_thread), "getaddrinfo ran on the event loop's thread"
    assert ticks > 10, "the event loop stood still while a name resolved"


def test_pin_allow_hosts_bypasses(monkeypatch):
    # A configured gateway / localhost is exempt (not pinned, not blocked).
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("127.0.0.1"))
    target, headers, ext = oh._pin_target(
        "http://host.docker.internal:9000/invoke",
        allow_hosts={"host.docker.internal"},
    )
    assert target == "http://host.docker.internal:9000/invoke"
    assert headers == {} and ext == {}


def test_pin_literal_ip_unchanged():
    target, headers, ext = oh._pin_target("http://93.184.216.34:8080/x")
    assert target == "http://93.184.216.34:8080/x"
    assert headers == {} and ext == {}


def test_pin_preserves_port(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai("93.184.216.34"))
    target, _, _ = oh._pin_target("http://example.com:8443/x")
    assert target == "http://93.184.216.34:8443/x"


def test_pin_dns_failure_is_fail_closed(monkeypatch):
    def fail_resolution(*_args, **_kwargs):
        raise socket.gaierror("temporary failure")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)
    with pytest.raises(ValueError, match="cannot safely resolve"):
        oh._pin_target("https://unresolved.example/x")


def test_invoke_allow_hosts_env(monkeypatch):
    monkeypatch.delenv("AIMARKET_ALLOW_LOCAL_PUBLISH", raising=False)
    monkeypatch.setenv("AIMARKET_INVOKE_HOST_GATEWAY", "host.docker.internal")
    assert oh._invoke_allow_hosts() == {"host.docker.internal"}
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    assert oh._invoke_allow_hosts() == {"host.docker.internal", "127.0.0.1", "localhost", "::1"}
