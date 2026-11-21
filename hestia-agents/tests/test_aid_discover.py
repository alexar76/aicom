"""aid.discover@v1 against a simulated domain whose endpoint signs real proofs.

The handler runs here with a fetch() that answers like the hearth: the two resolvers return a
record carrying the test key, and the endpoint signs its answer with that key over the request
the handler actually sent (its Accept-Signature, its AID-Domain), the way the live hub does. A
second key, an endpoint that ignores AID-Domain, and an endpoint on another host cover the
failures. The generated handler must be what scripts/build_aid_discover.py writes.
"""
# ruff: noqa: E501 — long literal lines (recorded headers, generated glue)

from __future__ import annotations

import base64
import hashlib
import json
import re
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from hestia_agents.manifests import AGENTS, deploy_body, handler_source

KEY = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"aid-discover test key").digest())
K = base64.urlsafe_b64encode(KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).rstrip(b"=").decode()
SEED = hashlib.sha256(b"one call").hexdigest()
DATE = "Fri, 20 Nov 2026 18:00:00 GMT"


class Reply:
    def __init__(self, status=200, headers=None, text="", error=None):
        self.status, self.headers, self.text, self.error = status, headers or {}, text, error

    @property
    def ok(self):
        return 200 <= self.status < 300


def dns(record):
    answer = [{"name": "_agent.agents.example.com", "type": 16, "TTL": 300, "data": record}] if record else []
    return Reply(200, {"date": DATE}, json.dumps({"Status": 0 if record else 3, "AD": True, "Answer": answer}))


def endpoint(key=KEY, *, bind=True, status=200, uri_host="agents.example.com"):
    """An endpoint that answers the proof request the handler sent."""
    def answer(url, headers):
        ask = headers["Accept-Signature"]
        nonce = re.search(r'nonce="([^"]+)"', ask).group(1)
        kid = re.search(r'keyid="([^"]+)"', ask).group(1)
        domain = headers.get("AID-Domain") if bind else None
        covered = '"@method";req "@target-uri";req "@authority";req ' + ('"aid-domain";req ' if domain else "") + '"@status"'
        now = int(time.time())
        params = f'({covered});created={now};expires={now + 60};keyid="{kid}";alg="ed25519";nonce="{nonce}";tag="aid-pka-v2"'
        lines = ['"@method";req: GET', f'"@target-uri";req: {url}', f'"@authority";req: {uri_host}']
        if domain:
            lines.append(f'"aid-domain";req: {domain}')
        lines += [f'"@status": {status}', f'"@signature-params": {params}']
        sig = base64.b64encode(key.sign("\n".join(lines).encode())).decode()
        return Reply(status, {"signature-input": "aid-pka=" + params, "signature": f"aid-pka=:{sig}:",
                              "cache-control": "no-store"}, "{}")
    return answer


def load(record, ep=None, *, seed=SEED):
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        asked.append((url, dict(headers or {})))
        if "dns-query" in url or "dns.google" in url:
            return dns(record)
        return ep(url, headers or {})

    namespace = {"fetch": fetch, "CALL_NONCE": seed}
    exec(compile(handler_source("aid-discover"), "aid-discover", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked


RECORD = f"v=aid2;u=https://agents.example.com/mcp;p=mcp;a=none;s=Example;k={K}"


def test_a_bound_proof_over_the_hearths_nonce_is_proven_bound() -> None:
    handle, asked = load(RECORD, endpoint())
    out = handle({"domain": "agents.example.com"})
    assert out["verdict"] == "proven_bound", out
    assert out["proof"]["verified"] is True and out["proof"]["domain_bound"] is True
    sent = asked[-1][1]
    nonce = base64.urlsafe_b64encode(bytes.fromhex(SEED)).decode().rstrip("=")
    assert asked[-1][0] == "https://agents.example.com/mcp"
    assert sent["AID-Domain"] == "agents.example.com" and f'nonce="{nonce}"' in sent["Accept-Signature"]
    assert sent["Cache-Control"] == "no-store" and out["exchange"]["nonce"] == nonce


def test_an_endpoint_that_ignores_aid_domain_is_proven_unbound_or_refused() -> None:
    handle, _ = load(RECORD, endpoint(bind=False))
    assert handle({"domain": "agents.example.com"})["verdict"] == "proven_unbound"
    out = handle({"domain": "agents.example.com", "require_domain_binding": True})
    assert out["verdict"] == "proof_failed" and "domain_binding" in out["proof"]["failed"]


def test_another_key_fails_the_proof() -> None:
    other = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"impostor").digest())
    handle, _ = load(RECORD, endpoint(key=other))
    out = handle({"domain": "agents.example.com"})
    assert out["verdict"] == "proof_failed" and out["error"] == "ERR_SECURITY"
    assert out["proof"]["failed"] == ["signature"]


