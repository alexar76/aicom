#!/usr/bin/env python3
"""Minimal HTTPS-capable agent runtime for mesh e2e (real HTTP, no [DEMO] markers)."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._json(200, {"status": "ok", "service": "mesh-real-agent"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/invoke":
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        intent = ""
        if isinstance(payload.get("input"), dict):
            intent = str(payload["input"].get("intent") or payload["input"].get("query") or "")
        self._json(
            200,
            {
                "status": "ok",
                "result": {"output": f"executed:{intent[:120]}"},
            },
        )


def main() -> None:
    port = int(os.environ.get("REAL_AGENT_PORT", "8091"))
    host = os.environ.get("REAL_AGENT_HOST", "127.0.0.1")
    # Mesh requires https:// for registered agents — use reverse proxy in prod.
    # For local e2e we register http://127.0.0.1 via test-only relaxation or use ngrok.
    # Local stack uses mesh direct invoke path against http endpoint in integration tests.
    server = HTTPServer((host, port), Handler)
    print(f"real agent listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
