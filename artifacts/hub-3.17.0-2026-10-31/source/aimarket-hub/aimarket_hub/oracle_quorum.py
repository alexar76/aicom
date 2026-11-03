"""m-of-n dispute-ruling quorum (threat assessment O-1).

The dispute oracle that decides slashes was single-operator — a trust bottleneck and a
pre-mainnet blocker. This replaces "one operator rules" with "**m of n authorities must each
sign the ruling**". A ruling is only valid when at least ``threshold`` *distinct* authorized
authorities have signed the exact `(dispute_id, slash_pct, ruling)` canonical with their own
key. No single key (including a compromised hub key) can slash a bond alone.

Pure crypto over the existing Ed25519 ``Signer`` — no new infra. Configure via env:

* ``AIMARKET_ORACLE_AUTHORITIES`` — comma-separated base64 Ed25519 public keys (the n).
* ``AIMARKET_ORACLE_THRESHOLD``   — m (default: majority of n).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aimarket_hub.signing import Signer


def ruling_canonical(dispute_id: str, slash_pct: float, ruling_note: str = "") -> str:
    """The exact string every authority signs to authorize a ruling."""
    return f"ruling|dispute:{dispute_id}|slash_pct:{round(float(slash_pct), 6)}|note:{ruling_note}"


@dataclass
class RulingQuorum:
    authorities: frozenset[str]  # authorized authority public keys (base64)
    threshold: int               # m of n required

    @classmethod
    def from_env(cls) -> RulingQuorum | None:
        raw = (os.environ.get("AIMARKET_ORACLE_AUTHORITIES", "") or "").strip()
        if not raw:
            return None
        authorities = frozenset(p.strip() for p in raw.split(",") if p.strip())
        if not authorities:
            return None
        n = len(authorities)
        try:
            m = int(os.environ.get("AIMARKET_ORACLE_THRESHOLD", "") or 0)
        except ValueError:
            m = 0
        if m <= 0:
            m = n // 2 + 1  # majority default
        return cls(authorities=authorities, threshold=max(1, min(m, n)))

    def verify(
        self,
        *,
        dispute_id: str,
        slash_pct: float,
        ruling_note: str,
        signatures: list[dict[str, Any]],
        verifier: Signer,
    ) -> dict[str, Any]:
        """Count distinct authorized authorities with a valid signature over the ruling.

        ``signatures`` = ``[{"pubkey": b64, "sig": b64}, ...]``. A signature counts once,
        only if its pubkey is in ``authorities`` and verifies the canonical. Returns
        ``{ok, valid_signers, threshold, authorities}``.
        """
        canonical = ruling_canonical(dispute_id, slash_pct, ruling_note)
        valid: set[str] = set()
        for s in signatures or []:
            pub = str(s.get("pubkey") or "")
            sig = str(s.get("sig") or "")
            if pub not in self.authorities or pub in valid:
                continue
            try:
                if verifier.verify(pub, sig, canonical):
                    valid.add(pub)
            except Exception:
                continue
        return {
            "ok": len(valid) >= self.threshold,
            "valid_signers": len(valid),
            "threshold": self.threshold,
            "authorities": len(self.authorities),
        }
