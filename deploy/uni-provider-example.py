"""A capability provider inside the bubble — and a properly signed one.

The hub's production policy requires every provider response to be Ed25519-signed and BOUND
to the request that asked for it (capability id + product id + a hash of the input), so a
signature cannot be replayed against a different call. The bubble runs that same policy
rather than switching it off, because a simulation that relaxes the rules it is simulating
stops being one.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_PATH = Path("/var/lib/uni_provider_key")

if KEY_PATH.exists():
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
else:
    key = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    KEY_PATH.chmod(0o600)

PUBKEY_B64 = base64.b64encode(
    key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
).decode()
Path("/var/lib/uni_provider_pubkey").write_text(PUBKEY_B64 + "\n")


def canonical(capability_id: str, product_id: str, payload, result) -> str:
    input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(
        {
            "capability_id": capability_id or "",
            "product_id": product_id or "",
            "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(),
            "result": result,
        },
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0) or 0)
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            request = {}
        # The hub posts an ENVELOPE — {"input": …, "product_id": …, "capability_id": …} —
        # and binds the signature to `input` alone, not to the envelope. Signing the whole
        # body instead produces a valid signature over the wrong canonical, which the hub
        # reports as "invalid provider response signature": correct, and impossible to
        # diagnose from the message.
        # Nothing a caller can see may name the realm. This is the reference provider, so
        # what it returns is what every copy of it returns — and the invariant is that from
        # the inside the bubble is indistinguishable from the live economy.
        result = {"answer": "ok", "echo": request.get("input"), "signed": True}
        signature = base64.b64encode(
            key.sign(canonical(
                request.get("capability_id", ""), request.get("product_id", ""),
                request.get("input"), result,
            ).encode())
        ).decode()
        body = json.dumps({"success": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.send_header("X-Provider-Signature", signature)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"provider pubkey: {PUBKEY_B64}", flush=True)
    HTTPServer(("172.17.0.1", 9195), H).serve_forever()
