from unittest.mock import MagicMock

from web.backend.http.client_ip import client_ip


def test_client_ip_uses_xff_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "10.0.0.1")
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers.get.return_value = "203.0.113.50, 10.0.0.1"
    assert client_ip(request) == "203.0.113.50"


def test_client_ip_ignores_xff_from_untrusted_peer(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TRUSTED_PROXY_IPS", "127.0.0.1")
    request = MagicMock()
    request.client.host = "203.0.113.99"
    request.headers.get.return_value = "1.2.3.4"
    assert client_ip(request) == "203.0.113.99"
