"""A capability satellite inside the UNI bubble.

The live hub hosts nothing of its own: 99 capabilities, 0 local, 7 federated sources. The
bubble had one locally published capability and no peers at all, which is the single most
obvious way to tell the two apart from the inside. This is the service that closes that gap —
one program, instantiated once per bubble satellite with a different catalogue.

What it has to be, to be indexed by a real hub rather than a lenient one:

* it serves `/.well-known/ai-market.json` with `name`, `protocol_versions`, `manifest_url`
  and `signer_public_key` — the four fields `validate_well_known` requires;
* it serves a manifest whose Ed25519 signature verifies under exactly the canonical the hub
  computes in `Signer.manifest_canonical`. That canonical hashes `tools` with
  ``json.dumps(sort_keys=True, ensure_ascii=False)`` and **default separators** — a compact
  dump produces a different digest and a signature that fails with no useful message;
* `generated_at` must be fresh, because the crawler rejects a stale manifest as a replay.
  So the manifest is built per request rather than cached;
* every row declares `source_hub: "local"`. The crawler indexes only what a peer originates
  — a row naming anyone else is a re-export and is skipped.

The bubble constraint runs through all of it: a capability may not reach the network, may not
call a model, and may not consult the outside world in any way. Everything here is a pure
function of its input, computed locally, from the standard library. That is not a limitation
imposed by the simulation — it is what makes the results real inside it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uni.capabilities import Catalogue, load_catalogue  # noqa: E402

HUB_VERSION = "3.2.1"
PROTOCOL_RELEASE = "0.1.0"
MAX_REQUEST_BYTES = 1_000_000


class Signer:
    """Ed25519, persisted. The hub pins this key on first contact and refuses the peer
    forever after if it changes, so losing it is not recoverable by restarting."""

    def __init__(self, key_path: Path):
        self.key_path = key_path
        if key_path.exists():
            self._key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        else:
            self._key = Ed25519PrivateKey.generate()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(self._key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ))
            key_path.chmod(0o600)

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )).decode()

    def sign_canonical(self, canonical: str) -> str:
        return base64.b64encode(self._key.sign(canonical.encode())).decode()


def manifest_canonical(manifest: dict[str, Any]) -> str:
    """Byte-for-byte the hub's `Signer.manifest_canonical`.

    Deliberately duplicated rather than imported: a satellite is a separate program that
    could be written by anyone, and the whole point of the exercise is that it interoperates
    with the hub over the wire. Note the plain `json.dumps` — no `separators` — because that
    is what the hub does, and a "tidier" compact dump here silently breaks every signature.
    """
    tools_hash = hashlib.sha256(
        json.dumps(manifest.get("tools", []), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    by_hub_hash = hashlib.sha256(
        json.dumps(manifest.get("by_hub", {}), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return (
        f"capabilities_count:{manifest.get('capabilities_count', 0)}"
        f"|generated_at:{manifest.get('generated_at', '')}"
        f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
        f"|tools_hash:{tools_hash}"
        f"|by_hub_hash:{by_hub_hash}"
    )


def provider_canonical(capability_id: str, product_id: str, payload: Any, result: Any) -> str:
    """What `supply_security.verify_provider_response` checks, bound to the request.

    The hub does not verify this on the federated path — it trusts the peer through the
    pinned manifest key instead. It is signed anyway: the same catalogue can be published
    as a local capability, where the hub does verify it, and a provider that only signs
    when it is being watched is not the thing being simulated.
    """
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


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Satellite:
    def __init__(self, catalogue: Catalogue, public_url: str, signer: Signer):
        self.catalogue = catalogue
        self.public_url = public_url.rstrip("/")
        self.signer = signer
        self.started = time.time()
        # Observed traffic, so `success_rate_30d` is a measurement rather than a decoration.
        # The hub ignores a peer-declared rate when indexing — it scores peers itself — but
        # a satellite that publishes an invented number is lying to every other reader.
        self.attempts: dict[str, int] = {}
        self.successes: dict[str, int] = {}

    # ── documents ────────────────────────────────────────────────────────────────
    def well_known(self) -> dict[str, Any]:
        return {
            "name": self.catalogue.name,
            "protocol_versions": ["v1", "v2"],
            "hub_version": HUB_VERSION,
            "protocol_release_version": PROTOCOL_RELEASE,
            # A peer that advertises `mcp_endpoint` is sent the
            # {capability_id, input, product_id, source_hub} envelope there. Without it the
            # hub falls back to /capabilities/{product}/{cap}/invoke with the bare input.
            "mcp_endpoint": f"{self.public_url}/ai-market/v2/invoke",
            "manifest_url": f"{self.public_url}/ai-market/v2/manifest",
            "products_count": 1,
            "capabilities_count": len(self.catalogue.capabilities),
            "federated_capabilities_count": 0,
            "supported_chains": ["base"],
            "supported_tokens": ["USDC"],
            "signer_public_key": self.signer.public_key_b64,
            "peers": [],
        }

    def tools(self) -> list[dict[str, Any]]:
        out = []
        for cap in self.catalogue.capabilities:
            attempts = self.attempts.get(cap.capability_id, 0)
            successes = self.successes.get(cap.capability_id, 0)
            out.append({
                "name": f"{self.catalogue.product_id}.{cap.capability_id}",
                "description": cap.description,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "price_per_call_usd": cap.price_usd,
                "p50_latency_ms": cap.p50_latency_ms,
                "success_rate_30d": (successes / attempts) if attempts else 0.5,
                "reputation_basis": "measured" if attempts else "unobserved",
                "observations_30d": attempts,
                "product_id": self.catalogue.product_id,
                "capability_id": cap.capability_id,
                # "local" — this satellite ORIGINATES every row it publishes. Naming anyone
                # else here makes the row a re-export, and the hub skips those.
                "source_hub": "local",
                "source_hub_name": self.catalogue.name,
            })
        return out

    def manifest(self) -> dict[str, Any]:
        tools = self.tools()
        by_hub = {
            "local": {
                "capabilities_count": len(tools),
                "trust_score": 1.0,
                "trust_basis": "self",
                "observations_30d": sum(self.attempts.values()),
                "last_crawl": _now(),
            }
        }
        body = {
            "protocol_version": "v2",
            "release_version": PROTOCOL_RELEASE,
            # Rebuilt per request: the crawler rejects a manifest whose signed timestamp is
            # older than its max age, reading it as a replay.
            "generated_at": _now(),
            "base_url": self.public_url,
            "products_count": 1,
            "capabilities_count": len(tools),
            "total_capabilities": len(tools),
            "local_capabilities": len(tools),
            "federated_capabilities": 0,
            "hubs_indexed": 0,
            "tools": tools,
            "by_hub": by_hub,
        }
        body["signature"] = {
            "algorithm": "ed25519",
            "public_key": self.signer.public_key_b64,
            "value": self.signer.sign_canonical(manifest_canonical(body)),
        }
        return body

    # ── invoke ───────────────────────────────────────────────────────────────────
    def invoke(self, capability_id: str, payload: Any) -> tuple[int, dict[str, Any], str]:
        cap = self.catalogue.by_id.get(capability_id)
        if cap is None:
            # Same shape the hub uses, so a caller cannot tell a bubble 404 from a real one.
            return 404, {"success": False, "error": "capability_not_found",
                          "detail": f"{capability_id} is not published here"}, ""
        self.attempts[capability_id] = self.attempts.get(capability_id, 0) + 1
        if not isinstance(payload, dict):
            return 400, {"success": False, "error": "invalid_input",
                          "detail": "input must be a JSON object"}, ""
        try:
            result = cap.run(payload)
        except ValueError as exc:
            # A bad input is the caller's fault and must not count against the capability's
            # success rate as if the computation had failed.
            return 400, {"success": False, "error": "invalid_input", "detail": str(exc)}, ""
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return 500, {"success": False, "error": "capability_failed",
                          "detail": f"{type(exc).__name__}"}, ""
        self.successes[capability_id] = self.successes.get(capability_id, 0) + 1
        signature = self.signer.sign_canonical(
            provider_canonical(capability_id, self.catalogue.product_id, payload, result)
        )
        return 200, {"success": True, "result": result}, signature


def make_handler(sat: Satellite):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "AIMarketSatellite/1.0"

        def _send(self, code: int, body: Any, extra: dict[str, str] | None = None) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(raw)))
            self.send_header("cache-control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/.well-known/ai-market.json":
                self._send(200, sat.well_known())
            elif path in ("/ai-market/v2/manifest", "/ai-market/manifest"):
                self._send(200, sat.manifest())
            elif path in ("/health", "/ai-market/v2/health"):
                self._send(200, {"status": "ok", "capabilities": len(sat.catalogue.capabilities),
                                 "uptime_s": int(time.time() - sat.started)})
            elif path == "/":
                self._send(200, {
                    "name": sat.catalogue.name,
                    "description": sat.catalogue.description,
                    "capabilities": len(sat.catalogue.capabilities),
                    "manifest": f"{sat.public_url}/ai-market/v2/manifest",
                })
            else:
                self._send(404, {"success": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_REQUEST_BYTES:
                self._send(413, {"success": False, "error": "payload_too_large"})
                return
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"success": False, "error": "invalid_json"})
                return
            if not isinstance(request, dict):
                self._send(400, {"success": False, "error": "invalid_json"})
                return

            if path in ("/ai-market/v2/invoke", "/invoke"):
                capability_id = str(request.get("capability_id") or "")
                payload = request.get("input")
            else:
                # The legacy shape the hub falls back to for a peer with no mcp_endpoint:
                # /capabilities/{product}/{capability}/invoke carrying the bare input.
                parts = [p for p in path.split("/") if p]
                if len(parts) == 4 and parts[0] == "capabilities" and parts[3] == "invoke":
                    capability_id = parts[2]
                    payload = request
                else:
                    self._send(404, {"success": False, "error": "not_found"})
                    return

            code, body, signature = sat.invoke(capability_id, payload)
            self._send(code, body, {"X-Provider-Signature": signature} if signature else None)

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def main() -> None:
    name = os.environ.get("UNI_SAT_CATALOGUE", "")
    if not name:
        raise SystemExit("UNI_SAT_CATALOGUE is required (e.g. khronos)")
    public_url = os.environ.get("UNI_SAT_PUBLIC_URL", "")
    if not public_url:
        raise SystemExit("UNI_SAT_PUBLIC_URL is required — it goes into every advertised URL")
    host = os.environ.get("UNI_SAT_HOST", "127.0.0.1")
    port = int(os.environ.get("UNI_SAT_PORT", "9300"))
    key_path = Path(os.environ.get("UNI_SAT_KEY", f"/var/lib/uni-satellites/{name}.pem"))

    catalogue = load_catalogue(name)
    signer = Signer(key_path)
    sat = Satellite(catalogue, public_url, signer)
    print(f"{catalogue.name}: {len(catalogue.capabilities)} capabilities at {public_url}",
          flush=True)
    print(f"signer_public_key: {signer.public_key_b64}", flush=True)
    ThreadingHTTPServer((host, port), make_handler(sat)).serve_forever()


if __name__ == "__main__":
    main()
