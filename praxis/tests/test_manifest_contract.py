"""PRAXIS's manifest signature must verify the way every peer checks it.

These tests FAIL while a drill is in progress. That is the point: they describe the state the
self-healing loop is expected to reach, and the deploy gate runs them against the candidate
image before anything is promoted. A patch that satisfies the probe but not these has not
fixed the contract, it has satisfied one reading of it.

The defect under exercise signs over `json.dumps` instead of
`oracle_core.signing.Signer.manifest_canonical`. It is not invented: `manifest_canonical` has
eight implementations in this tree, and a copy that fell behind the hub's fifth field once took
the entire federation down.
"""

from __future__ import annotations

import inspect
import json

from oracle_core.signing import Signer

from praxis.praxis import _manifest_body, _signature_payload


def _signer(tmp_path) -> Signer:
    return Signer(str(tmp_path / "praxis.key"))


def test_the_signature_verifies_the_way_a_peer_checks_it(tmp_path):
    signer = _signer(tmp_path)
    body = _manifest_body()
    manifest = {**body, "signature": signer.sign_payload(_signature_payload(body))}

    assert signer.verify_manifest_signature(manifest), (
        "the manifest signature does not verify against manifest_canonical — which is what "
        "every verifier in the ecosystem uses, so this manifest is rejected by every peer"
    )


def test_the_signed_payload_is_the_canonical_form_not_json(tmp_path):
    body = _manifest_body()
    payload = _signature_payload(body)

    assert not payload.lstrip().startswith("{"), "the signed payload is a JSON object"
    assert payload == Signer.manifest_canonical(Signer.__new__(Signer), body)


def test_the_canonical_form_is_called_not_merely_mentioned():
    """A second copy of an interop contract drifts the day the first one gains a field.

    Read from the FUNCTION, not the module: the module docstring names `manifest_canonical`
    while explaining the defect, so a module-wide search passes whether or not the code calls
    it — a test that agrees with itself. This looks at the one function that signs, with its
    own docstring stripped, so only executable lines are examined.
    """
    source = inspect.getsource(_signature_payload)
    body = source.split('"""')[-1] if '"""' in source else source
    code = "\n".join(
        line for line in body.splitlines() if line.strip() and not line.strip().startswith("#")
    )

    assert "manifest_canonical" in code, (
        "the signing function must CALL the canonical form, not merely mention it"
    )
    assert "json.dumps" not in code, "still signing over JSON"
    assert "|tools_hash:" not in code, (
        "the canonical string is spelled out here — import it, do not copy it"
    )


def test_a_correct_signature_binds_the_content_it_signs(tmp_path):
    """Signed CORRECTLY on purpose, so this tests binding rather than the defect.

    Signing the broken way also fails to verify, so a tamper test over the broken signature
    would pass for the wrong reason and keep passing after the repair without ever having
    checked anything.
    """
    signer = _signer(tmp_path)
    body = _manifest_body()
    manifest = {**body, "signature": signer.sign_manifest(body)}

    assert signer.verify_manifest_signature(manifest), "precondition: a correct signature verifies"

    tampered = json.loads(json.dumps(manifest))
    tampered["tools"][0]["price_per_call_usd"] = 999.0

    assert not signer.verify_manifest_signature(tampered), (
        "the signature does not bind the content it claims to sign"
    )
