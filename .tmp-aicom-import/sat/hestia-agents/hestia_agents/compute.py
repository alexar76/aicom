"""Buyer side of HESTIA compute: call a function, check the receipt, cross-check.

A compute receipt from one hearth says "these exact function bytes, on your exact
input bytes, produced these output bytes here" — and, for the replicated SKU,
that two replicas on that host agreed. Both replicas ran under one operator and
the receipt is signed with that operator's key (`same_operator: true`), so it
cannot catch that operator lying. What can is running the SAME function on a
second, independently keyed hearth and comparing the output digests. That is
`cross_verify`: our own buyer client, and the rung docs/COMPUTE.md calls the
real one.

Nothing here trusts a hearth's word for anything it can recompute: the input
digest is recomputed from what was sent, the output digest from what came back,
and each receipt's signature is checked against the key that hearth publishes in
its own signed `.well-known`.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from hestia_agents.x402 import secret_refusal

RUN = "hestia.compute.run@v1"
VERIFY = "hestia.compute.verify@v1"
RECEIPT_KIND = "hestia.compute.receipt@v1"
# Opaque AWR method identifier (awr/SPEC.md 3.4): two verdicts are comparable
# only when they name the same method.
CROSS_METHOD = "urn:aimarket:method:hestia-cross-hearth-v1"


class ComputeClientError(RuntimeError):
    """The call, or the check, did not produce something a buyer can rely on."""


class PaymentRequired(ComputeClientError):
    def __init__(self, quote: dict[str, Any]) -> None:
        super().__init__(str(quote.get("detail") or "payment required"))
        self.quote = quote


def canonical_bytes(value: Any) -> bytes:
    """Byte-identical to the hearth's own (hestia.compute_worker.canonical_bytes);
    a test asserts the two agree, because a divergence reads as a forged input."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_canonical(document: dict[str, Any]) -> str:
    """Mirror of the hearth's (and the hub's) `object_canonical`: the whole object
    minus `signature`, sorted keys, compact."""
    body = {k: v for k, v in document.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def signature_valid(document: dict[str, Any], public_key_b64: str) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:  # pragma: no cover - extra not installed
        raise ComputeClientError(
            "checking a receipt needs cryptography: pip install 'aimarket-hestia-agents[compute]'"
        ) from None
    signature = document.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "ed25519":
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(
            base64.b64decode(str(signature.get("value") or ""), validate=True),
            object_canonical(document).encode(),
        )
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def _json(response: Any, what: str) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise ComputeClientError(f"{what}: HTTP {response.status_code}, not JSON") from None
    if not isinstance(body, dict):
        raise ComputeClientError(f"{what}: not a JSON object")
    return body


def hearth_key(client: Any, hearth: str) -> str:
    """The signing key a hearth publishes, from its own signed `.well-known`."""
    url = f"{hearth.rstrip('/')}/.well-known/ai-market.json"
    document = _json(client.get(url), url)
    key = str(document.get("signer_public_key") or "")
    if not key or not signature_valid(document, key):
        raise ComputeClientError(f"{hearth}: .well-known is not signed by the key it names")
    return key


def catalogue(client: Any, hearth: str, key: str) -> dict[str, Any]:
    url = f"{hearth.rstrip('/')}/v1/compute"
    document = _json(client.get(url), url)
    if not document.get("enabled"):
        raise ComputeClientError(f"{hearth} does not sell compute")
    if not signature_valid(document, key):
        raise ComputeClientError(f"{hearth}: the compute catalogue is not signed by its key")
    return document


def listed_digest(document: dict[str, Any], slug: str) -> str:
    """The function_sha256 a catalogue lists under `slug`; '' when it lists none."""
    for function in document.get("functions") or []:
        if function.get("slug") == slug:
            if not function.get("admissible"):
                raise ComputeClientError(
                    f"'{slug}' is listed but not admissible for compute: {function.get('refused')}"
                )
            return str(function.get("function_sha256") or "")
    raise ComputeClientError(f"no compute function '{slug}' is listed")


def _pinned_listing(client: Any, hearth: str, key: str, slug: str) -> str:
    """The digest a cross-check pins, from one hearth's signed catalogue."""
    digest = listed_digest(catalogue(client, hearth, key), slug)
    if not digest:
        raise ComputeClientError(
            f"{hearth} lists '{slug}' with no function_sha256: there are no bytes to pin, "
            "so the two hearths could run different functions and still agree"
        )
    return digest


@dataclass
class Checked:
    """One hearth's answer, and everything wrong with it (empty = nothing)."""

    hearth: str
    public_key: str
    output: Any
    receipt: dict[str, Any]
    problems: list[str] = field(default_factory=list)


def check_receipt(
    body: dict[str, Any],
    *,
    hearth: str,
    public_key: str,
    capability_id: str,
    function_sha256: str,
    input_sha256: str,
) -> Checked:
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    receipt = result.get("compute_receipt")
    if not isinstance(receipt, dict):
        raise ComputeClientError(f"{hearth}: the answer carries no compute receipt")
    output = result.get("output")
    checked = Checked(hearth=hearth, public_key=public_key, output=output, receipt=receipt)
    problems = checked.problems
    if not signature_valid(receipt, public_key):
        problems.append("the receipt is not signed by this hearth's published key")
    if receipt.get("kind") != RECEIPT_KIND:
        problems.append(f"unknown receipt kind {receipt.get('kind')!r}")
    if receipt.get("capability_id") != capability_id:
        problems.append("the receipt is for a different capability")
    if function_sha256 and receipt.get("function_sha256") != function_sha256:
        problems.append("the receipt names a different function than the one pinned")
    if receipt.get("input_sha256") != input_sha256:
        problems.append("the receipt names a different input than the one sent")
    try:
        output_sha = sha256_hex(canonical_bytes(output))
    except (TypeError, ValueError):
        output_sha = ""
    if receipt.get("output_sha256") != output_sha:
        problems.append("the output returned does not match the digest the receipt signs")
    return checked


def call(
    client: Any,
    hearth: str,
    slug: str,
    payload: dict[str, Any],
    *,
    capability_id: str = RUN,
    function_sha256: str = "",
    api_key: str = "",
    tx_hash: str = "",
    public_key: str = "",
    payment_secret: str = "",
) -> Checked:
    """One compute call, checked. Raises on anything that is not a signed answer.

    `payment_secret` goes with a direct payment (`tx_hash`) at a hearth's key-less
    door: the transaction and its nonce are public once mined, and the secret whose
    sha256 that nonce is shows the hearth that this caller is the one who paid.
    """
    if payment_secret and not tx_hash:
        raise ComputeClientError(
            "a payment secret redeems a payment: send it with the transaction (tx_hash)"
        )
    problem = secret_refusal(payment_secret) if payment_secret else ""
    if problem:
        # Refused here, before the key is even fetched: the hearth would refuse it
        # too, and say so only after the buyer had already paid under it.
        raise ComputeClientError(f"the payment secret {problem}")
    public_key = public_key or hearth_key(client, hearth)
    body: dict[str, Any] = {"slug": slug, "input": payload}
    if function_sha256:
        body["function_sha256"] = function_sha256
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if tx_hash:
        headers["X-Payment"] = tx_hash
    if payment_secret:
        headers["X-Payment-Secret"] = payment_secret
    response = client.post(
        f"{hearth.rstrip('/')}/ai-market/v2/invoke",
        json={"capability_id": capability_id, "input": body},
        headers=headers,
    )
    answer = _json(response, hearth)
    if response.status_code == 402:
        raise PaymentRequired(answer)
    if response.status_code != 200:
        raise ComputeClientError(
            f"{hearth}: HTTP {response.status_code} {str(answer.get('detail') or answer)[:300]}"
        )
    if answer.get("ok") is False:
        raise ComputeClientError(
            f"{hearth}: {answer.get('refuse_reason')}: {answer.get('detail') or ''}".strip()
        )
    return check_receipt(
        answer,
        hearth=hearth,
        public_key=public_key,
        capability_id=capability_id,
        function_sha256=function_sha256,
        input_sha256=sha256_hex(canonical_bytes(payload)),
    )


def payment_terms(
    client: Any, hearth: str, slug: str, *, capability_id: str = RUN
) -> dict[str, Any]:
    """The 402 a direct buyer pays against: the call, sent with no key and no payment.

    The hearth settles payment before it runs anything, so nothing runs for this
    and the input can be empty. Anything but a 402 is not a price: a hub-key-only
    hearth answers 401, and that is a refusal to sell directly, not "free".
    """
    response = client.post(
        f"{hearth.rstrip('/')}/ai-market/v2/invoke",
        json={"capability_id": capability_id, "input": {"slug": slug, "input": {}}},
    )
    answer = _json(response, hearth)
    if response.status_code != 402:
        raise ComputeClientError(
            f"{hearth}: HTTP {response.status_code} {str(answer.get('detail') or answer)[:300]}"
        )
    return answer


@dataclass
class CrossCheck:
    agree: bool
    function_sha256: str
    input_sha256: str
    first: Checked
    second: Checked
    notes: list[str] = field(default_factory=list)


def cross_verify(
    client: Any,
    hearths: tuple[str, str],
    slug: str,
    payload: dict[str, Any],
    *,
    capability_id: str = RUN,
    function_sha256: str = "",
    api_key: str = "",
) -> CrossCheck:
    """The same function, pinned by digest, on two independently keyed hearths.

    Refuses before paying either hearth when the check could not mean anything:
    the two publish the same key (one operator twice is no second opinion), or
    they do not list the same function bytes under that slug. A listing with no
    digest at all is refused too: two empty digests are equal, but an unpinned
    call lets each hearth run whatever it likes, and the receipts' function
    digests would then never be compared.
    """
    first_url, second_url = hearths
    first_key = hearth_key(client, first_url)
    second_key = hearth_key(client, second_url)
    if first_key == second_key:
        raise ComputeClientError(
            "both hearths sign with the same key: that is one operator twice, not a cross-check"
        )
    pin = function_sha256 or _pinned_listing(client, first_url, first_key, slug)
    second_pin = _pinned_listing(client, second_url, second_key, slug)
    if second_pin != pin:
        raise ComputeClientError(
            f"{second_url} lists '{slug}' as {second_pin}, not {pin}: a different function"
        )
    first = call(
        client, first_url, slug, payload, capability_id=capability_id,
        function_sha256=pin, api_key=api_key, public_key=first_key,
    )
    second = call(
        client, second_url, slug, payload, capability_id=capability_id,
        function_sha256=pin, api_key=api_key, public_key=second_key,
    )
    problems = [f"{c.hearth}: {p}" for c in (first, second) for p in c.problems]
    if problems:
        raise ComputeClientError("; ".join(problems))
    notes = []
    for fact in ("python_version", "platform"):
        if first.receipt.get(fact) != second.receipt.get(fact):
            notes.append(
                f"{fact} differs ({first.receipt.get(fact)} vs {second.receipt.get(fact)}): "
                "a disagreement may be the platform, not the operator"
            )
    return CrossCheck(
        agree=first.receipt.get("output_sha256") == second.receipt.get("output_sha256"),
        function_sha256=pin,
        input_sha256=str(first.receipt.get("input_sha256") or ""),
        first=first,
        second=second,
        notes=notes,
    )


def awr_verdict(check: CrossCheck, key: Any) -> dict[str, Any]:
    """An AWR/2 VerificationVerdict on the first hearth's receipt, by this buyer.

    `verifiedWork` digests the first receipt (RFC 8785, as AWR requires); the
    second receipt is the evidence, by digest. The issuer is the buyer's key, so
    it differs from both hearths. A compute receipt is not an AWR WorkReceipt, so
    AWR's L1/L2 profiles are not evaluated over it; what this document gives is a
    portable, independently signed judgement that names exactly which receipt it
    judged.
    """
    try:
        import awr
    except ImportError:
        raise ComputeClientError("an AWR verdict needs the awr package: pip install awr") from None
    subject = {
        "verifiedWork": {
            "id": str(check.first.receipt.get("id") or ""),
            "digestSRI": awr.canonical_sri(check.first.receipt),
        },
        "verdict": "pass" if check.agree else "fail",
        "score": "1" if check.agree else "0",
        "method": {
            "id": CROSS_METHOD,
            "name": "re-executed on an independently keyed HESTIA hearth; output digests compared",
        },
        "evidence": [
            {
                "kind": "hestia-compute-receipt",
                "digestSRI": awr.canonical_sri(check.second.receipt),
            }
        ],
    }
    return awr.issue_verification_verdict(subject, key)
