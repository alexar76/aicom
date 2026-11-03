"""Ed25519 signing for hub manifests and receipts.

Fail-fast: refuses to initialize if cryptography is not installed
or if an existing key file is corrupted.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import sys
from pathlib import Path
from typing import Any

from ._signing_key_storage import (
    compromised_public_key, load_or_create_ed25519_keypair,
    load_or_create_mldsa_keypair,
)

# Post-quantum verification is a core dependency since 3.15.18 (`dilithium-py`). It used to be
# an extra, and a hub installed without it failed closed on every hybrid signature — which is
# every AIMarket hub's — and indexed none of them while its log said "Invalid manifest
# signature". Refusing what it cannot check is right; doing it SILENTLY is not. So a hub that
# still lacks the library (installed with --no-deps, or an old pin) says so at import, once per
# refusal kind in the log, in /health, and by name wherever a peer is refused for it.
try:
    from dilithium_py.ml_dsa import ML_DSA_65 as _MLDSA

    _PQ_LIB = True
except Exception:  # pragma: no cover - a broken install, reported loudly below
    _MLDSA = None
    _PQ_LIB = False

PQ_MISSING_ADVICE = (
    "this hub cannot check post-quantum (ML-DSA-65) signatures because dilithium-py is not "
    "installed. Every AIMarket hub signs hybrid, so their documents are refused (fail closed) "
    "and none of them is indexed. Install it: pip install 'aimarket-hub[pqc]' (or "
    "dilithium-py), then restart"
)
if not _PQ_LIB:  # pragma: no cover - depends on the install
    logging.getLogger(__name__).error("POST-QUANTUM VERIFIER MISSING: %s.", PQ_MISSING_ADVICE)

#: How many signatures this process refused because it could not evaluate their PQ half.
_pq_unverifiable_refusals = 0


def pqc_available() -> bool:
    """Whether this hub can evaluate an ML-DSA-65 signature."""
    return _PQ_LIB


def pq_unverifiable(sig: Any) -> bool:
    """True when `sig` carries a post-quantum signature this hub cannot evaluate.

    Callers use it to name the reason a document was refused: without it a missing library
    reads as "invalid signature" and the operator blames the peer.
    """
    return isinstance(sig, dict) and bool(sig.get("pq_value")) and not _PQ_LIB


SIGNATURE_OBJECT_SHAPE = '{"algorithm": "ed25519", "public_key": "<base64>", "value": "<base64>"}'

_JSON_TYPE_NAMES = {str: "a string", list: "an array", bool: "a boolean", int: "a number",
                    float: "a number", type(None): "null"}


def signature_shape_problem(sig: Any) -> str:
    """Why `sig` is not a usable signature OBJECT (spec §7.3.1), or "" when it is one.

    Both strangers who have ever knocked on modelmarket.dev from their own implementation
    (agent-exec.448c.org on 2026-10-08, mach402.dev on 2026-10-19) published the base64
    signature as a bare string. Every verifier then did `sig.get("value")` on a `str`, and the
    assay crashed instead of saying what was wrong: their dossiers froze on an older failure
    they had already fixed, and `aimarket doctor` printed a traceback. A wrong shape is the
    peer's mistake to fix, so it has to come back as a sentence that says how.
    """
    if isinstance(sig, dict):
        value = sig.get("value")
        if not isinstance(value, str) or not value.strip():
            return ('the signature object has no "value" string: put the base64 Ed25519 signature '
                    'there (spec §7.3.1)')
        return ""
    kind = _JSON_TYPE_NAMES.get(type(sig), "not an object")
    return (f"signature is {kind}, not an object (spec §7.3.1): publish "
            f"{SIGNATURE_OBJECT_SHAPE}, with the base64 Ed25519 signature in value")


def pq_unverifiable_refusals() -> int:
    """Signatures refused so far because the PQ half could not be evaluated (for /health)."""
    return _pq_unverifiable_refusals


def _note_pq_unverifiable() -> None:
    global _pq_unverifiable_refusals
    _pq_unverifiable_refusals += 1
    if _pq_unverifiable_refusals == 1 or _pq_unverifiable_refusals % 100 == 0:
        logging.getLogger(__name__).error(
            "Refused a post-quantum-signed document (%d so far): %s.",
            _pq_unverifiable_refusals, PQ_MISSING_ADVICE,
        )


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def pqc_signing_enabled() -> bool:
    """The `AIMARKET_PQC` switch alone (off when unset). The hub's own identity uses
    `hub_signs_hybrid`, which also looks at the keys it already has; other signers (plugins,
    providers, examples) keep this plain switch."""
    return _truthy(os.environ.get("AIMARKET_PQC"))


def pqc_signing_setting() -> bool | None:
    """`AIMARKET_PQC` as the operator set it, or None when it is not set at all."""
    raw = os.environ.get("AIMARKET_PQC")
    if raw is None or not raw.strip():
        return None
    return _truthy(raw)


def hub_signs_hybrid(key_path: str | Path) -> bool:
    """Whether the HUB signs hybrid, decided before its keys are loaded or made.

    `AIMARKET_PQC` set: exactly that. Unset — since 3.15.20 — the keys decide:
      * a hub that already holds an ML-DSA-65 key keeps signing with it. Peers pinned it, and
        the ratchet refuses a hub that stops; losing the flag on a redeploy (it happened to
        one of ours) must not be enough to drop out of the federation;
      * a NEW hub (no Ed25519 key yet) signs hybrid, as every AIMarket hub does, so every hub
        can index it — including the ones that require a post-quantum signature;
      * a hub that has signed Ed25519 only so far keeps doing so: nothing changes under it.
    A new hub without the verifier library signs classically (that hub is already loud about
    the missing library) rather than refusing to start.
    """
    explicit = pqc_signing_setting()
    if explicit is not None:
        return explicit
    key = Path(key_path)
    if Path(f"{key}_mldsa").exists():
        return True
    return (not key.exists()) and _PQ_LIB


def _pqc_required() -> bool:
    return _truthy(os.environ.get("AIMARKET_PQC_REQUIRE"))


def pqc_required() -> bool:
    """Whether this hub refuses a document carrying no PQ signature. Off by default."""
    return _pqc_required()


class PQCMisconfigured(RuntimeError):
    """PQ signatures are required but this hub cannot check one. Loud, not a silent reject."""

logger = logging.getLogger(__name__)

# ── Canonical-format versions ────────────────────────────────────────────────
#
# v1 is the original field set. v2 additionally binds the fields a Pay-on-Verified
# money outcome is *justified* by — the delivery verdict, the audit score, the bar
# applied, and the settlement's own resolution — which v1 left outside the
# signature: a stored or forwarded envelope's stated REASONS were unauthenticated
# while its verdict was, so a relay could rewrite "why" without breaking the
# signature and a dispute would be argued from tampered evidence.
#
# The version travels in the signature block AND inside the v2 canonical itself
# (`|v:2|`), so it is bound by the signature rather than merely asserted next to it, and
# it is ABSENT for v1 — every byte a previously-signed receipt/envelope carries is
# unchanged and still verifies.
#
# Receipts cannot simply be flipped to v2 everywhere: `receipt_canonical` v1 is a
# cross-package interop shape (oracle_core, platon and the protocol test vectors all
# mirror the 7-field v1 string), so a plain invoke receipt MUST stay v1 or external
# verifiers reject it. But leaving the choice to each call site is what left the hub
# split-brained: `verified_settlement` signed its rejection receipt at v2 while
# `safety_gate.build_rejection_receipt` and the api's plugin-block receipt signed
# byte-identical evidence at v1, where every v1 field on a rejection is a constant and
# the signature therefore authenticated nothing about WHY the money came back.
#
# The version is therefore no longer a per-call-site default: `sign_receipt` DERIVES it
# from the receipt's own content (`resolve_receipt_version`). A receipt that carries any
# field only v2 binds is signed at v2; an interop invoke receipt, which carries none of
# them, keeps the byte-stable v1 canonical. A call site can still pin a version
# explicitly, but it can no longer under-sign its evidence by omission.
VERIFICATION_SIG_VERSION = 2
# A verdict envelope that carries an `appeal` object (Pay-on-Verified with an appeal
# window: its deadline, who appealed, the bond, the second verifier, its verdict and
# whether it overturned the first) is signed at v3, which binds that object too. Like
# receipts, the version is derived from content (`resolve_verification_version`): an
# envelope with no appeal keeps the v2 canonical byte-for-byte, so every envelope signed
# before appeals existed — and every one a hub with the window at 0 still signs — is
# unchanged.
VERIFICATION_APPEAL_SIG_VERSION = 3
RECEIPT_SIG_VERSION = 2
# The version an unversioned signature block means. Absent == 1 for back-compat.
LEGACY_SIG_VERSION = 1

# Fields each v2 canonical binds through a digest, ON TOP of its v1 string. A digest
# rather than more `|`-joined text: several of these are verifier- or peer-authored
# strings, and a raw join would let a `|` inside one forge the boundary of the next.
_VERIFICATION_V2_FIELDS = (
    "status", "performed", "verified", "settled", "audit_score", "threshold",
    "delivery_fulfils", "delivery_reasons", "reason", "verifier", "mode",
)
# v3 = v2 + the appeal object. Unsigned, "who appealed" and "the second court overturned
# it" would be exactly the claims a dispute about an appeal is argued from.
_VERIFICATION_V3_FIELDS = _VERIFICATION_V2_FIELDS + ("appeal",)
_RECEIPT_V2_FIELDS = (
    "type", "channel_id", "category", "plugin", "reason", "verify_score",
    "delivery_reasons", "trace_id", "refunded",
)


def _fields_digest(obj: dict[str, Any], names: tuple[str, ...]) -> str:
    """Deterministic digest over a named subset of `obj`.

    Missing keys are bound as `null` on purpose — dropping a field must change the
    digest, or removing `delivery_reasons` from a stored envelope would go unnoticed.
    """
    import hashlib
    import json

    payload = {name: obj.get(name) for name in names}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), default=str).encode()
    ).hexdigest()


def resolve_receipt_version(receipt: dict[str, Any]) -> int:
    """The canonical version a receipt MUST be signed at, derived from its content.

    v2 iff the receipt carries at least one field that only v2 binds. This is what makes
    the receipt/verification split readable instead of accidental: the interop invoke
    receipt (nonce/product/capability/price/timestamp/success/latency) carries none of
    them and stays on the byte-stable v1 string that oracle_core, platon and the protocol
    vectors mirror, while any receipt that states a REASON, a score, a channel or a refund
    — i.e. every rejection receipt — is signed over that evidence.
    """
    return 2 if any(name in receipt for name in _RECEIPT_V2_FIELDS) else 1


def resolve_verification_version(verification: dict[str, Any]) -> int:
    """The canonical version a verdict envelope MUST be signed at: v3 iff it carries an
    `appeal` object, else v2. Derived, like receipts, so no call site can sign an appeal
    out of the signature by forgetting to ask for v3."""
    if "appeal" in verification:
        return VERIFICATION_APPEAL_SIG_VERSION
    return VERIFICATION_SIG_VERSION


def _signed_version(artefact: dict[str, Any]) -> int:
    """The canonical version an artefact's OWN signature block names.

    Returns 0 when there is no usable signature or the version is unreadable, so callers
    fail closed instead of silently assuming v1 for a malformed block.
    """
    sig = artefact.get("signature")
    if not isinstance(sig, dict) or not sig.get("value"):
        return 0
    raw = sig.get("version", LEGACY_SIG_VERSION)
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return 0
    return version if version >= 1 else 0


def receipt_signature_version(receipt: dict[str, Any]) -> int:
    """Version of the canonical this receipt was signed under; 0 if not determinable.

    Discoverable from the artefact, not inferred by the reader: for v2 the version is
    inside the signed bytes, and for v1 the absence of the field IS the v1 marker.
    """
    return _signed_version(receipt)


def unsigned_receipt_fields(receipt: dict[str, Any]) -> tuple[str, ...]:
    """v2-only fields this receipt carries that its OWN signature does not cover.

    Empty for anything signed at the version its content requires. Non-empty means the
    artefact is legacy (signed before v2 existed, or by a peer still on v1): the values
    are present but unauthenticated, which a dispute has to be able to see rather than
    guess. Also non-empty for an unsigned/unreadable block — everything is uncovered then.
    """
    present = tuple(name for name in _RECEIPT_V2_FIELDS if name in receipt)
    if not present:
        return ()
    return () if _signed_version(receipt) >= 2 else present


def _ensure_keypair(path: Path) -> tuple[bytes, bytes]:
    existed = path.exists() or path.is_symlink()
    pair = load_or_create_ed25519_keypair(path)
    if not existed:
        logger.warning(
            "NEW Ed25519 signing key generated at %s. Back it up now. "
            "An existing peer identity requires explicit trust reconciliation.", path,
        )
    return pair


def _load_or_make_pq(path: Path) -> tuple[bytes, bytes]:
    existed = path.exists() or path.is_symlink()
    pair = load_or_create_mldsa_keypair(path, _MLDSA)
    if not existed:
        logger.warning(
            "NEW post-quantum (ML-DSA-65) signing key generated at %s. Back it up together "
            "with the Ed25519 key beside it. Peers pin it; an existing identity requires "
            "explicit trust reconciliation.", path,
        )
    return pair


class Signer:
    """Ed25519 signer for a hub instance."""

    def __init__(self, key_path: str | Path = "data/hub_signing_key",
                 pqc: bool | None = None):
        self.key_path = Path(key_path)
        self._seed, self._pub_bytes = _ensure_keypair(self.key_path)
        self._public_key_b64 = base64.b64encode(self._pub_bytes).decode()

        # Phase 2. The hub could VERIFY a post-quantum signature and not produce one, which meant
        # the busiest authenticated channel in the ecosystem — a hub's signed `.well-known` and
        # manifest — could never carry the PQ layer, and no peer could ever pin a PQ key for it.
        # Off by default: a signer that gets ahead of the verifiers de-federates itself, because
        # verification fails CLOSED on a `pq_value` it cannot evaluate.
        if pqc is None:
            pqc = pqc_signing_enabled()
        self._pq: tuple[bytes, bytes] | None = None
        if pqc:
            # Loud, not a silent downgrade. `and _PQ_LIB` here meant a hub with AIMARKET_PQC=1
            # and no dilithium-py signed classically and said nothing about it — the same
            # quiet fallback that kept three of our own nodes on Ed25519 through all of phase
            # 2 while every dashboard showed them healthy. `verify_hybrid` has always raised
            # in the mirror-image case; signing now matches it.
            if not _PQ_LIB:
                raise PQCMisconfigured(
                    "AIMARKET_PQC is on but dilithium-py is missing — "
                    "install aimarket-hub[pqc] on this hub")
            self._pq = _load_or_make_pq(Path(f"{self.key_path}_mldsa"))

    @property
    def pq_public_key_b64(self) -> str:
        """This hub's ML-DSA-65 public key, or "" when PQ signing is off."""
        return base64.b64encode(self._pq[0]).decode() if self._pq else ""

    def _pq_fields(self, canonical: str) -> dict[str, str]:
        """The additive `pq_*` block for a signature object. Empty when PQ signing is off."""
        if self._pq is None:
            return {}
        pk, sk = self._pq
        return {
            "pq_algorithm": "ml-dsa-65",
            "pq_public_key": base64.b64encode(pk).decode(),
            "pq_value": base64.b64encode(_MLDSA.sign(sk, canonical.encode())).decode(),
        }

    @property
    def public_key_b64(self) -> str:
        return self._public_key_b64

    def sign(self, payload: bytes) -> bytes:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            return Ed25519PrivateKey.from_private_bytes(self._seed).sign(payload)
        except ImportError as exc:
            raise ImportError(
                "cryptography>=44 is required for Ed25519 signing. "
                "Install it: pip install cryptography>=44"
            ) from exc

    def sign_canonical(self, canonical: str) -> str:
        sig = self.sign(canonical.encode())
        return base64.b64encode(sig).decode()

    @staticmethod
    def verify_hybrid(public_key_b64: str, sig: dict[str, Any], canonical: str,
                      *, require_pq: bool | None = None,
                      pq_public_key_b64: str | None = None) -> bool:
        """Verify a signature OBJECT, checking the post-quantum layer when it is present.

        The hub previously read only `signature.value` and ignored `pq_*` entirely, which meant a
        peer could publish an ML-DSA-65 signature and the hub would never look at it — the PQ
        fields were decoration on the busiest verification path in the ecosystem.

        Policy, matching `oracle_core.signing`:
          1. Ed25519 MUST verify against the PINNED key. Always, and first.
          2. If PQ is required and there is no `pq_value` -> reject. Without this rule an
             adversary who breaks Ed25519 just deletes the pq_* keys and is accepted.
          3. If `pq_value` is present, ML-DSA-65 MUST verify too.

        `require_pq` defaults to `AIMARKET_PQC_REQUIRE`. It is OFF by default and must stay off
        until every FEDERATED PEER signs hybrid — peers are third parties this hub does not
        control, so requiring PQ globally would de-federate everyone who has not migrated.

        `pq_public_key_b64` PINS the peer's PQ identity. Omitted, the PQ key is taken from the
        signature object, which makes the PQ layer useless against the adversary it exists for:
        one who can forge Ed25519 forges it against the pinned classical key and attaches an
        ML-DSA keypair of their own. The hub does not yet carry a per-peer PQ key — `PeerRecord`
        stores `public_key` only — so requiring PQ here without adding that field first would buy
        presence, not attribution. Recording each peer's PQ key on first sight, while classical
        signatures still authenticate it, is the prerequisite for phase 3.
        """
        must_pq = _pqc_required() if require_pq is None else bool(require_pq)
        if must_pq and not _PQ_LIB:
            raise PQCMisconfigured(
                "AIMARKET_PQC_REQUIRE is on but dilithium-py is missing — "
                "install aimarket-hub[pqc] on this hub")
        if signature_shape_problem(sig):
            return False        # a bare string, or an object without a value, is not a signature
        if not Signer.verify(public_key_b64, sig.get("value", ""), canonical):
            return False
        pq_value = sig.get("pq_value")
        if not pq_value:
            return not must_pq
        if not _PQ_LIB:
            _note_pq_unverifiable()
            return False        # fail-closed on a PQ signature this hub cannot evaluate
        presented = sig.get("pq_public_key", "")
        if pq_public_key_b64 and presented != pq_public_key_b64:
            return False        # pinned PQ identity: a substituted key is a forgery attempt
        try:
            pk = decode_b64(presented)
            raw = decode_b64(pq_value)
            if pk is None or raw is None:
                return False
            return bool(_MLDSA.verify(pk, canonical.encode(), raw))
        except Exception:
            return False

    @staticmethod
    def verify(public_key_b64: str, signature_b64: str, canonical: str) -> bool:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as exc:
            raise ImportError(
                "cryptography>=44 is required for Ed25519 verification. "
                "Install it: pip install cryptography>=44"
            ) from exc

        try:
            pk_bytes = decode_b64(public_key_b64)
            sig_bytes = decode_b64(signature_b64)
            if pk_bytes is None or sig_bytes is None:
                return False
            # Strict verification: a small-order key or R makes a signature valid for any message.
            if compromised_public_key(pk_bytes) or has_small_order(pk_bytes) or has_small_order(sig_bytes[:32]):
                return False
            Ed25519PublicKey.from_public_bytes(pk_bytes).verify(sig_bytes, canonical.encode())
            return True
        except (InvalidSignature, ValueError):
            return False

    def manifest_canonical(self, manifest: dict[str, Any]) -> str:
        """Canonical string signed for a manifest. Carries `generated_at` (freshness)."""
        import hashlib
        import json
        tools = manifest.get("tools", [])
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        # by_hub carries per-peer trust_score + routing metadata; it MUST be covered by the
        # signature or a relay could tamper with peer trust/routing under a valid signature.
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

    def sign_manifest(self, manifest: dict[str, Any]) -> dict[str, str]:
        # Sign over structural integrity fields + content digest.
        # The manifest signature now covers the full tools[] array via a hash
        # so that any price/trust/agent modification invalidates the signature.
        canonical = self.manifest_canonical(manifest)
        signed = {
            "algorithm": "ed25519",
            "public_key": self.public_key_b64,
            "value": self.sign_canonical(canonical),
        }
        signed.update(self._pq_fields(canonical))
        return signed

    @staticmethod
    def object_canonical(obj: dict[str, Any]) -> str:
        """Deterministic canonical over an ENTIRE object (minus any existing `signature`).

        Static on purpose: canonicalizing is not a privileged act, and the update advisor that
        verifies a hub's `.well-known` holds no signing key at all. Instance calls
        (`signer.object_canonical(...)`) keep working unchanged.

        For documents where every field must be tamper-evident — e.g. `/.well-known/ai-market.json`
        and `/ai-market/v2/prices`, whose contents (mcp_servers, prices, federation, peers) are not
        covered by the structural manifest canonical.
        """
        import json

        body = {k: v for k, v in obj.items() if k != "signature"}
        return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def verify_object_signature(obj: dict[str, Any], public_key_b64: str, *,
                                require_pq: bool | None = None,
                                pq_public_key_b64: str | None = None) -> bool:
        """Verify a WHOLE-document signature (`sign_object`) against a pinned public key.

        `/.well-known/ai-market.json` and `/ai-market/v2/prices` are signed this way rather than
        with `manifest_canonical`, which covers structural fields only (see `api.py`, where the
        well-known switched to `sign_object` precisely so `mcp_servers`, `peers` and the price
        rows became tamper-evident). A verifier that reaches for `verify_manifest_signature` on
        those documents gets a confident `False`, which reads exactly like a bad signature.

        Keyless and static: the caller needs the PEER's public key, never one of its own. Pass the
        key from a PIN — the document advertises `signer_public_key` equal to
        `signature.public_key`, so a key read out of the response verifies it against itself.
        """
        if not public_key_b64:
            return False        # fail closed: no pin means no trust chain, as on manifests
        sig = obj.get("signature") or {}
        if not sig:
            return False
        return Signer.verify_hybrid(public_key_b64, sig, Signer.object_canonical(obj),
                                    require_pq=require_pq,
                                    pq_public_key_b64=pq_public_key_b64)

    def sign_object(self, obj: dict[str, Any]) -> dict[str, str]:
        """Sign the full object canonical (see object_canonical), hybrid when PQ signing is on."""
        canonical = self.object_canonical(obj)
        signed = {
            "algorithm": "ed25519",
            "public_key": self.public_key_b64,
            "value": self.sign_canonical(canonical),
        }
        # Additive: both signatures cover the SAME canonical string, so a verifier that has never
        # heard of ML-DSA reads `algorithm` and `value` and ignores the rest.
        signed.update(self._pq_fields(canonical))
        return signed

    def receipt_canonical(self, receipt: dict[str, Any], version: int = 1) -> str:
        """Canonical string signed for a receipt. Carries `nonce` + `timestamp` (replay).

        v1 (the default HERE, because this method is also the interop vector generator)
        is the cross-package interop shape mirrored by oracle_core, platon and the
        protocol test vectors — do not change it. Signing goes through `sign_receipt`,
        which picks the version from the receipt's content. v2 additionally binds
        the fields a REJECTION receipt is argued from (`reason`, `verify_score`,
        `delivery_reasons`, `trace_id`, `refunded`, `channel_id`): on a rejection the
        v1 fields are all constant (price 0, success 0, latency 0), so v1 signed
        essentially nothing about why the buyer's money came back.
        """
        base = (
            f"nonce:{receipt.get('nonce','')}"
            f"|product_id:{receipt.get('product_id','')}"
            f"|capability_id:{receipt.get('capability_id','')}"
            f"|price_usd:{receipt.get('price_usd',0)}"
            f"|timestamp:{receipt.get('timestamp','')}"
            f"|success:{1 if receipt.get('success') else 0}"
            f"|latency_ms:{receipt.get('latency_ms',0)}"
        )
        if version < 2:
            return base
        return f"{base}|v:2|fields:{_fields_digest(receipt, _RECEIPT_V2_FIELDS)}"

    def receipt_canonical_candidates(
        self, receipt: dict[str, Any], version: int = 1
    ) -> tuple[str, ...]:
        """Canonicals a cross-language JSON round-trip may have meant.

        Receipt v1 predates a typed canonical-number rule and interpolates
        ``price_usd`` directly. Python therefore signed zero as ``0.0`` while a
        browser parses and re-serializes that exact JSON value as ``0``. The receipt
        was still byte-for-byte genuine, but sending it back to a verifier changed
        the Python type and made its signature unverifiable. Keep the signing
        canonical and every external test vector unchanged; during verification only,
        also try the equivalent integral spelling. This is deliberately narrow:
        arbitrary numeric coercion would create ambiguous signed values.
        """
        primary = self.receipt_canonical(receipt, version)
        value = receipt.get("price_usd", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return (primary,)
        try:
            integral = float(value).is_integer()
        except (OverflowError, ValueError):
            integral = False
        if not integral:
            return (primary,)
        alternate = dict(receipt)
        alternate["price_usd"] = float(value) if isinstance(value, int) else int(value)
        second = self.receipt_canonical(alternate, version)
        return (primary,) if second == primary else (primary, second)

    def sign_receipt(
        self, receipt: dict[str, Any], version: int | None = None
    ) -> dict[str, Any]:
        """Sign a receipt at the canonical version its CONTENT requires.

        `version=None` (the default, and what every call site should use) resolves via
        `resolve_receipt_version`: a receipt whose evidence fields only v2 binds is signed
        at v2, an interop invoke receipt at the byte-stable v1. Pass a version only to pin
        one deliberately — pinning 1 on a receipt that carries v2 evidence signs that
        evidence out of the signature, which is exactly the bug this default removes.
        """
        resolved = resolve_receipt_version(receipt) if version is None else int(version)
        canonical = self.receipt_canonical(receipt, resolved)
        sig: dict[str, Any] = {
            "algorithm": "ed25519",
            "value": self.sign_canonical(canonical),
        }
        if resolved > 1:
            # Absent == 1, so a v1 block is byte-identical to what it always was.
            sig["version"] = resolved
        # A receipt is the buyer's durable proof that a capability ran and money was
        # charged (or returned). Leaving it classic-only while manifests were hybrid
        # protected the catalogue but not the economic outcome. Both signatures cover
        # exactly the same versioned canonical; old clients continue to read `value`.
        sig.update(self._pq_fields(canonical))
        return sig

    def verify_receipt_signature(
        self, receipt: dict[str, Any], known_public_key: str = "",
        known_pq_public_key: str = "",
    ) -> bool:
        """Verify a receipt against the canonical version its OWN signature names.

        Back-compat is the point: a receipt signed before v2 existed carries no
        `version` and must keep verifying against the v1 canonical forever.
        Defaults to this hub's key because these receipts are hub-self-signed; a peer's
        receipt must pass the peer's pinned key explicitly.
        """
        version = _signed_version(receipt)
        if version == 0:
            # No usable signature, or an unreadable version — fail closed.
            return False
        classical_key = known_public_key or self.public_key_b64
        # Self-signed receipts are pinned to BOTH of this hub's identities. Without
        # this pin, somebody who could forge Ed25519 could attach their own ML-DSA key
        # and still pass a syntactically hybrid verification. A caller checking a peer
        # can pass that peer's independently stored PQ key explicitly.
        pq_key = known_pq_public_key or (
            self.pq_public_key_b64
            if same_key(classical_key, self.public_key_b64) else ""
        )
        return any(
            self.verify_hybrid(
                classical_key,
                receipt["signature"],
                canonical,
                pq_public_key_b64=pq_key or None,
            )
            for canonical in self.receipt_canonical_candidates(receipt, version)
        )

    def verification_canonical(
        self, verification: dict[str, Any], version: int = VERIFICATION_SIG_VERSION
    ) -> str:
        """Canonical string signed for a Pay-on-Verified verdict envelope.

        Separate from receipt_canonical on purpose: the invoke receipt is signed
        (and possibly already delivered to the buyer) BEFORE the verdict exists,
        so the verdict gets its own signature instead of mutating the receipt
        canonical. Carries `nonce` (the receipt nonce) + `timestamp` (replay).

        v2 (the default for new signatures) also binds the rest of the money
        outcome: `delivery_fulfils`/`delivery_reasons` (what the verdict actually
        said about the delivery), `audit_score` and `threshold` (the numbers it was
        decided from), and `status`/`verified`/`settled`/`reason` (what the hub then
        did with the money). Under v1 all of those travelled unauthenticated next to
        an authenticated `verdict`, so a stored envelope could be re-described
        without invalidating its signature. v1 remains available for verifying
        envelopes signed before the change.

        v3 adds the `appeal` object (see VERIFICATION_APPEAL_SIG_VERSION) to the digest.
        """
        base = (
            f"nonce:{verification.get('nonce','')}"
            f"|capability_id:{verification.get('capability_id','')}"
            f"|verdict:{verification.get('verdict','')}"
            f"|verify_score:{verification.get('verify_score',0)}"
            f"|trace_id:{verification.get('trace_id','')}"
            f"|timestamp:{verification.get('timestamp','')}"
        )
        if version < 2:
            return base
        if version == 2:
            return f"{base}|v:2|fields:{_fields_digest(verification, _VERIFICATION_V2_FIELDS)}"
        return (
            f"{base}|v:{VERIFICATION_APPEAL_SIG_VERSION}"
            f"|fields:{_fields_digest(verification, _VERIFICATION_V3_FIELDS)}"
        )

    def sign_verification(
        self, verification: dict[str, Any], version: int | None = None
    ) -> dict[str, Any]:
        """Sign a verdict envelope at the version its CONTENT requires (`version=None`,
        what every call site should pass): v3 when it carries an `appeal`, else v2. Pin a
        version only deliberately — pinning 2 on an appeal envelope signs the appeal out."""
        if version is None:
            version = resolve_verification_version(verification)
        if version > VERIFICATION_APPEAL_SIG_VERSION:
            raise ValueError(f"unknown verification signature version {version}")
        canonical = self.verification_canonical(verification, version)
        sig: dict[str, Any] = {
            "algorithm": "ed25519",
            "value": self.sign_canonical(canonical),
        }
        if version > 1:
            sig["version"] = version
        # The verdict controls settlement, so it needs the same hybrid protection as
        # the receipt it resolves. This is additive and keeps the v1/v2 canonical bytes.
        sig.update(self._pq_fields(canonical))
        return sig

    def verify_verification_signature(
        self, verification: dict[str, Any], known_public_key: str = "",
        known_pq_public_key: str = "",
    ) -> bool:
        """Verify a verdict envelope against the canonical version it names.

        The envelope's `signature` block is excluded from the canonical, so passing
        the envelope as stored (signature included) is correct.
        """
        version = _signed_version(verification)
        if version == 0 or version > VERIFICATION_APPEAL_SIG_VERSION:
            # No usable signature, or a version this code cannot canonicalise — a
            # "future" version must never be read as the nearest one it knows.
            return False
        canonical = self.verification_canonical(verification, version)
        classical_key = known_public_key or self.public_key_b64
        pq_key = known_pq_public_key or (
            self.pq_public_key_b64
            if same_key(classical_key, self.public_key_b64) else ""
        )
        return self.verify_hybrid(
            classical_key,
            verification["signature"],
            canonical,
            pq_public_key_b64=pq_key or None,
        )

    def verify_manifest_signature(
        self, manifest: dict[str, Any], known_public_key: str = "",
        pinned_pq_public_key: str = ""
    ) -> bool:
        """Verify manifest signature against a KNOWN public key (pinned).

        Args:
            manifest: The manifest dict containing a 'signature' block.
            known_public_key: Peer's public key from a trusted source (DB pinning).
                              MUST be non-empty — empty key returns False.
            pinned_pq_public_key: The peer's ML-DSA key, likewise from a trusted source. Empty
                              means "not pinned yet", and then a present PQ signature is checked
                              against the key the document itself carries — which authenticates
                              the document but NOT the peer. See `verify_hybrid`.

        Security: The public key MUST come from a trusted source (peer DB record),
        NOT from the signature block itself — otherwise signatures are self-verifying.
        First-contact callers should reject the peer until an operator approves it.
        """
        if not known_public_key:
            # Fail-closed: no pinned key = cannot verify trust chain.
            # Previously fell back to sig.public_key which is self-verifying.
            return False
        sig = manifest.get("signature") or {}
        if not sig:
            return False
        # Use the single canonical (covers tools_hash AND by_hub_hash) — do NOT duplicate it
        # here, or sign/verify can silently diverge and miss tampering.
        canonical = self.manifest_canonical(manifest)
        # Hybrid: a peer that signs with ML-DSA-65 now has that signature CHECKED, not ignored.
        return self.verify_hybrid(known_public_key, sig, canonical,
                                  pq_public_key_b64=pinned_pq_public_key or None)



_URLSAFE_TO_STANDARD = str.maketrans("-_", "+/")


# Ed25519 points of small order (orders 1, 2, 4, 8), canonical and non-canonical encodings, with
# the sign bit cleared — the list libsodium checks in ge25519_has_small_order(). Same list as
# oracle_core.signing; tests check both against the eight points computed from the curve.
_SMALL_ORDER = frozenset(bytes.fromhex(h) for h in (
    "0000000000000000000000000000000000000000000000000000000000000000",  # order 4
    "0100000000000000000000000000000000000000000000000000000000000000",  # order 1 (identity)
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",  # order 8
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",  # order 8
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",  # p-1, order 2
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",  # p (= 0), order 4
    "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",  # p+1 (= 1), order 1
))


def has_small_order(point: bytes) -> bool:
    """Is this 32-byte Ed25519 encoding a point of small order?

    OpenSSL (`cryptography`) accepts, under the identity public key, the signature R = identity,
    S = 0 for EVERY message, and an all-zero key is forgeable the same way after a few tries; no
    secret exists for these keys, so anyone can sign "as" them. A peer, provider or issuer whose
    announced key is one of these would be impersonable by anybody. Verified 2026-10-12 against
    cryptography 50.0.1; refused here for the key and for R, as libsodium does.
    """
    if len(point) != 32:
        return False
    return (point[:31] + bytes([point[31] & 0x7F])) in _SMALL_ORDER


def decode_b64(text: str) -> bytes | None:
    """Base64 in either alphabet, padded or not. ``None`` when it is not base64 at all.

    The spec and the test vectors use standard base64, and so does this hub — but two of
    our own implementations (the factory's AI-Market signer and the UNI bubble) publish
    keys and signatures as unpadded base64url, and a stranger's SDK may do either. Plain
    ``base64.b64decode`` does not fail on a `-`/`_`: with ``validate=False`` it *discards*
    the characters it does not recognise and returns different bytes, so a perfectly good
    signature verified as garbage and the peer was told its signature did not match its key.
    Strict decoding, tried in both alphabets, is the honest reading — it accepts an
    encoding, never a wrong signature.
    """
    if not isinstance(text, str):
        return None         # a peer's JSON can put a number or an object where a key belongs
    raw = text.strip()
    if not raw:
        return None
    padded = raw + "=" * (-len(raw) % 4)
    # `urlsafe_b64decode` takes no `validate`, so the url alphabet is folded into the
    # standard one and decoded strictly: same tolerance, no silent character dropping.
    for candidate in (padded, padded.translate(_URLSAFE_TO_STANDARD)):
        try:
            return base64.b64decode(candidate, validate=True)
        except (ValueError, binascii.Error):
            continue
    return None


def same_key(a: str, b: str) -> bool:
    """Do these two strings name the same key? Encoding is not identity.

    A peer that re-publishes its key in the other base64 alphabet has not rotated it, and
    treating that as a rotation quarantines a peer that did nothing.
    """
    if not a or not b:
        return False
    left, right = decode_b64(a), decode_b64(b)
    if left is None or right is None:
        return a == b
    return left == right


def verify_crypto_ready(key_path: str | Path = "data/hub_signing_key") -> Signer:
    """Fail-fast crypto initialization for hub startup.

    Returns a Signer or exits the process.
    Call this at the top of main() / create_app().
    """
    try:
        return Signer(key_path=key_path)
    except ImportError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
