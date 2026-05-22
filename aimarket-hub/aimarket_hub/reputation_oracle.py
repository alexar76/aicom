"""Reputation Oracle + Capability Staking (#1)

Providers lock USDT-bond against quality. Every invoke generates a signed
outcome from the consumer: {success, latency, quality_score}. On dispute
(also signed), bond is partially slashed and paid to the affected party.

Reputation is an on-chain aggregate, not website reviews.

Architecture:
    Provider stakes USDT → bond recorded on-chain
    Consumer invokes → receives signed outcome
    Consumer disputes → submits signed dispute
    Oracle verifies → slashes bond → pays consumer
    Trust score = f(bond_size, success_rate, age, volume, slash_history)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aimarket_hub.signing import Signer


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    DISPUTED = "disputed"


@dataclass
class SignedOutcome:
    """Consumer-signed invocation outcome. Verifiable proof of what happened."""

    invocation_id: str
    capability_id: str
    product_id: str
    provider_hub: str
    consumer_hub: str
    status: OutcomeStatus
    price_usd: float
    latency_ms: int
    quality_score: float  # 0.0 - 1.0, consumer-assessed
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""  # Ed25519 signature from consumer

    def canonical(self) -> str:
        return (
            f"invocation_id:{self.invocation_id}"
            f"|capability_id:{self.capability_id}"
            f"|product_id:{self.product_id}"
            f"|provider_hub:{self.provider_hub}"
            f"|consumer_hub:{self.consumer_hub}"
            f"|status:{self.status.value}"
            f"|price_usd:{self.price_usd}"
            f"|latency_ms:{self.latency_ms}"
            f"|quality_score:{self.quality_score}"
            f"|timestamp:{self.timestamp}"
        )

    def sign(self, signer: Signer) -> "SignedOutcome":
        self.signature = signer.sign_canonical(self.canonical())
        return self

    def verify(self, public_key_b64: str, signer: Signer) -> bool:
        return signer.verify(public_key_b64, self.signature, self.canonical())


@dataclass
class Dispute:
    """Consumer-signed dispute claiming provider delivered bad quality."""

    dispute_id: str
    invocation_id: str
    provider_hub: str
    consumer_hub: str
    reason: str  # Human-readable reason
    evidence: dict[str, Any] = field(default_factory=dict)
    requested_slash_pct: float = 0.0  # 0.0 - 1.0 of bond
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""

    def canonical(self) -> str:
        return (
            f"dispute_id:{self.dispute_id}"
            f"|invocation_id:{self.invocation_id}"
            f"|provider_hub:{self.provider_hub}"
            f"|consumer_hub:{self.consumer_hub}"
            f"|reason:{self.reason}"
            f"|requested_slash_pct:{self.requested_slash_pct}"
            f"|timestamp:{self.timestamp}"
        )

    def sign(self, signer: Signer) -> "Dispute":
        self.signature = signer.sign_canonical(self.canonical())
        return self


@dataclass
class Bond:
    """Provider's economic stake in quality."""

    provider_hub: str
    amount_usd: float
    token: str = "USDT"
    chain: str = "base"
    tx_hash: str = ""
    locked_at: str = ""
    unlocks_at: str = ""  # Optional time-lock
    slashed_amount_usd: float = 0.0
    active: bool = True

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.amount_usd - self.slashed_amount_usd)


