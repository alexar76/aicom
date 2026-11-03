"""The ledger's database connection and schema, and the per-wallet open and close rate windows."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("aimarket_hub.channels")


class LedgerStorageMixin:
    """Database connection and schema, and the per-wallet rate windows."""

    # ── Database ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        pass  # Handled by Migrations in __init__

    def _legacy_init_db(self) -> None:
        self._backend.dir.mkdir(parents=True, exist_ok=True) if hasattr(self._backend, 'dir') else None
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    balance_cents INTEGER NOT NULL,
                    original_deposit_cents INTEGER NOT NULL,
                    used_cents INTEGER NOT NULL DEFAULT 0,
                    token TEXT NOT NULL DEFAULT 'USDT',
                    chain TEXT NOT NULL DEFAULT 'base',
                    wallet TEXT NOT NULL DEFAULT '',
                    tx_hash TEXT NOT NULL DEFAULT '',
                    recipient TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    opened_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    settle_tx_hash TEXT NOT NULL DEFAULT '',
                    closed_at TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debited_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_status
                ON channels(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_wallet
                ON channels(wallet)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_expires
                ON channels(expires_at) WHERE status = 'open'
            """)
            conn.commit()

    def _get_conn(self):
        """Return a context-managed DB connection (SQLite or PG)."""
        return self._backend.get_connection()

    # ── Rate limiting ─────────────────────────────────────────────

    def _check_rate(self, wallet: str, rate_store: dict[str, list[float]],
                    max_per_hour: int, anon_max_per_hour: int | None = None) -> bool:
        """Return True if within rate limit, False if exceeded.

        Wallet-less callers are NOT exempt (they used to be, which made a public hub
        unlimited to anyone who simply omitted the wallet field): they share one bucket
        with its own, larger, configurable cap. Note the window is per-process — with N
        workers the effective cap is N x max_per_hour.

        The bucket table is bounded, and a FULL table evicts instead of refusing. The
        previous "fail closed when full" turned a memory DoS into a total availability
        outage: the key is caller-supplied and is charged before any verification, so
        ~50k cheap requests carrying distinct made-up wallet strings filled the table
        and then EVERY new wallet — every real depositor — was refused both open and
        close until the buckets aged out an hour later. Evicting the
        least-recently-active bucket is the right trade: the worst an attacker buys by
        forcing eviction is a reset window for a wallet that had *almost* stopped
        transacting, and the real cap on flooding lives at the HTTP layer (per-IP,
        api.py) where the identity is not attacker-chosen.
        """
        key = (wallet or "").strip() or channels._ANON_RATE_KEY
        if key == channels._ANON_RATE_KEY and anon_max_per_hour is not None:
            limit = anon_max_per_hour   # 0 means "no allowance", not "no limit"
        else:
            limit = max_per_hour
        if limit <= 0:
            return False  # explicitly disabled → refuse rather than allow
        now = time.time()
        window = now - 3600
        hits = [t for t in rate_store.get(key, ()) if t > window]
        if len(hits) >= limit:
            rate_store[key] = hits
            return False
        hits.append(now)
        rate_store[key] = hits
        if len(rate_store) > channels._MAX_RATE_TRACKED_KEYS:
            self._evict_rate_store(rate_store, window, keep=key)
        return True

    @staticmethod
    def _prune_rate_store(rate_store: dict[str, list[float]], window: float) -> None:
        """Drop buckets whose newest hit fell out of the window (they hold no state)."""
        stale = [k for k, hits in rate_store.items() if not hits or max(hits) <= window]
        for k in stale:
            del rate_store[k]

    @classmethod
    def _evict_rate_store(
        cls, rate_store: dict[str, list[float]], window: float, *, keep: str,
    ) -> None:
        """Bound the table in place: expired buckets first, then least-recently-active.

        Expired buckets carry no state, so they go for free. Dropping only those is not
        a bound though — enough distinct keys inside one window keeps every bucket live
        — so anything still over the cap is evicted LRU. ``keep`` is the bucket just
        charged; evicting it would hand this very caller a fresh window.
        """
        # `keep` was charged microseconds ago, so pruning can never drop it.
        cls._prune_rate_store(rate_store, window)
        excess = len(rate_store) - channels._MAX_RATE_TRACKED_KEYS
        if excess <= 0:
            return
        by_age = sorted(
            (k for k in rate_store if k != keep and k != channels._ANON_RATE_KEY),
            key=lambda k: max(rate_store[k]) if rate_store[k] else 0.0,
        )
        for k in by_age[:excess]:
            del rate_store[k]
        if len(rate_store) > channels._MAX_RATE_TRACKED_KEYS:
            logger.error(
                "Rate-limit table still over cap after eviction (%d keys) — the shared "
                "anonymous bucket and the active caller are never evicted",
                len(rate_store),
            )


# Imported after the class on purpose: methods read aimarket_hub.channels at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import channels  # noqa: E402
