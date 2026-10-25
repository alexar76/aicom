"""Vault credentials must stay on their configured origin, including redirects."""

from __future__ import annotations

import io
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from security import secret_resolver as sr

pytestmark = pytest.mark.component_integration


@contextmanager
def vault_server(redirect):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("X-Vault-Token")))
            if redirect.get("to") and self.path != "/value":
                self.send_response(302)
                self.send_header("Location", redirect["to"])
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"data": {"data": {"value": "fixture-value"}}}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("cross_origin", [False, True], ids=["same-origin", "different-port"])
def test_vault_redirect_preserves_the_token_boundary(monkeypatch, cross_origin):
    redirect = {}
    with vault_server({}) as (other, received), vault_server(redirect) as (source, sent):
        redirect["to"] = f"{other if cross_origin else source}/value"
        monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_ADDR", source)
        monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_TOKEN", "vault-fixture-token")
        result = sr._read_hashicorp("aicom/fixture")
        assert sent[0][1] == "vault-fixture-token"
        if cross_origin:
            assert result is None
            assert received == [], "a rejected origin must receive neither a request nor a token"
        else:
            assert result == {"value": "fixture-value"}
            assert sent[-1] == ("/value", "vault-fixture-token")


@pytest.mark.parametrize("address", [
    "file:///private/tmp/vault", "ftp://vault.invalid", "https://user:pass@vault.invalid",
    "https://vault.invalid/?token=x", "https://vault.invalid/#fragment", "https://[bad",
])
def test_invalid_vault_address_is_rejected_before_network(monkeypatch, address):
    monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_ADDR", address)
    monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_TOKEN", "vault-fixture-token")

    def unexpected(*_args):
        pytest.fail("an invalid Vault address reached the network")

    monkeypatch.setattr(sr.request, "build_opener", unexpected)
    assert sr._read_hashicorp("aicom/fixture") is None


@pytest.mark.parametrize("payload", [
    b"[]", b'{"data": []}', b'{"data":{"data":[]}}', b"\xff", b"x" * 1_048_577,
], ids=["array", "bad-envelope", "bad-secret", "invalid-utf8", "oversized"])
def test_malformed_vault_response_fails_closed(monkeypatch, payload):
    monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_ADDR", "https://vault.invalid")
    monkeypatch.setenv("AIFACTORY_HASHICORP_VAULT_TOKEN", "vault-fixture-token")
    opener = SimpleNamespace(open=lambda *_args, **_kwargs: io.BytesIO(payload))
    monkeypatch.setattr(sr.request, "build_opener", lambda *_args: opener)
    assert sr._read_hashicorp("aicom/fixture") is None
