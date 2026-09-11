"""PRAXIS — a practice target for the self-healing loop, repairable in SOURCE.

Why this exists, and why the canary could not do this job.

The canary is a fixture that advertises a contract and knowingly breaks it, so the detection
pipeline can be seen to fire against a real finding. Its repair is a runtime toggle —
``POST /canary/fix`` flips a flag — because a source-level repair would make it conforming for
ever and it would never demonstrate a finding again. Repairing the canary destroys the canary.

That left the loop with nothing to prove itself on. Every real component passes its own
contract checks, which is the point of building them carefully, and the only findings in the
corpus were the canary's deliberate ones. So five autonomous repair attempts were measured
against a file whose opening paragraph says being broken is load-bearing — and the models that
declined were, on reflection, right to.

PRAXIS is the missing thing: a service with a GENUINE source-level defect, no consumers, and no
argument against being fixed.

  * Repairing it is the intended outcome. A patch that makes the signature verify is correct
    and should ship. Nothing here must stay broken.
  * Breaking it again is a deliberate operator act — a commit, a drill — not a toggle. Each
    exercise starts by reintroducing a defect on purpose and ends when the loop has removed it.
  * It serves no paying traffic and is not federated to the hub. It binds to loopback.

THE DEFECT, and why this one.

``manifest_canonical`` has eight independent implementations in this tree, and one of them has
already taken the whole federation down: the hub added a fifth field, the oracle copy did not
follow, and every oracle manifest failed verification. Signing over ``json.dumps`` instead of
the canonical form is not an invented bug — it is the exact mistake every autonomous attempt
reached for when it could not see the contract, and the one the ecosystem actually suffered.

The repair is to import the canonical form rather than to reimplement it. That is a real
interop lesson, and a loop that can learn it here has learned something that transfers.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from oracle_core.signing import Signer

app = FastAPI(title="PRAXIS practice target")

_KEY_PATH = os.environ.get("PRAXIS_KEY_PATH", "/data/praxis_signing_key")

_SIGNER: Signer | None = None


def _signer_instance() -> Signer:
    """The signer, built on first use rather than at import.

    ``Signer(...)`` creates the key and its parent directory, so building it at
    module scope made importing this module write to ``/data`` — impossible
    outside the container, which is why `tests/test_manifest_contract.py`
    (the tests the deploy gate runs against a candidate image) could not even be
    collected on a laptop. Reading the env var at first use also means
    ``PRAXIS_KEY_PATH`` set by a test or a wrapper is honoured, instead of being
    frozen at whatever it was when the import happened.
    """
    global _SIGNER
    if _SIGNER is None:
        _SIGNER = Signer(os.environ.get("PRAXIS_KEY_PATH", _KEY_PATH))
    return _SIGNER

TOOLS: list[dict[str, Any]] = [
    {
        "capability_id": "praxis.echo@v1",
        "description": "Echoes its input. Exists so the manifest has something to describe.",
        "price_per_call_usd": 0.0,
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
    }
]


def _manifest_body() -> dict[str, Any]:
    return {
        "capabilities_count": len(TOOLS),
        "generated_at": "2026-01-01T00:00:00Z",
        "protocol_version": "v2",
        "tools": TOOLS,
    }


def _signature_payload(manifest: dict[str, Any]) -> str:
    """Signs over the interop canonical form imported from oracle_core.signing.

    Every verifier in the ecosystem checks the signature against
    ``oracle_core.signing.Signer.manifest_canonical(manifest)`` — a pipe-delimited string of
    five named fields, not a JSON serialisation. Importing the canonical form keeps this in
    lockstep with the hub: a second copy is what drifts the day the first one gains a field,
    and that has happened here before.
    """
    return _signer_instance().manifest_canonical(manifest)


@app.get("/ai-market/v2/manifest")
async def manifest() -> dict[str, Any]:
    body = _manifest_body()
    signature = _signer_instance().sign_payload(_signature_payload(body))
    return {**body, "signature": signature}


@app.get("/.well-known/ai-market.json")
async def well_known() -> dict[str, Any]:
    return {
        "service": "praxis",
        "role": "practice target for the self-healing loop",
        "protocol_version": "v2",
        "capabilities_count": len(TOOLS),
        "provider_pubkey": _signer_instance().public_key_b64,
        "federated": False,
    }


@app.post("/ai-market/v2/invoke")
async def invoke(body: dict[str, Any] | None = None) -> dict[str, Any]:
    text = ((body or {}).get("input") or {}).get("text", "")
    return {"capability_id": "praxis.echo@v1", "output": {"text": text}, "price_usd": 0.0}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "praxis", "pubkey": _signer_instance().public_key_b64[:16]}


def main() -> None:
    import uvicorn

    # 0.0.0.0 inside the container so MOMUS can reach it over the docker network; keeping it
    # off the internet is the port mapping's job, not the bind's.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PRAXIS_PORT", "9460")))


if __name__ == "__main__":
    main()