class ReputationOracle:
    """On-chain reputation aggregation for capability providers.

    Tracks bonds, outcomes, and disputes. Computes trust scores that include
    slash history as a negative signal.
    """

    def __init__(self, signer: Signer | None = None):
        self.signer = signer or Signer()
        self._bonds: dict[str, Bond] = {}  # provider_hub → Bond
        self._outcomes: list[SignedOutcome] = []
        self._disputes: list[Dispute] = []

    # ── Bond Management ───────────────────────────────────────

    def stake_bond(
        self,
        provider_hub: str,
        amount_usd: float,
        token: str = "USDT",
        chain: str = "base",
        tx_hash: str = "",
        lock_days: int = 30,
    ) -> Bond:
        """Record a new bond stake from a provider."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        unlock = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + lock_days * 86400),
        )
        bond = Bond(
            provider_hub=provider_hub,
            amount_usd=amount_usd,
            token=token,
            chain=chain,
            tx_hash=tx_hash,
            locked_at=now,
            unlocks_at=unlock,
        )
        # Add to existing bond if present
        existing = self._bonds.get(provider_hub)
        if existing and existing.active:
            bond.amount_usd += existing.remaining_usd
            bond.slashed_amount_usd = existing.slashed_amount_usd
        self._bonds[provider_hub] = bond
        return bond

    def get_bond(self, provider_hub: str) -> Bond | None:
        return self._bonds.get(provider_hub)

    def total_bonded_usd(self) -> float:
        return sum(b.remaining_usd for b in self._bonds.values() if b.active)

    # ── Outcome Recording ─────────────────────────────────────

    def record_outcome(
        self,
        invocation_id: str,
        capability_id: str,
        product_id: str,
        provider_hub: str,
        consumer_hub: str,
        status: OutcomeStatus,
        price_usd: float,
        latency_ms: int,
        quality_score: float,
    ) -> SignedOutcome:
        """Record a consumer-signed invocation outcome."""
        outcome = SignedOutcome(
            invocation_id=invocation_id,
            capability_id=capability_id,
            product_id=product_id,
            provider_hub=provider_hub,
            consumer_hub=consumer_hub,
            status=status,
            price_usd=price_usd,
            latency_ms=latency_ms,
            quality_score=quality_score,
        ).sign(self.signer)
        self._outcomes.append(outcome)
        return outcome

    def get_outcomes_for_provider(self, provider_hub: str, limit: int = 100) -> list[SignedOutcome]:
        return [o for o in self._outcomes if o.provider_hub == provider_hub][-limit:]

    def success_rate(self, provider_hub: str, window_days: int = 30) -> float:
        cutoff = time.time() - window_days * 86400
        outcomes = [
            o for o in self._outcomes
            if o.provider_hub == provider_hub
            and _ts_to_unix(o.timestamp) >= cutoff
        ]
        if not outcomes:
            return 0.5
        ok = sum(1 for o in outcomes if o.status == OutcomeStatus.SUCCESS)
        return ok / len(outcomes)

    def avg_quality_score(self, provider_hub: str, window_days: int = 30) -> float:
        cutoff = time.time() - window_days * 86400
        scores = [
            o.quality_score for o in self._outcomes
            if o.provider_hub == provider_hub
            and _ts_to_unix(o.timestamp) >= cutoff
        ]
        return sum(scores) / len(scores) if scores else 0.0

    # ── Dispute Resolution ────────────────────────────────────

    def file_dispute(
        self,
        invocation_id: str,
        provider_hub: str,
        consumer_hub: str,
        reason: str,
        requested_slash_pct: float = 0.1,
        evidence: dict[str, Any] | None = None,
    ) -> Dispute:
        """File a signed dispute against a provider."""
        dispute_id = hashlib.sha256(
            f"{invocation_id}:{provider_hub}:{consumer_hub}:{time.time()}".encode()
        ).hexdigest()[:16]

        dispute = Dispute(
            dispute_id=dispute_id,
            invocation_id=invocation_id,
            provider_hub=provider_hub,
            consumer_hub=consumer_hub,
            reason=reason,
            evidence=evidence or {},
            requested_slash_pct=requested_slash_pct,
        ).sign(self.signer)
        self._disputes.append(dispute)
        return dispute

    def resolve_dispute(
        self,
        dispute_id: str,
        slash_pct: float,
        ruling_note: str = "",
    ) -> dict[str, Any]:
        """Resolve a dispute by slashing the provider's bond.

        In production, this would be a multi-sig or DAO vote.
        Here it's oracle-administered.
        """
        dispute = next((d for d in self._disputes if d.dispute_id == dispute_id), None)
        if not dispute:
            return {"error": "dispute not found"}

        bond = self._bonds.get(dispute.provider_hub)
        if not bond or not bond.active:
            return {"error": "no active bond for provider"}

        slash_amount = min(bond.remaining_usd, bond.amount_usd * slash_pct)
        bond.slashed_amount_usd += slash_amount

        return {
            "dispute_id": dispute_id,
            "resolved": True,
            "provider_hub": dispute.provider_hub,
            "slashed_usd": round(slash_amount, 4),
            "bond_remaining_usd": round(bond.remaining_usd, 4),
            "ruling": ruling_note,
        }

    def dispute_count(self, provider_hub: str) -> int:
        return sum(1 for d in self._disputes if d.provider_hub == provider_hub)

    def slash_ratio(self, provider_hub: str) -> float:
        """Portion of bond that has been slashed (0.0 = clean, 1.0 = fully slashed)."""
        bond = self._bonds.get(provider_hub)
        if not bond or bond.amount_usd == 0:
            return 1.0 if bond and bond.slashed_amount_usd > 0 else 0.0
        return min(1.0, bond.slashed_amount_usd / bond.amount_usd)

    # ── Aggregated Reputation ─────────────────────────────────

    def compute_reputation_score(self, provider_hub: str) -> dict[str, Any]:
        """Compute the full reputation profile for a provider."""
        bond = self.get_bond(provider_hub)
        bond_usd = bond.remaining_usd if bond else 0.0

        success = self.success_rate(provider_hub)
        quality = self.avg_quality_score(provider_hub)
        disputes = self.dispute_count(provider_hub)
        slash = self.slash_ratio(provider_hub)

        # Score formula (higher is better):
        #   base = 0.5
        #   + 0.2 * log10(1+bond_usd)/4  (bond signal)
        #   + 0.3 * success_rate           (performance)
        #   + 0.2 * quality_score          (consumer satisfaction)
        #   - 0.3 * slash_ratio            (punishment for slashing)
        #   - 0.05 * min(disputes, 10)/10  (dispute count penalty)
        import math

        bond_signal = min(math.log10(1 + bond_usd) / 4.0, 1.0) * 0.2
        perf_signal = success * 0.3
        quality_signal = quality * 0.2
        slash_penalty = slash * 0.3
        dispute_penalty = min(disputes / 10.0, 1.0) * 0.05

        score = 0.5 + bond_signal + perf_signal + quality_signal - slash_penalty - dispute_penalty

        return {
            "provider_hub": provider_hub,
            "score": round(max(0.0, min(1.0, score)), 4),
            "bond_usd": round(bond_usd, 2),
            "success_rate_30d": round(success, 4),
            "avg_quality_score_30d": round(quality, 4),
            "dispute_count": disputes,
            "slash_ratio": round(slash, 4),
            "total_outcomes": len(self.get_outcomes_for_provider(provider_hub)),
        }


def _ts_to_unix(ts: str) -> float:
    try:
        return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OSError):
        return 0.0
