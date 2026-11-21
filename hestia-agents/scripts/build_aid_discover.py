"""Build agents/aid-discover/handler.py from agents/aid-record and agents/aid-proof.

    python scripts/build_aid_discover.py

aid.discover@v1 does what the two agents do, end to end, in one call: the DNS lookup and record
rules of aid-record, then the endpoint proof request and the verifier rules of aid-proof against
the live endpoint. Their sources are embedded verbatim and run in namespaces of their own, so the
two published checks and this one cannot drift apart. tests/test_aid_discover.py fails when the
committed file is not what this script writes.
"""
# ruff: noqa: E501 — long literal lines (recorded headers, generated glue)

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"

GLUE = r'''

# ------------------------------------------------------------------ the two checks, as embedded

import base64 as _base64
import time as _time

_RECORD = {"__name__": "aid_record", "fetch": fetch}  # noqa: F821 — the sandbox provides fetch()
exec(compile(RECORD_SOURCE, "aid-record/handler.py", "exec"), _RECORD)
_PROOF = {"__name__": "aid_proof"}
exec(compile(PROOF_SOURCE, "aid-proof/handler.py", "exec"), _PROOF)

SPEC = "AID v2.1.1: sections 2.1-2.3 (record) and Appendix B (endpoint proof, B.7 domain binding)"


def _host_of(uri):
    rest = uri.split("://", 1)[1] if "://" in uri else ""
    return rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].rsplit("@", 1)[-1].split(":", 1)[0].lower()


def _named(payload, name):
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    return (_host_of(text) if "://" in text else text.lower().rstrip("."))


def handle(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("domain"), str):
        raise ValueError("send domain: the host whose agent you want to find, e.g. example.com")
    domain = _RECORD["host"](payload["domain"])
    if payload["domain"].strip().lower().rstrip(".") != domain:
        # The hearth lets this call reach the host the domain field names, exactly that one.
        raise ValueError("send domain as the bare host, e.g. " + domain)
    seed = globals().get("CALL_NONCE") or ""
    if len(seed) != 64:
        raise ValueError("this hearth gives handlers no call nonce, so no fresh proof can be asked for")
    found = _RECORD["handle"]({"domain": domain})
    out = {"domain": domain, "spec": SPEC, "record": found}
    if not found.get("valid"):
        # 1004: neither resolver answered (or the hearth's egress budget refused them). That says
        # nothing about the record, so it is not reported as a missing one.
        verdict = "lookup_failed" if found.get("code") == 1004 else "no_valid_record"
        out.update(verdict=verdict, code=found.get("code"), error=found.get("error"))
        return out
    record = found["record"]
    uri, proto = record["uri"], record["proto"]
    out["endpoint"] = {"uri": uri, "proto": proto, "auth": record.get("auth")}
    if record["v"] != "aid2" or "pka" not in record:
        out.update(verdict="found_unproven",
                   detail="the record has no aid2 key (k): the endpoint cannot prove it belongs to "
                          "this domain; trust it as far as you trust DNS for " + domain)
        return out
    if not uri.startswith("https://"):
        out.update(verdict="found_unproven",
                   detail="the endpoint is not https (" + proto + "): the proof of Appendix B is an "
                          "HTTPS exchange")
        return out
    target = _host_of(uri)
    if target not in (domain, _named(payload, "endpoint")):
        out.update(verdict="endpoint_host_not_named", endpoint_host=target,
                   detail="the endpoint is on " + target + ", another host than " + domain + ". This "
                          "agent reaches only hosts the caller names: call again with endpoint=" + target)
        return out
    k = record["pka"]
    nonce = _base64.urlsafe_b64encode(bytes.fromhex(seed)).decode().rstrip("=")
    kid = _PROOF["keyid"](k)
    covered = '"@method";req "@target-uri";req "@authority";req "aid-domain";req "@status"'
    ask = ("aid-pka=(" + covered + ');created;expires;keyid="' + kid + '";alg="ed25519";nonce="'
           + nonce + '";tag="aid-pka-v2"')
    reply = fetch(uri, headers={"Accept-Signature": ask, "AID-Domain": domain,  # noqa: F821
                                "Cache-Control": "no-store"})
    exchange = {"k": k, "request": {"uri": uri, "nonce": nonce, "method": "GET", "aid_domain": domain},
                "response": {"status": reply.status, "headers": dict(reply.headers)},
                "now": int(_time.time()),
                "require_domain_binding": payload.get("require_domain_binding") is True}
    proof = _PROOF["handle"](exchange)
    if reply.error:
        proof["fetch_error"] = str(reply.error)[:200]
    out["proof"] = proof
    out["exchange"] = {"status": reply.status, "nonce": nonce, "aid_domain": domain,
                       "observed_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(exchange["now"]))}
    if proof["verified"]:
        out["verdict"] = "proven_bound" if proof["domain_bound"] else "proven_unbound"
    else:
        out["verdict"] = "proof_failed"
        out["code"] = 1003
        out["error"] = "ERR_SECURITY"
    return out
'''

HEAD = '''# ruff: noqa: E402, E501 — generated: the embedded sources come first
"""aid.discover@v1: AID discovery end to end — what a careful AID client would conclude.

Give `domain`. The agent reads _agent.<domain> through two DNS-over-HTTPS resolvers and applies
the record rules (the aid-record agent), then, when the record has a key, asks the endpoint for
a fresh proof bound to the domain and applies every verifier rule (the aid-proof agent) to the
answer it got. The challenge is the hearth's CALL_NONCE for this call: 32 random bytes the
endpoint could not have seen before.

The endpoint is reached only because the caller named it: `domain` (or, when the record points
to another host, `endpoint`) is one of this agent's egress input fields, so the hearth lets this
one call fetch that one host, over https, from public addresses only, without redirects.

Verdicts: proven_bound, proven_unbound, proof_failed, found_unproven, endpoint_host_not_named,
no_valid_record, lookup_failed (no resolver answered: retry). GENERATED by hestia-agents/scripts/build_aid_discover.py from the two agents'
sources, embedded below verbatim; edit those, not this file.
"""

'''


def build() -> str:
    record = (AGENTS / "aid-record" / "handler.py").read_text(encoding="utf-8")
    proof = (AGENTS / "aid-proof" / "handler.py").read_text(encoding="utf-8")
    return (HEAD + "RECORD_SOURCE = " + repr(record) + "\n\nPROOF_SOURCE = " + repr(proof) + "\n"
            + GLUE)


def main() -> int:
    target = AGENTS / "aid-discover" / "handler.py"
    target.write_text(build(), encoding="utf-8")
    print(f"{target.relative_to(ROOT)}: {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