def test_an_endpoint_on_another_host_must_be_named_by_the_caller() -> None:
    record = f"v=aid2;u=https://api.other-host.example.net/mcp;p=mcp;a=none;k={K}"
    handle, asked = load(record, endpoint(uri_host="api.other-host.example.net"))
    out = handle({"domain": "agents.example.com"})
    assert out["verdict"] == "endpoint_host_not_named" and out["endpoint_host"] == "api.other-host.example.net"
    assert all("other-host" not in url for url, _ in asked)          # never fetched
    out = handle({"domain": "agents.example.com", "endpoint": "https://api.other-host.example.net/"})
    assert out["verdict"] == "proven_bound"


@pytest.mark.parametrize(("record", "verdict"), [
    (None, "no_valid_record"),
    ("v=aid2;u=https://agents.example.com/mcp;p=mcp;a=none", "found_unproven"),
    (f"v=aid2;u=wss://agents.example.com/s;p=websocket;a=none;k={K}", "found_unproven"),
    ("v=aid2;u=https://agents.example.com/mcp;p=telnet", "no_valid_record"),
])
def test_records_that_allow_no_proof(record, verdict) -> None:
    handle, asked = load(record, endpoint())
    out = handle({"domain": "agents.example.com"})
    assert out["verdict"] == verdict, out
    assert all("agents.example.com/" not in url for url, _ in asked)


def test_bad_input_and_a_hearth_without_a_nonce_are_refused() -> None:
    handle, _ = load(RECORD, endpoint())
    for payload in ({}, {"domain": 5}, {"domain": "_agent.agents.example.com"}, {"domain": "https://x.example.com"}):
        with pytest.raises(ValueError):
            handle(payload)
    no_nonce, _ = load(RECORD, endpoint(), seed="")
    with pytest.raises(ValueError, match="call nonce"):
        no_nonce({"domain": "agents.example.com"})


def test_the_manifest_lets_the_caller_name_the_hosts() -> None:
    body = deploy_body("aid-discover")
    assert body["egress_input_fields"] == ["domain", "endpoint"]
    assert body["egress_hosts"] == ["cloudflare-dns.com", "dns.google"]
    assert AGENTS["aid-discover"]["sandbox_only"] is True


def test_the_generated_handler_is_current() -> None:
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parent.parent / "scripts" / "build_aid_discover.py"
    spec = importlib.util.spec_from_file_location("build_aid_discover", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build() == handler_source("aid-discover")


def test_resolvers_that_did_not_answer_are_not_a_missing_record() -> None:
    namespace = {"CALL_NONCE": SEED}

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        raise RuntimeError("egress refused: this agent's egress budget (60/min) is spent")

    namespace["fetch"] = fetch
    exec(compile(handler_source("aid-discover"), "aid-discover", "exec"), namespace)  # noqa: S102
    out = namespace["handle"]({"domain": "agents.example.com"})
    assert out["verdict"] == "lookup_failed" and out["code"] == 1004
