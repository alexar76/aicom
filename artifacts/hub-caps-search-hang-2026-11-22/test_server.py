"""Local check of the capability-search fix: serve a page, pass every other GET to modelmarket.dev, and hold the
second catalogue page (offset > 0) for 1.5 s so that a second keystroke always lands while it is loading: the case
that froze the tab. GET /__stats counts catalogue page requests. Usage:
  PORT=8781 python3 test_server.py page.html
"""
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

UPSTREAM = "https://modelmarket.dev"
HTML = open(sys.argv[1], "rb").read()
STATE = {"pages": 0, "later_pages": 0}


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
        if u.path == "/__stats":
            return self.send(200, json.dumps(STATE).encode(), "application/json")
        if u.path == "/ai-market/v2/search" and parse_qs(u.query).get("intent", [""])[0] == "":
            STATE["pages"] += 1
            if int(parse_qs(u.query).get("offset", ["0"])[0]) > 0:
                STATE["later_pages"] += 1
                time.sleep(1.5)
        req = urllib.request.Request(UPSTREAM + self.path, headers={"User-Agent": "caps-search-test/1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body, ctype, code = r.read(), r.headers.get("Content-Type", "application/octet-stream"), r.status
        except urllib.error.HTTPError as e:
            body, ctype, code = e.read(), e.headers.get("Content-Type", "text/plain"), e.code
        return self.send(code, body, ctype)


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8781"))), Handler).serve_forever()
