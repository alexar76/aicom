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

import json
import math
import os
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aimarket_hub.database import HubDatabase


IDENTITY_ALIASES_ENV = "AIMARKET_PEER_IDENTITY_ALIASES"


def _identity_url(value: Any) -> str:
    """A comparison key for an operator-configured peer address; never fetched."""
    if not isinstance(value, str) or not value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{IDENTITY_ALIASES_ENV}: invalid peer URL")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("https", "http") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or "%" in parsed.path
                or any(part in (".", "..") for part in parsed.path.split("/"))):
            raise ValueError
        port = parsed.port
        host = parsed.hostname.lower()
        host = f"[{host}]" if ":" in host else host
        if port is not None and (parsed.scheme, port) not in (("http", 80), ("https", 443)):
            host += f":{port}"
        return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))
    except ValueError:
        raise ValueError(f"{IDENTITY_ALIASES_ENV}: invalid peer URL") from None


def _identity_aliases(raw: str) -> dict[str, tuple[str, ...]]:
    """Explicit verified migrations, not names or peer-supplied declarations.

    The operator must verify the same signing identity before configuring an alias.
    Ambiguous ownership and transitive chains are refused rather than silently pooling
    two providers' reputations. Historical source URLs and signed rows stay unchanged.
    """
    if not raw.strip():
        return {}

    def unique_object(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError
            out[key] = value
        return out

    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, TypeError):
        raise ValueError(f"{IDENTITY_ALIASES_ENV}: expected a JSON object") from None
    if not isinstance(data, dict):
        raise ValueError(f"{IDENTITY_ALIASES_ENV}: expected a JSON object")
    groups: dict[tuple[str, ...], tuple[str, ...]] = {}
    claimed: set[str] = set()
    for canonical, aliases in data.items():
        if not isinstance(aliases, list):
            raise ValueError(f"{IDENTITY_ALIASES_ENV}: aliases must be URL lists")
        group = (_identity_url(canonical), *(_identity_url(alias) for alias in aliases))
        if len(set(group)) != len(group) or claimed.intersection(group):
            raise ValueError(f"{IDENTITY_ALIASES_ENV}: overlapping or cyclic identities")
        claimed.update(group)
        if len(claimed) > 64:
            raise ValueError(f"{IDENTITY_ALIASES_ENV}: too many peer URLs")
        # SQLite/Postgres history retains the exact source URL that was signed
        # or observed. Normalize ownership/lookup only, not stored query values.
        groups[group] = (canonical, *aliases)
    return {url: raw_group for group, raw_group in groups.items() for url in group}


class TrustScorer:
    def __init__(self, db: HubDatabase, weights: tuple[float, float, float, float] | None = None):
        self.db = db
        self.w1, self.w2, self.w3, self.w4 = weights or (0.2, 0.3, 0.35, 0.15)
        self._identity_aliases = _identity_aliases(os.getenv(IDENTITY_ALIASES_ENV, ""))

    def _history_urls(self, provider_hub: str) -> tuple[str, ...]:
        if not self._identity_aliases:
            return (provider_hub,)
        try:
            key = _identity_url(provider_hub)
        except ValueError:
            return (provider_hub,)
        return self._identity_aliases.get(key, (provider_hub,))

    def compute_score(self, provider_hub: str) -> float:
        """Compute trust score for a provider hub (0.0 to 1.0)."""
        if provider_hub == "local":
            return 1.0

        peer = self.db.get_peer(self._history_urls(provider_hub)[0])

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
        events = sorted(
            (event for url in self._history_urls(provider_hub)
             for event in self.db.reputation_events_for(url, limit=10)),
            key=lambda event: event.timestamp, reverse=True,
        )[:10]
        if not events:
            return 100.0  # assume minimum bond
        # Naive: highest price event as proxy for bond
        return max(e.price_usd for e in events) * 10

    def _compute_success_rate(self, provider_hub: str) -> float:
        """Compute success rate from invocation stats (30d window)."""
        thirty_days_ago = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400)
        )
        urls = self._history_urls(provider_hub)
        placeholders = ",".join("?" for _ in urls)
        # Always go through HubDatabase/_conn.execute so Postgres gets sqlite_to_pg
        # (? → %s). A raw cursor().execute leaves SQLite placeholders and psycopg
        # raises "0 placeholders but N parameters were passed".
        total = self.db._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            f"WHERE source_hub IN ({placeholders}) AND timestamp >= ? "
            "AND outcome NOT IN ('refused', 'incomplete')",
            (*urls, thirty_days_ago),
        ).fetchone()[0]
        # Sales this hub cannot see (paid to the seller directly) count when buyers confirmed
        # them with the seller's signed receipt and the transaction (deliveries.py): one
        # success per DISTINCT buyer, not per delivery, so a seller buying from itself through
        # one extra wallet moves the rate by one observation, not by its volume.
        try:
            if len(urls) == 1:
                buyers = sum(v["distinct_buyers"] for (hub, _p), v in self.db.deliveries_30d().items() if hub in urls)
            else:
                # A buyer confirming the same provider before and after its move
                # is one observation, not two new reputation votes.
                buyers = self.db._conn.execute(
                    f"SELECT COUNT(DISTINCT buyer_hash) FROM delivery_confirmations "
                    f"WHERE source_hub IN ({placeholders}) AND kind='delivery' AND confirmed_at >= ?",
                    (*urls, thirty_days_ago),
                ).fetchone()[0]
        except Exception:   # an older schema without the table
            buyers = 0
        if total + buyers == 0:
            return 0.5  # neutral default for no data
        ok = self.db._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            f"WHERE source_hub IN ({placeholders}) AND timestamp >= ? AND outcome='ok'",
            (*urls, thirty_days_ago),
        ).fetchone()[0]
        return (ok + buyers) / (total + buyers)

    def _compute_volume_30d(self, provider_hub: str) -> float:
        thirty_days_ago = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400)
        )
        urls = self._history_urls(provider_hub)
        placeholders = ",".join("?" for _ in urls)
        return self.db._conn.execute(
            f"SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats WHERE source_hub IN ({placeholders}) AND timestamp >= ?",
            (*urls, thirty_days_ago),
        ).fetchone()[0]

    def score_details(self, provider_hub: str) -> dict[str, Any]:
        """Return full breakdown of trust score."""
        return {
            "provider_hub": provider_hub,
            "trust_score": self.compute_score(provider_hub),
            "weights": {"age": self.w1, "bond": self.w2, "success_rate": self.w3, "volume": self.w4},
        }
