"""The policy signer's credentials stay at the configured endpoint."""
from __future__ import annotations

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from aimarket_hub.escrow_bridge import signer
from aimarket_hub.escrow_bridge.errors import SubmissionRefused


def _tx():
    return signer.UnsignedTx(to="0x" + "11" * 20, data="0x", chain_id=1, gas=1)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_signer_refuses_redirects_without_forwarding_its_token(status):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.respond()

        def do_GET(self):
            self.respond()

        def respond(self):
            seen.append((self.path, self.headers.get("Authorization")))
            if self.path == "/sign":
                self.send_response(status)
                self.send_header("Location", "/sink")
            else:
                self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        client = signer.ExternalSigner(url=f"http://127.0.0.1:{server.server_port}/sign", token="test-token")
        with pytest.raises(SubmissionRefused, match=f"HTTP {status}"):
            client.submit(_tx())
        assert seen == [("/sign", "Bearer test-token")]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("raw, message", [
    (b"[]", "did not return a transaction hash"),
    (b" " * (signer._MAX_SIGNER_REPLY_BYTES + 1), "response exceeds the size limit"),
])
def test_signer_bounds_and_validates_responses(monkeypatch, raw, message):
    monkeypatch.setattr(signer, "_open_signer", lambda *args, **kwargs: io.BytesIO(raw))
    with pytest.raises(SubmissionRefused, match=message):
        signer.ExternalSigner(url="https://signer.invalid").submit(_tx())
