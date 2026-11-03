"""Local check of the peers refresh: serve a patched terminal-home.html, pass every other GET to modelmarket.dev.

GET /__fake?on=1 adds a made-up hub to the pending list of /ai-market/v2/federation/peers (on=0 removes it);
GET /__stats says how many times the page asked for the peers list. Usage:
  PORT=8771 python3 test_server.py variant-1ea4/terminal-home.patched.html
"""
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

UPSTREAM = "https://modelmarket.dev"
HTML = open(sys.argv[1], "rb").read()
STATE = {"fake": False, "peers_requests": 0}
FAKE = {"url": "https://fake-hub.example", "name": "fake hub (local test)", "first_seen": "2026-11-02T00:00:00Z",
        "discoverer": "local-test", "assay_verdict": "review", "assay_blockers": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.send(200, HTML, "text/html; charset=utf-8")
        if u.path == "/__fake":
            STATE["fake"] = parse_qs(u.query).get("on", ["1"])[0] == "1"
            return self.send(200, json.dumps(STATE).encode(), "application/json")
        if u.path == "/__stats":
            return self.send(200, json.dumps(STATE).encode(), "application/json")
        req = urllib.request.Request(UPSTREAM + self.path, headers={"User-Agent": "peers-refresh-test/1"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body, ctype, code = r.read(), r.headers.get("Content-Type", "application/octet-stream"), r.status
        except urllib.error.HTTPError as e:
            body, ctype, code = e.read(), e.headers.get("Content-Type", "text/plain"), e.code
        if u.path == "/ai-market/v2/federation/peers" and code == 200:
            STATE["peers_requests"] += 1
            data = json.loads(body)
            if STATE["fake"]:
                data["pending"] = list(data.get("pending") or []) + [FAKE]
            body = json.dumps(data).encode()
        return self.send(code, body, ctype)


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8771"))), Handler).serve_forever()
