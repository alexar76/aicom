"""Federated slash synchronization + portable proof-of-misbehavior (F2 / F6).

Today a slash in hub A leaves the agent's standing in hub B untouched — reputation does not
cross the federation, so a cheater just moves hubs. This module closes that gap **without a
central authority**:

* A hub that slashes a bond emits a **signed ``SlashAttestation``** to an append-only,
  per-issuer, monotonically-sequenced log.
* Peers pull each other's logs and **verify the issuer's signature** before storing — a hub
  cannot forge another hub's attestation.
* The reputation score consumes the **union** of local + remote slashes, so misbehavior
  anywhere lowers the agent's score everywhere.

Critical defense (F6): a cross-hub slash is fully trusted only when it carries a **portable
proof-of-misbehavior** — the original dispute *signed by the wronged consumer*. Without it a
malicious hub could poison a competitor's agents by emitting fake slashes.

Two evidence tiers (consensus > one hub's mood):

* **strong** — carries a verifiable consumer-signed PoM. One strong issuer is enough to move
  the federated penalty (the consumer's signature is independently checkable anywhere).
* **weak** — issuer-signed only (e.g. an automated invoke-failure or verified-failure slash,
  optionally carrying self-verifying ``evidence`` such as a signed verification_rejection
  receipt). A single weak issuer NEVER moves the penalty; it takes at least two *distinct*
  hubs independently attesting — cross-hub consensus — and even then each weak issuer
  counts as half a strong one. ``ingest_remote(accept_weak=True)`` opts a hub into storing
  the weak tier at all.

The tier is decided by EVIDENCE, never by authorship. A hub's own slashes are classified with
the same rule its peers apply: PoM present and verifiable → strong, otherwise weak. This hub's
automated ladders (invoke-failure, verified-failure, self-bond breach) carry no consumer-signed
PoM and are therefore weak *locally too* — so a handful of induced failures on one hub cannot
move ``federated_penalty`` by itself, which is exactly what "a lone weak issuer moves nothing"
is supposed to mean. A first-hand operator dispute that DOES carry a verifiable consumer PoM
(``reputation_oracle.resolve_dispute``) still counts fully. For the same reason every
missing/blank tier — an envelope reloaded from an older row, a key never recorded — defaults to
**weak**, never to strong: an unknown tier is not evidence. Rows persisted by the older
authorship rule are re-judged on load: a stored ``strong`` whose envelope carries no PoM at all
is downgraded to weak, so upgrading the code actually retires the inflated penalties instead of
grandfathering them.

The registry is durably backed by the ``slash_attestations`` table when constructed with a
database: the authored log (and its monotonic ``seq``) survives restarts — an append-only
log that forgets on reboot is not append-only.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aimarket_hub.signing import Signer


def _parse_pinned(canonical: str) -> dict[str, str]:
    """Parse a ``k:v|k:v`` canonical into a mapping; {} when it is not that shape.

    Values may themselves contain ``:`` (a hub URL does), so only the FIRST colon in
    each segment separates key from value.
    """
    out: dict[str, str] = {}
    for segment in str(canonical or "").split("|"):
        if ":" not in segment:
            continue
        key, _, value = segment.partition(":")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def _normalize_hub_url(url: str) -> str:
    """Compare hub URLs without tripping over a trailing slash or scheme/host case."""
    raw = str(url or "").strip().rstrip("/")
    if "://" in raw:
        scheme, _, rest = raw.partition("://")
        host, slash, path = rest.partition("/")
        return f"{scheme.lower()}://{host.lower()}{slash}{path}"
    return raw.lower()


def _issuer_identity(env: dict[str, Any]) -> str:
    """The issuer identity the consensus arithmetic may count.

    The **verified** one: ``issuer_pubkey_b64`` is what ``attestation_tier`` checked the
    envelope signature against, and what ``ingest_remote`` pinned to the serving peer.
    ``issuer_hub`` is a self-declared string in the same envelope — counting THAT let one
    peer, with one real key, present itself as N distinct "hubs" (or as an honest
    competitor) and saturate ``federated_penalty`` alone. Falls back to the hub string
    only for rows persisted before envelopes carried the key.
    """
    return str(env.get("issuer_pubkey_b64") or "").strip() or f"hub:{env.get('issuer_hub')}"


@dataclass
class ProofOfMisbehavior:
    """The consumer-signed dispute that justifies a slash — independently verifiable anywhere."""

    dispute_canonical: str
    complainant_pubkey_b64: str
    signature_b64: str

    def verify(self, verifier: Signer) -> bool:
        """Cryptographic check only: this signature really was made by this key.

        NOT sufficient on its own — all three fields arrive in the same envelope, so a
        forger supplies its own keypair and signs anything. :meth:`binds` is the other
        half, and :func:`_evidence_tier` requires both before granting the strong tier.
        """
        if not (self.dispute_canonical and self.complainant_pubkey_b64 and self.signature_b64):
            return False
        try:
            return verifier.verify(self.complainant_pubkey_b64, self.signature_b64, self.dispute_canonical)
        except Exception:
            return False

    def binds(self, *, dispute_id: str, provider_hub: str) -> bool:
        """Does the signed dispute actually name the slash it is offered as proof of?

        ``dispute_canonical`` is ``reputation_oracle.Dispute.canonical()`` — a pinned
        ``key:value|key:value`` string. Without this check the signature proved only that
        SOME consumer signed SOMETHING: a genuine dispute published against provider A
        could be lifted verbatim onto a fabricated attestation against victim B and still
        rate 'strong'. The proof has to be a proof *of this*.
        """
        fields = _parse_pinned(self.dispute_canonical)
        if not fields:
            return False
        return (
            fields.get("dispute_id", "") == str(dispute_id)
            and fields.get("provider_hub", "") == str(provider_hub)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispute_canonical": self.dispute_canonical,
            "complainant_pubkey_b64": self.complainant_pubkey_b64,
            "signature_b64": self.signature_b64,
        }


@dataclass
class SlashAttestation:
    issuer_hub: str       # the hub that performed the slash
    provider_hub: str     # the slashed provider/agent identity
    slashed_usd: float
    dispute_id: str
    reason: str
    seq: int              # monotonic per issuer — replay/dup detection
    timestamp: float
    pom: ProofOfMisbehavior | None = None
    # Self-verifying supporting evidence for no-PoM slashes (weak tier), e.g. the
    # hub-signed verification_rejection receipt behind a verified-failure slash.
    # NOT covered by the issuer canonical (kept for envelope compatibility); its
    # authenticity rests on its OWN embedded signature, verified by consumers.
    evidence: dict[str, Any] | None = field(default=None)
    evidence_kind: str = ""

    def canonical(self) -> str:
        # Deterministic, field-pinned; the PoM is bound in by dispute_id (and verified separately).
        return (
            f"slash|issuer:{self.issuer_hub}|provider:{self.provider_hub}"
            f"|usd:{round(float(self.slashed_usd), 6)}|dispute:{self.dispute_id}"
            f"|seq:{self.seq}|ts:{int(self.timestamp)}"
        )

    def to_envelope(self, signer: Signer) -> dict[str, Any]:
        env: dict[str, Any] = {
            "issuer_hub": self.issuer_hub,
            "provider_hub": self.provider_hub,
            "slashed_usd": self.slashed_usd,
            "dispute_id": self.dispute_id,
            "reason": self.reason,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "pom": self.pom.to_dict() if self.pom else None,
            "issuer_pubkey_b64": signer.public_key_b64,
            "signature_b64": signer.sign_canonical(self.canonical()),
        }
        if self.evidence is not None:
            env["evidence"] = self.evidence
            env["evidence_kind"] = self.evidence_kind
        return env


def _attestation_from_envelope(env: dict[str, Any]) -> SlashAttestation:
    pom_raw = env.get("pom")
    pom = (
        ProofOfMisbehavior(
            dispute_canonical=str(pom_raw.get("dispute_canonical") or ""),
            complainant_pubkey_b64=str(pom_raw.get("complainant_pubkey_b64") or ""),
            signature_b64=str(pom_raw.get("signature_b64") or ""),
        )
        if isinstance(pom_raw, dict)
        else None
    )
    evidence = env.get("evidence")
    return SlashAttestation(
        issuer_hub=str(env.get("issuer_hub") or ""),
        provider_hub=str(env.get("provider_hub") or ""),
        slashed_usd=float(env.get("slashed_usd") or 0.0),
        dispute_id=str(env.get("dispute_id") or ""),
        reason=str(env.get("reason") or ""),
        seq=int(env.get("seq") or 0),
        timestamp=float(env.get("timestamp") or 0.0),
        pom=pom,
        evidence=evidence if isinstance(evidence, dict) else None,
        evidence_kind=str(env.get("evidence_kind") or ""),
    )


def attestation_tier(env: dict[str, Any], verifier: Signer) -> str | None:
    """Classify an envelope: 'strong' (issuer sig + consumer PoM verify), 'weak'
    (issuer sig verifies, no verifiable PoM), or None (issuer sig invalid → discard)."""
    att = _attestation_from_envelope(env)
    issuer_pub = str(env.get("issuer_pubkey_b64") or "")
    sig = str(env.get("signature_b64") or "")
    if not (issuer_pub and sig):
        return None
    try:
        if not verifier.verify(issuer_pub, sig, att.canonical()):
            return None
    except Exception:
        return None
    return _evidence_tier(
        att.pom, verifier, dispute_id=att.dispute_id, provider_hub=att.provider_hub
    )


def _normalize_tier(raw: Any) -> str:
    """Coerce a stored/derived tier label to 'strong' or 'weak', defaulting to WEAK.

    Anything that is not exactly the recorded string 'strong' is treated as weak, so a
    missing, blank or corrupted tier cannot silently gain full penalty weight.
    """
    return "strong" if str(raw or "").strip() == "strong" else "weak"


def _envelope_carries_pom(env: dict[str, Any]) -> bool:
    """True when the envelope structurally CONTAINS a consumer PoM (all three fields set).

    Signature-free check, for the one place that has no verifier: reloading persisted rows.
    It cannot promote anything — it only detects the entries that provably cannot be strong.
    """
    pom = env.get("pom")
    if not isinstance(pom, dict):
        return False
    return all(
        str(pom.get(field) or "").strip()
        for field in ("dispute_canonical", "complainant_pubkey_b64", "signature_b64")
    )


def _evidence_tier(
    pom: ProofOfMisbehavior | None,
    verifier: Signer,
    *,
    dispute_id: str = "",
    provider_hub: str = "",
) -> str:
    """THE tier rule, applied identically to authored and ingested attestations: a
    consumer PoM that both VERIFIES and BINDS to this slash is strong; anything else
    (missing, unverifiable, malformed, or proving a different dispute) is weak.

    The binding arguments are keyword-only and default to empty so a caller that omits
    them gets the weak tier rather than a silent pass — a missing check must not read as
    a passed one.
    """
    if pom is None or not pom.verify(verifier):
        return "weak"
    if not pom.binds(dispute_id=dispute_id, provider_hub=provider_hub):
        return "weak"
    return "strong"


def verify_envelope(env: dict[str, Any], verifier: Signer, *, require_pom: bool = True) -> bool:
    """Verify an attestation envelope: issuer signature, and (optionally) the portable PoM."""
    tier = attestation_tier(env, verifier)
    if tier is None:
        return False
    return tier == "strong" or not require_pom


class SlashRegistry:
    """Per-hub federated slash store. Local appends are authored; remote entries are verified.

    When ``db`` is provided (HubDatabase), every accepted entry — authored or ingested — is
    persisted to ``slash_attestations`` and reloaded on construction, restoring the authored
    monotonic ``seq`` across restarts.
    """

    def __init__(self, hub_url: str, db: Any = None):
        self.hub_url = hub_url
        self._db = db
        self._seq = 0
        # key: (issuer_hub, seq) -> envelope, so re-pulling a peer is idempotent.
        self._entries: dict[tuple[str, int], dict[str, Any]] = {}
        # key -> 'strong' | 'weak', decided by evidence (a verifiable PoM), not by authorship.
        self._tiers: dict[tuple[str, int], str] = {}
        if db is not None:
            self._load()

    # ── persistence ──────────────────────────────────────────────
    def _load(self) -> None:
        try:
            rows = self._db.slash_attestation_load_all()
        except Exception:
            return
        for row in rows:
            issuer = str(row.get("issuer_hub") or "")
            seq = int(row.get("seq") or 0)
            try:
                env = json.loads(row.get("envelope_json") or "{}")
            except Exception:
                continue
            if not (issuer and isinstance(env, dict)):
                continue
            self._entries[(issuer, seq)] = env
            # A missing/blank persisted tier must NOT be promoted to strong — an unrecorded
            # tier is an unknown one, and unknown evidence is no evidence.
            tier = _normalize_tier(row.get("tier"))
            if tier == "strong" and not _envelope_carries_pom(env):
                # Rows written before the tier rule was evidence-based: every authored slash
                # was stamped 'strong', PoM or not. Trusting the stored label would carry that
                # fail-open across the upgrade forever (the automated ladders write no PoM, so
                # such a row alone still pushed federated_penalty to 0.5). The envelope is the
                # evidence; the label is only a cache of a verdict about it.
                tier = "weak"
            self._tiers[(issuer, seq)] = tier
            if issuer == self.hub_url:
                self._seq = max(self._seq, seq)

    def reload(self) -> None:
        """Refresh the in-memory view from durable storage. Called on the event-loop
        thread after a background crawl has persisted freshly-ingested peer attestations
        through its OWN connection — so federated_penalty reflects them without a restart
        and without the crawl worker ever writing this registry's app connection."""
        if self._db is not None:
            self._load()

    def _persist(self, issuer: str, seq: int, env: dict[str, Any], tier: str) -> None:
        # Best-effort: only REMOTE ingests use this, and they are re-pullable, so a
        # dropped write is recovered on the next crawl. Authored slashes take the
        # durable, seq-allocating path in record_local_slash instead.
        if self._db is None:
            return
        try:
            self._db.slash_attestation_save(issuer, seq, json.dumps(env, ensure_ascii=False), tier)
        except Exception:
            pass

    # ── local authoring ──────────────────────────────────────────
    def record_local_slash(
        self,
        *,
        provider_hub: str,
        slashed_usd: float,
        dispute_id: str,
        reason: str,
        signer: Signer,
        pom: ProofOfMisbehavior | None = None,
        evidence: dict[str, Any] | None = None,
        evidence_kind: str = "",
    ) -> dict[str, Any]:
        # The envelope signature covers the seq, so the seq must be fixed before signing.
        def _build(seq: int) -> dict[str, Any]:
            att = SlashAttestation(
                issuer_hub=self.hub_url,
                provider_hub=provider_hub,
                slashed_usd=slashed_usd,
                dispute_id=dispute_id,
                reason=reason,
                seq=seq,
                timestamp=time.time(),
                pom=pom,
                evidence=evidence,
                evidence_kind=evidence_kind,
            )
            return att.to_envelope(signer)

        # Evidence, not authorship, decides the tier. Hardcoding 'strong' here made every
        # automated local slash (invoke-failure / verified-failure / self-bond breach) a
        # full-weight issuer, so 3 induced failures on ONE hub pushed federated_penalty to
        # 0.5 — the exact opposite of the documented "a lone weak issuer moves nothing".
        tier = _evidence_tier(
            pom, signer, dispute_id=dispute_id, provider_hub=provider_hub
        )

        if self._db is not None:
            # DB-authoritative seq: allocated + persisted atomically (multi-worker safe),
            # BEFORE we advance in-memory state or serve the envelope. A failure raises —
            # the caller (supply_security.slash) degrades to federated=False — so we never
            # serve (via export()) a seq that peers would mirror but isn't durable.
            seq, env = self._db.slash_attestation_append(self.hub_url, _build, tier)
        else:
            # In-memory-only registry (no DB): monotonic per-instance counter.
            seq = self._seq + 1
            env = _build(seq)
        self._seq = max(self._seq, seq)
        key = (self.hub_url, seq)
        self._entries[key] = env
        self._tiers[key] = tier
        return env

    def export(self) -> list[dict[str, Any]]:
        """Signed log this hub serves to peers (e.g. GET /reputation/slashes)."""
        return [e for (issuer, _), e in self._entries.items() if issuer == self.hub_url]

    # ── remote ingestion ─────────────────────────────────────────
    def ingest_remote(
        self,
        envelopes: list[dict[str, Any]],
        verifier: Signer,
        *,
        require_pom: bool = True,
        accept_weak: bool = False,
        expected_issuer_pubkey: str | None = None,
        peer_url: str | None = None,
    ) -> int:
        """Verify and store peers' attestations. Returns the number newly accepted.

        ``expected_issuer_pubkey`` binds the issuer identity to the **serving peer's known
        public key** (from the peer table). When set, an envelope whose ``issuer_pubkey_b64``
        does not match is rejected — so a peer cannot serve attestations forged "from" another
        hub. Leave None only when the issuer key is already trusted by other means.

        ``peer_url`` binds the self-declared ``issuer_hub`` STRING to that same peer. The key
        check alone was not enough: the dedupe key and the consensus sets were derived from
        the string, so one peer signing with its one real key could declare a different
        ``issuer_hub`` per envelope — presenting itself as N distinct hubs, or as an honest
        competitor — and drive ``federated_penalty`` to 1.0 by itself.

        Tiering: a valid consumer PoM → **strong**. No PoM → **weak**, stored only when
        ``accept_weak=True`` (or ``require_pom=False``, the legacy full-trust switch, which
        stores it as weak too). Weak entries only move ``federated_penalty`` under cross-hub
        consensus — see ``federated_penalty``.
        """
        added = 0
        for env in envelopes or []:
            issuer = str(env.get("issuer_hub") or "")
            if not issuer or issuer == self.hub_url:
                continue  # never let a peer overwrite our own authored log
            if expected_issuer_pubkey is not None and str(env.get("issuer_pubkey_b64") or "") != expected_issuer_pubkey:
                continue  # issuer identity not bound to the serving peer
            if peer_url is not None and _normalize_hub_url(issuer) != _normalize_hub_url(peer_url):
                continue  # a peer may only vouch for slashes it issued AS ITSELF
            seq = int(env.get("seq") or 0)
            if (issuer, seq) in self._entries:
                continue
            tier = attestation_tier(env, verifier)
            if tier is None:
                continue
            if tier == "weak" and require_pom and not accept_weak:
                continue
            self._entries[(issuer, seq)] = env
            self._tiers[(issuer, seq)] = tier
            self._persist(issuer, seq, env, tier)
            added += 1
        return added

    # ── aggregated signal ────────────────────────────────────────
    def slash_signal(self, provider_hub: str) -> dict[str, Any]:
        """Union view of slashes against a provider across the whole federation."""
        matched = [
            (key, e) for key, e in self._entries.items()
            if str(e.get("provider_hub")) == provider_hub
        ]
        issuers = {str(e.get("issuer_hub")) for _, e in matched}
        strong_issuers = {
            str(e.get("issuer_hub")) for key, e in matched
            # An entry with no recorded tier defaults to WEAK: promoting an unknown tier to
            # strong would let a single untiered attestation move the penalty on its own.
            if _normalize_tier(self._tiers.get(key)) == "strong"
        }
        weak_issuers = {str(e.get("issuer_hub")) for key, e in matched} - strong_issuers
        # The COUNTED identity is the verified signing key, never the self-declared hub
        # string — see _issuer_identity. The *_issuers lists above stay hub URLs because
        # they are the human-readable/API view; only the arithmetic below is authoritative.
        strong_keys = {
            _issuer_identity(e) for key, e in matched
            if _normalize_tier(self._tiers.get(key)) == "strong"
        }
        weak_keys = {_issuer_identity(e) for key, e in matched} - strong_keys
        total = round(sum(float(e.get("slashed_usd") or 0.0) for _, e in matched), 4)
        return {
            "provider_hub": provider_hub,
            "slash_count": len(matched),
            "distinct_issuers": len(issuers),
            "distinct_issuer_keys": len(strong_keys | weak_keys),
            "total_slashed_usd": total,
            "issuers": sorted(issuers),
            "strong_issuers": sorted(strong_issuers),
            "weak_issuers": sorted(weak_issuers),
            "strong_issuer_keys": len(strong_keys),
            "weak_issuer_keys": len(weak_keys),
        }

    def federated_penalty(self, provider_hub: str) -> float:
        """0.0 (clean) … 1.0 (heavily slashed across many hubs) — a reputation multiplier input.

        Saturating in the number of *distinct* hubs that slashed the provider: cross-hub
        consensus is the strong signal, not one hub slashing repeatedly.

        Strong issuers (consumer-PoM-backed) count fully. Weak issuers (issuer-signed only)
        require consensus — a single weak issuer contributes NOTHING (one hub's mood is not
        evidence), and once ≥2 distinct weak issuers agree, each counts as half a strong one.
        """
        sig = self.slash_signal(provider_hub)
        # Distinct VERIFIED KEYS, not distinct issuer_hub strings: the string is
        # attacker-chosen and one key could claim many of them.
        strong = int(sig["strong_issuer_keys"])
        weak = int(sig["weak_issuer_keys"])
        effective = float(strong) + (0.5 * weak if weak >= 2 else 0.0)
        if effective <= 0:
            return 0.0
        return round(min(1.0, 1.0 - 0.5**effective), 4)  # strong: 1→0.5, 2→0.75, 3→0.875, …
