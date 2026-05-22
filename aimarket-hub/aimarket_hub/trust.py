"""Trust scorer — computes reputation scores for peer hubs.

Formula:
    trust = w1*age_factor + w2*bond_factor + w3*success_rate + w4*volume_factor

    age_factor   = min(hub_age_days / 365, 1.0)
    bond_factor  = min(log10(bond_usd) / 4, 1.0)
    success_rate = successful / total (30d window)
    volume_factor = min(log10(volume_usd_30d) / 5, 1.0)

Default weights: w1=0.2, w2=0.3, w3=0.35, w4=0.15
"""

from __future__ import annotations

import math
import time
from typing import Any

from aimarket_hub.database import HubDatabase


class TrustScorer:
    def __init__(self, db: HubDatabase, weights: tuple[float, float, float, float] | None = None):
        self.db = db
        self.w1, self.w2, self.w3, self.w4 = weights or (0.2, 0.3, 0.35, 0.15)

    def compute_score(self, provider_hub: str) -> float:
        """Compute trust score for a provider hub (0.0 to 1.0)."""
        if provider_hub == "local":
            return 1.0

        peer = self.db.get_peer(provider_hub)

        # Age factor: how long since first crawl
        age_factor = 0.1  # default for new hubs
        if peer and peer.last_crawl:
            try:
                first_seen = time.mktime(time.strptime(peer.last_crawl, "%Y-%m-%dT%H:%M:%SZ"))
                age_days = (time.time() - first_seen) / 86400.0
                age_factor = min(age_days / 365.0, 1.0)
            except (ValueError, OSError):
                pass

        # Bond factor: economic stake
        bond_usd = self._estimate_bond(provider_hub)
        bond_factor = min(math.log10(max(bond_usd, 1)) / 4.0, 1.0)

        # Success rate: last 30 days
        success_rate = self._compute_success_rate(provider_hub)

        # Volume factor: total USD volume in 30d
        volume_usd = self._compute_volume_30d(provider_hub)
        volume_factor = min(math.log10(max(volume_usd, 0.01)) / 5.0, 1.0)

        score = (
            self.w1 * age_factor
            + self.w2 * bond_factor
            + self.w3 * success_rate
            + self.w4 * volume_factor
        )
        return round(max(0.0, min(1.0, score)), 4)

    def _estimate_bond(self, provider_hub: str) -> float:
        """Estimate bond from reputation events. Returns USD amount."""
        events = self.db.reputation_events_for(provider_hub, limit=10)
        if not events:
            return 100.0  # assume minimum bond
        # Naive: highest price event as proxy for bond
        return max(e.price_usd for e in events) * 10

    def _compute_success_rate(self, provider_hub: str) -> float:
        """Compute success rate from invocation stats (30d window)."""
        thirty_days_ago = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400)
        )
        # Query directly
        cur = self.db._conn.cursor()
        total = cur.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE source_hub=? AND timestamp >= ?",
            (provider_hub, thirty_days_ago),
        ).fetchone()[0]
        if total == 0:
            return 0.5  # neutral default for no data
        ok = cur.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE source_hub=? AND timestamp >= ? AND success=1",
            (provider_hub, thirty_days_ago),
        ).fetchone()[0]
        return ok / total if total > 0 else 0.5

    def _compute_volume_30d(self, provider_hub: str) -> float:
        thirty_days_ago = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400)
        )
        cur = self.db._conn.cursor()
        return cur.execute(
            "SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats WHERE source_hub=? AND timestamp >= ?",
            (provider_hub, thirty_days_ago),
        ).fetchone()[0]

    def score_details(self, provider_hub: str) -> dict[str, Any]:
        """Return full breakdown of trust score."""
        return {
            "provider_hub": provider_hub,
            "trust_score": self.compute_score(provider_hub),
            "weights": {"age": self.w1, "bond": self.w2, "success_rate": self.w3, "volume": self.w4},
        }
