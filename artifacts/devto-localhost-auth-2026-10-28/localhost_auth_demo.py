"""Educational HTTP reconstruction; fixed localhost targets, no MCP dependency."""
from contextlib import contextmanager
from hmac import compare_digest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import json
import secrets
from threading import Thread


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No request or credential logging in this demonstration.


def backend_handler(require_key, key):
    class Backend(QuietHandler):
        def do_GET(self):
            if self.path != "/private":
                self.send_error(404)
                return
            peer = self.client_address[0]
            supplied = self.headers.get("Authorization", "").encode("utf-8")
            accepted = (
                compare_digest(supplied, f"Bearer {key}".encode("ascii"))
                if require_key else ip_address(peer).is_loopback
            )
            payload = json.dumps({"accepted": accepted, "peer": peer}).encode()
            self.send_response(200 if accepted else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Backend


def relay_handler(upstream_port):
    class Relay(QuietHandler):
        def do_GET(self):
            # Fixed upstream/path; no URL supplied by the caller.
            headers = {}
            if "Authorization" in self.headers:
                headers["Authorization"] = self.headers["Authorization"]
            conn = HTTPConnection("127.0.0.1", upstream_port, timeout=3)
            try:
                conn.request("GET", "/private", headers=headers)
                response = conn.getresponse()
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            finally:
                conn.close()
    return Relay


def request(port, key=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        conn.request("GET", "/private", headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def main():
    key = secrets.token_urlsafe(32)
    results = []
    for mode, require_key in (("peer-only", False), ("bearer", True)):
        with serve(backend_handler(require_key, key)) as backend:
            with serve(relay_handler(backend)) as relay:
                cases = [("direct, no key", backend, None, 401 if require_key else 200),
                         ("relay, no key", relay, None, 401 if require_key else 200)]
                if require_key:
                    cases += [("direct, wrong key", backend, "wrong-demo-key", 401),
                              ("relay, wrong key", relay, "wrong-demo-key", 401),
                              ("direct, valid key", backend, key, 200),
                              ("relay, valid key", relay, key, 200)]
                for label, port, credential, expected in cases:
                    status, body = request(port, credential)
                    assert status == expected, (mode, label, status)
                    assert body["peer"] == "127.0.0.1", body
                    assert body["accepted"] == (status == 200), body
                    results.append({"gate": mode, "path": label,
                                    "status": status, "backend_peer": body["peer"]})
    print(json.dumps({"scope": "educational HTTP reconstruction; all listeners and clients use IPv4 loopback",
                      "checks": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
