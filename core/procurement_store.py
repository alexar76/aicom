"""Durable purchase journal. Unknown payments keep their reservation across restarts."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def micros(value: object) -> int:
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("expected a finite non-negative USD amount")
    return int((number * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class PurchaseStore:
    def __init__(self, root: Path):
        self.path = root / "state" / "procurement.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    product TEXT NOT NULL, issue TEXT NOT NULL, observation TEXT NOT NULL,
                    PRIMARY KEY(product, issue, observation)
                );
                CREATE TABLE IF NOT EXISTS purchases (
                    id TEXT PRIMARY KEY, product TEXT NOT NULL, issue TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, supplier TEXT NOT NULL,
                    created REAL NOT NULL, status TEXT NOT NULL,
                    reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
                    payment TEXT NOT NULL, request TEXT NOT NULL,
                    response TEXT, report TEXT, reason TEXT NOT NULL DEFAULT '',
                    applied INTEGER NOT NULL DEFAULT 0, outcome TEXT,
                    receipt_nonce TEXT UNIQUE, settled REAL,
                    observation TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_purchase ON purchases(product)
                    WHERE payment = 'unknown';
            """)
            self.path.chmod(0o600)
            yield conn
        finally:
            conn.close()

    def observe(self, product: str, issue: str, observation: str) -> int:
        with self.connection() as conn:
            conn.execute("INSERT OR IGNORE INTO observations VALUES (?, ?, ?)", (product, issue, observation))
            return conn.execute("SELECT COUNT(*) FROM observations WHERE product=? AND issue=?",
                                (product, issue)).fetchone()[0]

    def orders(self, product: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM purchases WHERE product=? ORDER BY created", (product,)) \
                if product else conn.execute("SELECT * FROM purchases ORDER BY created")
            return [dict(row) for row in rows]

    def exposure(self, product: str) -> int:
        return sum(row["charged"] + row["reserved"] for row in self.orders(product))

    def reserve(self, *, order: dict, amount: int, llm_spent: int, total_cap: int,
                external_cap: int, daily_cap: int, completion_reserve: int, max_attempts: int) -> bool:
        """BEGIN IMMEDIATE serializes all purchases, including the company-wide daily cap.

        The LLM spend is an observed snapshot, not a prediction of future token usage.
        Open orders from earlier days continue to consume today's daily allowance.
        """
        now = time.time()
        day = int(now // 86400) * 86400
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = [dict(r) for r in conn.execute("SELECT * FROM purchases")]
            own = [r for r in rows if r["product"] == order["product"]]
            external = sum(r["charged"] + r["reserved"] for r in own)
            daily = sum(r["reserved"] + (r["charged"] if (r["settled"] or r["created"]) >= day else 0)
                        for r in rows)
            prior = [r for r in own if r["issue"] == order["issue"]]
            refused = (
                any(r["payment"] == "unknown" for r in own)
                or any(r["id"] == order["id"] for r in rows)
                or bool(order.get("observation") and any(
                    r["observation"] == order["observation"] for r in own))
                or len(prior) >= max_attempts
                or any(r["supplier"] == order["supplier"] for r in prior)
                or any(r["status"] == "accepted" for r in prior)
                or total_cap <= 0
                or llm_spent + external + amount + completion_reserve > total_cap
                or external + amount > external_cap
                or daily + amount > daily_cap
            )
            if refused:
                conn.rollback()
                return False
            conn.execute("""INSERT INTO purchases
                (id,product,issue,fingerprint,supplier,created,status,reserved,payment,request,observation)
                VALUES (?,?,?,?,?,?,'in_flight',?,'unknown',?,?)""",
                (order["id"], order["product"], order["issue"], order["fingerprint"],
                 order["supplier"], now, amount, json.dumps(order["request"], ensure_ascii=False),
                 order.get("observation", "")))
            conn.commit()
            return True

    def finish(self, order_id: str, *, status: str, response: dict | None = None,
               charged: int | None = None, report: dict | None = None, reason: str = "") -> None:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM purchases WHERE id=?", (order_id,)).fetchone()
            if row is None or row["payment"] != "unknown":
                conn.rollback()
                return
            known = charged is not None
            conn.execute("""UPDATE purchases SET status=?,response=?,report=?,reason=?,
                         charged=?,reserved=?,payment=?,receipt_nonce=?,settled=? WHERE id=?""",
                         (status, json.dumps(response, ensure_ascii=False), json.dumps(report, ensure_ascii=False),
                          reason, charged if known else 0, 0 if known else row["reserved"],
                          ("paid" if charged else "not_charged") if known else "unknown",
                          ((response or {}).get("receipt") or {}).get("nonce"), time.time() if known else None,
                          order_id))
            conn.commit()

    def mark_applied(self, order_id: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE purchases SET applied=1 WHERE id=? AND status='accepted'", (order_id,))

    def record_outcome(self, order_id: str, outcome: dict) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE purchases SET outcome=? WHERE id=? AND outcome IS NULL",
                         (json.dumps(outcome), order_id))
