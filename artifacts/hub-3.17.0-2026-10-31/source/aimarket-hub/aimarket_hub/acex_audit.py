"""Proof-of-Audit hub ledger — auditor rewards from invoke revenue (mirrors AgentAuditPool).

Off-chain reference for Pulse Terminal + invoke routing. On-chain bridge via
fundAuditRewards when ACEX_AUDIT_BRIDGE_MODE=onchain (Phase 2 worker).

Storage:
  Production  PostgreSQL via AIMARKET_ACEX_AUDIT_DATABASE_URL / ACEX_AUDIT_DATABASE_URL /
              DATABASE_URL (SQLite refused when AIFACTORY_PROD=1)
  Dev/test    ACEX_AUDIT_DB_PATH SQLite file (default data/acex_audit.db)

Env:
  ACEX_AUDIT_FEE_BPS          Bps of gross invoke → auditors (default 100 = 1%)
  ACEX_AUDIT_DB_PATH          Dev-only SQLite path (default data/acex_audit.db)
  ACEX_AUDIT_BRIDGE_MODE      offchain | onchain | both (default offchain)
  ACEX_AUDIT_POOL_ADDRESS     EVM AgentAuditPool (optional, for indexer)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from aimarket_hub.acex_storage import (
    LedgerNotConfigured,
    warn_not_configured_once,
    require_postgres_url,
    resolve_database_url,
    resolve_sqlite_path,
)

logger = logging.getLogger(__name__)

_MICRO = 1_000_000
_DEFAULT_AUDIT_FEE_BPS = int(os.getenv("ACEX_AUDIT_FEE_BPS", "100"))
_DB_PATH = os.getenv("ACEX_AUDIT_DB_PATH", "data/acex_audit.db")
_BRIDGE_MODE = os.getenv("ACEX_AUDIT_BRIDGE_MODE", "offchain").strip().lower()
_POOL_ADDRESS = os.getenv("ACEX_AUDIT_POOL_ADDRESS", "").strip()

MIN_STAKE_USD = 10_000.0
MIN_COVER_USD = 1_000.0
MIN_AUDIT_SCORE_BPS = 7000
DEFAULT_DROP_BPS = 5000
PHASES = ("open", "insuring", "slashed", "released")
_HUB_AUDITOR = "ai-auditor:acex-v1"
_LEGACY_HUB_AUDITOR = "hub-auditor-pool"


def audit_fee_bps() -> int:
    return max(0, min(10_000, _DEFAULT_AUDIT_FEE_BPS))


def _to_micro(usd: float) -> int:
    return int(round(float(usd) * _MICRO))


def _usd(micro: int) -> float:
    return round(micro / _MICRO, 6)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_risk(
    *,
    defaulted: bool,
    drawdown_bps: int | None,
    aggregate_score_bps: int,
) -> str:
    if defaulted:
        return "defaulted"
    if drawdown_bps is not None and drawdown_bps >= DEFAULT_DROP_BPS:
        return "elevated"
    if drawdown_bps is not None and drawdown_bps >= 3000:
        return "watch"
    if aggregate_score_bps < MIN_AUDIT_SCORE_BPS:
        return "watch"
    return "none"


class AcexAuditLedger:
    def __init__(self, db_path: str = "", database_url: str = "") -> None:
        from aimarket_hub.db_backend import create_backend

        configured_url = (
            database_url
            or resolve_database_url(
                "AIMARKET_ACEX_AUDIT_DATABASE_URL",
                "ACEX_AUDIT_DATABASE_URL",
            )
        ).strip()
        require_postgres_url(configured_url, ledger="audit")
        self._path = resolve_sqlite_path(db_path or _DB_PATH, label="audit")
        self._backend = create_backend(database_url=configured_url, db_path=self._path)
        self._lock = threading.RLock()
        self._init_db()
        logger.info(
            "ACEX audit ledger backend=%s",
            getattr(self._backend, "backend_type", type(self._backend).__name__),
        )

    def _init_db(self) -> None:
        with self._lock, self._backend.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acex_coverages (
                    listing_id   TEXT NOT NULL,
                    auditor      TEXT NOT NULL,
                    cover_micro  INTEGER NOT NULL,
                    score_bps    INTEGER NOT NULL,
                    phase        TEXT NOT NULL,
                    covered_at   TEXT NOT NULL,
                    PRIMARY KEY (listing_id, auditor)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acex_rewards (
                    listing_id      TEXT NOT NULL,
                    auditor         TEXT NOT NULL,
                    pending_micro   INTEGER NOT NULL DEFAULT 0,
                    claimed_micro   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (listing_id, auditor)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acex_listing_state (
                    listing_id            TEXT PRIMARY KEY,
                    aggregate_score_bps   INTEGER NOT NULL DEFAULT 0,
                    total_cover_micro     INTEGER NOT NULL DEFAULT 0,
                    baseline_price_usd    REAL,
                    twap_price_usd        REAL,
                    defaulted             INTEGER NOT NULL DEFAULT 0,
                    approved_at           TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS acex_funding_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id   TEXT NOT NULL,
                    gross_micro  INTEGER NOT NULL,
                    fee_micro    INTEGER NOT NULL,
                    bridged      INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL
                )
            """)
            conn.commit()

    def _ipo_approved(self, listing_id: str) -> dict[str, Any] | None:
        try:
            from aimarket_hub import acex_ipo

            st = acex_ipo.listing_state(listing_id)
            if st.get("error") or st.get("status") != "approved":
                return None
            return st
        except Exception:
            return None

    def ensure_coverage_from_ipo(self, listing_id: str) -> None:
        """Bootstrap synthetic insuring coverage when IPO floated but no chain sync yet."""
        ipo = self._ipo_approved(listing_id)
        if not ipo:
            return
        score = int(ipo.get("audit_score_bps") or MIN_AUDIT_SCORE_BPS)
        auditor = str(ipo.get("auditor_id") or "").strip() or _HUB_AUDITOR
        with self._lock, self._backend.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM acex_coverages WHERE listing_id = ? "
                "AND auditor IN (?, ?) LIMIT 1",
                (listing_id, auditor, _LEGACY_HUB_AUDITOR),
            ).fetchone()
            if row:
                return
            cover_micro = _to_micro(MIN_COVER_USD * 10)
            now = _now()
            conn.execute(
                """INSERT INTO acex_coverages
                   (listing_id, auditor, cover_micro, score_bps, phase, covered_at)
                   VALUES (?, ?, ?, ?, 'insuring', ?)""",
                (listing_id, auditor, cover_micro, score, now),
            )
            conn.execute(
                """INSERT INTO acex_listing_state
                   (listing_id, aggregate_score_bps, total_cover_micro, approved_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(listing_id) DO UPDATE SET
                     approved_at = COALESCE(acex_listing_state.approved_at, excluded.approved_at)""",
                (listing_id, score, cover_micro, ipo.get("listed_at") or now),
            )
            self._recompute_aggregate(conn, listing_id)
            conn.commit()

    def sync_coverage(
        self,
        listing_id: str,
        auditor: str,
        *,
        cover_usd: float,
        score_bps: int,
        phase: str = "insuring",
    ) -> dict[str, Any]:
        phase = (phase or "insuring").strip().lower()
        if phase not in PHASES:
            return {"error": "invalid_phase"}
        if score_bps < MIN_AUDIT_SCORE_BPS or score_bps > 10_000:
            return {"error": "invalid_score_bps"}
        cover_micro = _to_micro(cover_usd)
        if cover_micro < _to_micro(MIN_COVER_USD):
            return {"error": "cover_too_low"}

        with self._lock, self._backend.get_connection() as conn:
            conn.execute(
                """INSERT INTO acex_coverages
                   (listing_id, auditor, cover_micro, score_bps, phase, covered_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(listing_id, auditor) DO UPDATE SET
                     cover_micro = excluded.cover_micro,
                     score_bps = excluded.score_bps,
                     phase = excluded.phase""",
                (listing_id, auditor.strip(), cover_micro, score_bps, phase, _now()),
            )
            self._recompute_aggregate(conn, listing_id)
            conn.commit()
        return {"ok": True, **self.listing_audit_state(listing_id)}

    def _recompute_aggregate(self, conn: Any, listing_id: str) -> None:
        rows = conn.execute(
            """SELECT cover_micro, score_bps FROM acex_coverages
               WHERE listing_id = ? AND phase IN ('open', 'insuring')""",
            (listing_id,),
        ).fetchall()
        total = sum(int(r["cover_micro"]) for r in rows)
        weighted = sum(int(r["cover_micro"]) * int(r["score_bps"]) for r in rows)
        agg = weighted // total if total else 0
        conn.execute(
            """INSERT INTO acex_listing_state
               (listing_id, aggregate_score_bps, total_cover_micro)
               VALUES (?, ?, ?)
               ON CONFLICT(listing_id) DO UPDATE SET
                 aggregate_score_bps = excluded.aggregate_score_bps,
                 total_cover_micro = excluded.total_cover_micro""",
            (listing_id, agg, total),
        )

    def accrue_audit_rewards(self, listing_id: str, gross_usd: float) -> dict[str, Any]:
        gross_micro = _to_micro(gross_usd)
        if gross_micro <= 0:
            return {"error": "non_positive_amount"}

        self.ensure_coverage_from_ipo(listing_id)
        fee_bps = audit_fee_bps()
        fee_micro = gross_micro * fee_bps // 10_000
        if fee_micro <= 0:
            return {
                "ok": True,
                "listing_id": listing_id,
                "to_auditors_usd": 0.0,
                "audit_fee_bps": fee_bps,
            }

        with self._lock, self._backend.get_connection() as conn:
            covs = conn.execute(
                """SELECT auditor, cover_micro FROM acex_coverages
                   WHERE listing_id = ? AND phase = 'insuring'""",
                (listing_id,),
            ).fetchall()
            if not covs:
                return {"error": "no_insuring_coverage"}
            total_cover = sum(int(c["cover_micro"]) for c in covs)
            if total_cover <= 0:
                return {"error": "zero_cover"}

            for c in covs:
                share = fee_micro * int(c["cover_micro"]) // total_cover
                if share <= 0:
                    continue
                conn.execute(
                    """INSERT INTO acex_rewards (listing_id, auditor, pending_micro)
                       VALUES (?, ?, ?)
                       ON CONFLICT(listing_id, auditor) DO UPDATE SET
                         pending_micro = pending_micro + excluded.pending_micro""",
                    (listing_id, c["auditor"], share),
                )
            conn.execute(
                """INSERT INTO acex_funding_log
                   (listing_id, gross_micro, fee_micro, created_at)
                   VALUES (?, ?, ?, ?)""",
                (listing_id, gross_micro, fee_micro, _now()),
            )
            conn.commit()

        return {
            "ok": True,
            "listing_id": listing_id,
            "gross_usd": _usd(gross_micro),
            "to_auditors_usd": _usd(fee_micro),
            "audit_fee_bps": fee_bps,
            "bridge": _BRIDGE_MODE,
        }

    def claim_audit_reward(self, listing_id: str, auditor: str) -> dict[str, Any]:
        auditor = (auditor or "").strip()
        if not auditor:
            return {"error": "missing_auditor"}
        with self._lock, self._backend.get_connection() as conn:
            row = conn.execute(
                """SELECT pending_micro FROM acex_rewards
                   WHERE listing_id = ? AND auditor = ?""",
                (listing_id, auditor),
            ).fetchone()
            if not row:
                return {"error": "nothing_to_claim"}
            pending = int(row["pending_micro"])
            if pending <= 0:
                return {"error": "nothing_to_claim"}
            conn.execute(
                """UPDATE acex_rewards SET pending_micro = 0,
                   claimed_micro = claimed_micro + ?
                   WHERE listing_id = ? AND auditor = ?""",
                (pending, listing_id, auditor),
            )
            conn.commit()
        return {
            "ok": True,
            "listing_id": listing_id,
            "auditor": auditor,
            "claimed_usd": _usd(pending),
        }

    def observe_prices(
        self,
        listing_id: str,
        *,
        baseline_price_usd: float | None = None,
        twap_price_usd: float | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._backend.get_connection() as conn:
            conn.execute(
                """INSERT INTO acex_listing_state (listing_id) VALUES (?)
                   ON CONFLICT(listing_id) DO NOTHING""",
                (listing_id,),
            )
            if baseline_price_usd is not None:
                conn.execute(
                    "UPDATE acex_listing_state SET baseline_price_usd = ? "
                    "WHERE listing_id = ?",
                    (float(baseline_price_usd), listing_id),
                )
            if twap_price_usd is not None:
                conn.execute(
                    "UPDATE acex_listing_state SET twap_price_usd = ? WHERE listing_id = ?",
                    (float(twap_price_usd), listing_id),
                )
            conn.commit()
        return self.listing_audit_state(listing_id)

    def mark_defaulted(self, listing_id: str) -> dict[str, Any]:
        with self._lock, self._backend.get_connection() as conn:
            conn.execute(
                """UPDATE acex_listing_state SET defaulted = 1 WHERE listing_id = ?""",
                (listing_id,),
            )
            conn.execute(
                """UPDATE acex_coverages SET phase = 'slashed'
                   WHERE listing_id = ? AND phase = 'insuring'""",
                (listing_id,),
            )
            conn.commit()
        return self.listing_audit_state(listing_id)

    def listing_audit_state(self, listing_id: str) -> dict[str, Any]:
        self.ensure_coverage_from_ipo(listing_id)
        with self._lock, self._backend.get_connection() as conn:
            st = conn.execute(
                "SELECT * FROM acex_listing_state WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
            covs = conn.execute(
                "SELECT * FROM acex_coverages WHERE listing_id = ? "
                "ORDER BY cover_micro DESC",
                (listing_id,),
            ).fetchall()
            rewards = conn.execute(
                "SELECT auditor, pending_micro, claimed_micro FROM acex_rewards "
                "WHERE listing_id = ?",
                (listing_id,),
            ).fetchall()
        if not st and not covs:
            return {"error": "unknown_listing", "listing_id": listing_id}

        total_cover = (
            int(st["total_cover_micro"])
            if st
            else sum(int(c["cover_micro"]) for c in covs)
        )
        agg = int(st["aggregate_score_bps"]) if st else 0
        baseline = (
            float(st["baseline_price_usd"])
            if st and st["baseline_price_usd"] is not None
            else None
        )
        twap = (
            float(st["twap_price_usd"])
            if st and st["twap_price_usd"] is not None
            else None
        )
        defaulted = bool(int(st["defaulted"])) if st else False
        drawdown_bps = None
        if baseline and twap and baseline > 0:
            drawdown_bps = max(0, int((1.0 - twap / baseline) * 10_000))

        auditors = []
        reward_map = {r["auditor"]: r for r in rewards}
        for c in covs:
            rw = reward_map.get(c["auditor"])
            auditors.append(
                {
                    "auditor": c["auditor"],
                    "cover_usd": _usd(int(c["cover_micro"])),
                    "score_bps": int(c["score_bps"]),
                    "phase": c["phase"],
                    "pending_rewards_usd": (
                        _usd(int(rw["pending_micro"])) if rw else 0.0
                    ),
                    "claimed_rewards_usd": (
                        _usd(int(rw["claimed_micro"])) if rw else 0.0
                    ),
                }
            )

        max_spread = 2000
        spread = max_spread
        if agg >= MIN_AUDIT_SCORE_BPS:
            spread = max(
                100,
                max_spread
                - ((agg - MIN_AUDIT_SCORE_BPS) * max_spread)
                // (10_000 - MIN_AUDIT_SCORE_BPS),
            )

        return {
            "listing_id": listing_id,
            "enabled": total_cover > 0 and agg >= MIN_AUDIT_SCORE_BPS,
            "aggregate_score_bps": agg,
            "total_cover_usd": _usd(total_cover),
            "auditor_count": len(auditors),
            "audit_fee_bps": audit_fee_bps(),
            "accrued_audit_rewards_usd": sum(a["pending_rewards_usd"] for a in auditors),
            "suggested_note_spread_bps": spread,
            "default_risk": _default_risk(
                defaulted=defaulted,
                drawdown_bps=drawdown_bps,
                aggregate_score_bps=agg,
            ),
            "default": {
                "defaulted": defaulted,
                "baseline_price_usd": baseline,
                "twap_price_usd": twap,
                "drawdown_bps": drawdown_bps,
            },
            "coverages": auditors,
            "audit_pool_address": _POOL_ADDRESS or None,
            "bridge_mode": _BRIDGE_MODE,
        }

    def list_audit_states(self, limit: int = 500) -> list[dict[str, Any]]:
        try:
            from aimarket_hub import acex_ipo

            listings = acex_ipo.list_listings(limit=limit)
        except Exception:
            return []
        out = []
        for st in listings:
            if st.get("error"):
                continue
            lid = st.get("listing_id") or st.get("product_id")
            if not lid:
                continue
            audit = self.listing_audit_state(str(lid))
            if not audit.get("error"):
                out.append(audit)
        return out


_ledger: AcexAuditLedger | None = None
_ledger_lock = threading.Lock()


def _get() -> AcexAuditLedger:
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:
                try:
                    _ledger = AcexAuditLedger()
                except LedgerNotConfigured as exc:
                    warn_not_configured_once(exc, "audit")
                    raise
    return _ledger


def _reset_for_tests() -> None:
    global _ledger
    with _ledger_lock:
        _ledger = None


def accrue_audit_rewards(listing_id: str, gross_usd: float) -> dict[str, Any]:
    return _get().accrue_audit_rewards(listing_id, gross_usd)


def claim_audit_reward(listing_id: str, auditor: str) -> dict[str, Any]:
    return _get().claim_audit_reward(listing_id, auditor)


def sync_coverage(
    listing_id: str,
    auditor: str,
    *,
    cover_usd: float,
    score_bps: int,
    phase: str = "insuring",
) -> dict[str, Any]:
    return _get().sync_coverage(
        listing_id, auditor, cover_usd=cover_usd, score_bps=score_bps, phase=phase
    )


def listing_audit_state(listing_id: str) -> dict[str, Any]:
    return _get().listing_audit_state(listing_id)


def observe_prices(
    listing_id: str,
    *,
    baseline_price_usd: float | None = None,
    twap_price_usd: float | None = None,
) -> dict[str, Any]:
    return _get().observe_prices(
        listing_id,
        baseline_price_usd=baseline_price_usd,
        twap_price_usd=twap_price_usd,
    )


def list_audit_states(limit: int = 500) -> list[dict[str, Any]]:
    return _get().list_audit_states(limit=limit)
