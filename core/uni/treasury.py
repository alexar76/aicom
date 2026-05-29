"""Treasury reserve invariant: on-chain USDT ≥ outstanding UNI × $0.01."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.uni.config import uni_db_backend, uni_treasury_usdt_observed
from core.uni.constants import PLATFORM_OWNER_ID, TREASURY_HEALTHY_RATIO
from core.uni.pricing import uni_to_usd
from core.uni.store import now_ts, row_to_dict, uni_connection

logger = logging.getLogger(__name__)


def get_latest_treasury_audit() -> dict[str, Any] | None:
    """Read-only: latest stored snapshot without writing a new row."""
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                """
                SELECT snapshot_id, ts, total_uni_outstanding, total_uni_platform,
                       usdt_required, usdt_observed_on_chain, reserve_ratio, healthy, note
                FROM uni_treasury_audit ORDER BY ts DESC LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT snapshot_id, ts, total_uni_outstanding, total_uni_platform,
                       usdt_required, usdt_observed_on_chain, reserve_ratio, healthy, note
                FROM uni_treasury_audit ORDER BY ts DESC LIMIT 1
                """
            ).fetchone()
    if not row:
        return None
    data = row_to_dict(row)
    return {
        "snapshot_id": data.get("snapshot_id"),
        "ts": data.get("ts"),
        "total_uni_outstanding": int(data.get("total_uni_outstanding") or 0),
        "total_uni_platform": int(data.get("total_uni_platform") or 0),
        "usdt_required": float(data.get("usdt_required") or 0),
        "usdt_observed_on_chain": float(data.get("usdt_observed_on_chain") or 0),
        "reserve_ratio": float(data.get("reserve_ratio") or 0),
        "healthy": bool(data.get("healthy")),
        "note": data.get("note") or "",
    }


def snapshot_treasury_audit(*, usdt_observed: float | None = None) -> dict[str, Any]:
    """
    Record ``uni_treasury_audit`` row.

    ``usdt_observed`` may come from chain indexer; falls back to
    ``AIFACTORY_UNI_TREASURY_USDT_OBSERVED`` env for ops/manual audits.
    """
    observed = usdt_observed
    if observed is None:
        observed = uni_treasury_usdt_observed()
    if observed is None:
        observed = 0.0

    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN owner_id != %s THEN balance_uni + hold_uni ELSE 0 END), 0) AS outstanding,
                  COALESCE(SUM(CASE WHEN owner_id = %s THEN balance_uni ELSE 0 END), 0) AS platform_uni
                FROM uni_wallets
                """,
                (PLATFORM_OWNER_ID, PLATFORM_OWNER_ID),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN owner_id != ? THEN balance_uni + hold_uni ELSE 0 END), 0) AS outstanding,
                  COALESCE(SUM(CASE WHEN owner_id = ? THEN balance_uni ELSE 0 END), 0) AS platform_uni
                FROM uni_wallets
                """,
                (PLATFORM_OWNER_ID, PLATFORM_OWNER_ID),
            ).fetchone()
        data = row_to_dict(row)
        outstanding = int(round(float(data.get("outstanding") or 0)))
        platform_uni = int(round(float(data.get("platform_uni") or 0)))
        required = uni_to_usd(outstanding)
        ratio = (float(observed) / required) if required > 1e-9 else 1.0
        healthy = 1 if ratio >= TREASURY_HEALTHY_RATIO else 0
        snapshot_id = f"snap_{uuid.uuid4().hex[:16]}"
        ts = now_ts()
        note = "" if healthy else f"reserve_ratio={ratio:.4f} below {TREASURY_HEALTHY_RATIO}"
        if uni_db_backend() == "postgres":
            conn.execute(
                """
                INSERT INTO uni_treasury_audit (
                    snapshot_id, ts, total_uni_outstanding, total_uni_platform,
                    usdt_required, usdt_observed_on_chain, reserve_ratio, healthy, note
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (snapshot_id, ts, outstanding, platform_uni, required, observed, ratio, healthy, note),
            )
        else:
            conn.execute(
                """
                INSERT INTO uni_treasury_audit (
                    snapshot_id, ts, total_uni_outstanding, total_uni_platform,
                    usdt_required, usdt_observed_on_chain, reserve_ratio, healthy, note
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (snapshot_id, ts, outstanding, platform_uni, required, observed, ratio, healthy, note),
            )
        if not healthy:
            logger.warning("UNI treasury unhealthy: required=%.2f observed=%.2f ratio=%.4f", required, observed, ratio)
    return {
        "snapshot_id": snapshot_id,
        "total_uni_outstanding": outstanding,
        "total_uni_platform": platform_uni,
        "usdt_required": required,
        "usdt_observed_on_chain": observed,
        "reserve_ratio": round(ratio, 6),
        "healthy": bool(healthy),
        "note": note,
    }
