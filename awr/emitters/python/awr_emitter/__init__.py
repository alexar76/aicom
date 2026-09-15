"""Emit an AWR/2 WorkReceipt in one call.

This package implements **none** of the AWR format. Canonicalization (SPEC.md §4), the
``eddsa-jcs-2022`` proof (§6) and ``did:key`` derivation (§5) all come from the ``awr``
reference implementation; everything here is the ten lines of glue between "I just ran a
model" and "I have a signed receipt". If this file ever grows a second implementation of
one of those, delete it — that is how the int-versus-float split that produced AWR/2 in the
first place happened.

WHAT GETS DIGESTED — the one decision an emitter cannot avoid
-------------------------------------------------------------
SPEC.md §3.3 requires ``inputDigest`` and ``outputDigest`` to be digests of *application
payload bytes* and deliberately leaves the serialization to the issuer. This emitter states
its choice rather than hiding it:

* ``emit_receipt(input_payload=..., output_payload=...)`` digests **exactly the bytes you
  pass**. ``bytes`` are used as-is; a ``str`` is encoded UTF-8 with no normalization and no
  trailing newline.
* If your payload is JSON and you want a third party to be able to *reproduce* the digest,
  pass it through :func:`jcs_payload` first. That canonicalizes with RFC 8785 so that two
  parties who serialize the same object differently still agree on the digest.

The distinction matters: a receipt whose digest nobody else can recompute is still a valid
receipt, but it can only ever be checked by whoever kept the original bytes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from awr import (
    SigningKey,
    canonical_sri,
    issue_work_receipt,
    load_key_file,
    sri_encode,
)

# Not in the reference's __all__, but part of its modules and the only correct way to get
# RFC 8785 bytes, a SHA-256 and an RFC 3339 timestamp without writing any of them here.
from awr.digest import canonical_bytes, sha256
from awr.documents import coerce_now, format_rfc3339_utc

__all__ = [
    "Payload",
    "digest_payload",
    "emit_receipt",
    "generate_key",
    "jcs_payload",
    "load_key",
    "EMPTY_PAYLOAD",
]

#: What you may hand the emitter as a payload.
Payload = Union[bytes, bytearray, str]

#: The digest of no bytes at all — SPEC.md §3.3 permits it for a receipt whose work
#: produced no output (``status`` other than ``succeeded``).
EMPTY_PAYLOAD = b""

_WORK_STATUSES = ("succeeded", "failed", "refused", "timeout", "partial")


def _as_bytes(payload: Payload) -> bytes:
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, str):
        # UTF-8, no normalization: §4.1 forbids normalizing document strings and a payload
        # digest that silently normalized would disagree with the bytes actually sent.
        return payload.encode("utf-8")
    raise TypeError(
        "payload must be bytes or str, got %s — if you have a JSON object, call "
        "jcs_payload(obj) so the digest is reproducible" % (type(payload).__name__,)
    )


def digest_payload(payload: Payload) -> str:
    """SRI digest of exactly these bytes (SPEC.md §3.2 encoding)."""
    return sri_encode(sha256(_as_bytes(payload)))


def jcs_payload(value: Any) -> bytes:
    """RFC 8785 canonical bytes of a JSON value, for a digest a third party can reproduce.

    Use this when the payload *is* JSON. It is the same canonicalization the document
    itself is signed under, so a consumer who has the object — however their JSON library
    ordered its keys — computes the same digest.
    """
    return canonical_bytes(value)


def generate_key() -> SigningKey:
    """A fresh Ed25519 signing key. Its ``did()`` is the issuer identity."""
    return SigningKey.generate()


def load_key(path: str) -> SigningKey:
    """Load a signing key previously written by the reference CLI's key file format."""
    with open(path, "r", encoding="utf-8") as handle:
        return load_key_file(handle.read())


def emit_receipt(
    *,
    key: SigningKey,
    model_id: str,
    input_payload: Payload,
    output_payload: Payload,
    status: str = "succeeded",
    completed_at: Optional[str] = None,
    started_at: Optional[str] = None,
    latency_ms: Optional[int] = None,
    capability: Optional[str] = None,
    price: Optional[Dict[str, str]] = None,
    nonce: Optional[str] = None,
    parents: Optional[list] = None,
    issuer_name: Optional[str] = None,
    document_id: Optional[str] = None,
    valid_from: Optional[str] = None,
    created: Optional[str] = None,
    now: Any = None,
) -> Dict[str, Any]:
    """Issue a signed L0 ``WorkReceipt``.

    Only ``key``, ``model_id`` and the two payloads are required; everything else is
    OPTIONAL in SPEC.md §3.3 and omitted when not given, so the smallest receipt this
    emitter produces carries no field the specification does not require.

    ``document_id``, ``valid_from`` and ``created`` exist so a caller can produce a
    deterministic document — the cross-language equivalence test depends on it. Leave them
    unset in production and the reference implementation fills them.
    """
    if status not in _WORK_STATUSES:
        raise ValueError(
            "status must be one of %s, got %r" % (", ".join(_WORK_STATUSES), status)
        )
    if latency_ms is not None and (not isinstance(latency_ms, int) or latency_ms < 0):
        raise ValueError("latencyMs must be a non-negative integer (§3.3)")

    # §3.3 REQUIRES work.completedAt, so the emitter always carries one: the caller's if
    # given, otherwise the same moment the document is stamped with. It is not optional and
    # the reference refuses to issue without it — better to fill it than to hand the caller
    # an IssuanceError for a field they had no reason to know about.
    moment = completed_at or created or valid_from or format_rfc3339_utc(coerce_now(now))

    work: Dict[str, Any] = {"modelId": model_id, "status": status}
    if capability is not None:
        work["capability"] = capability
    if started_at is not None:
        work["startedAt"] = started_at
    work["completedAt"] = moment
    if latency_ms is not None:
        work["latencyMs"] = latency_ms

    subject: Dict[str, Any] = {
        "work": work,
        "inputDigest": digest_payload(input_payload),
        "outputDigest": digest_payload(output_payload),
    }
    if parents:
        subject["parents"] = list(parents)
    if price is not None:
        # §4.3: money is a decimal STRING. Passing a float here would be rejected by the
        # reference at issue time, which is the correct place to find out.
        subject["price"] = dict(price)
    if nonce is not None:
        subject["nonce"] = nonce

    return issue_work_receipt(
        subject,
        key,
        document_id=document_id,
        valid_from=valid_from,
        created=created,
        issuer_name=issuer_name,
        now=now,
    )


def receipt_reference(document: Dict[str, Any]) -> Dict[str, str]:
    """A ``{id, digestSRI}`` reference to *document*, for use as a child's ``parents`` entry.

    The digest is over the **secured** document (§8.1), so a chain edge commits to the
    parent's exact bytes including its proof.
    """
    return {"id": document["id"], "digestSRI": canonical_sri(document)}
