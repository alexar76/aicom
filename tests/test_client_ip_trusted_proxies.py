"""Behind a published container port the backend's peer is the docker bridge gateway, so
the trusted-proxy list must be able to name it (or its network) — otherwise every visitor
shares one address and per-IP limits are global."""

from types import SimpleNamespace

from web.backend.http.client_ip import client_ip


def _req(peer, xff=""):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"x-forwarded-for": xff} if xff else {})


def test_a_gateway_named_in_the_list_is_believed(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "127.0.0.1,::1,172.18.0.1")
    assert client_ip(_req("172.18.0.1", "198.51.100.7")) == "198.51.100.7"


def test_a_cidr_entry_covers_its_network(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "172.18.0.0/16")
    assert client_ip(_req("172.18.0.9", "1.2.3.4, 198.51.100.7")) == "198.51.100.7"


def test_an_untrusted_peer_is_never_believed(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    assert client_ip(_req("172.18.0.1", "198.51.100.7")) == "172.18.0.1"


def test_the_right_most_untrusted_hop_wins(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "172.18.0.0/16,127.0.0.1")
    assert client_ip(_req("172.18.0.1", "6.6.6.6, 198.51.100.7, 127.0.0.1")) == "198.51.100.7"
