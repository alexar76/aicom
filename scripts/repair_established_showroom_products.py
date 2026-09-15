#!/usr/bin/env python3
"""
Restore showroom products stuck in repair loops to their last real pipeline milestone.

Uses ``learning_memory.jsonl`` + ``product_followup`` flags — does NOT wipe tasks/artifacts.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP_DIR = ROOT / "data/state/product_followup"
MEMORY_PATH = ROOT / "data/state/learning_memory.jsonl"
DB_PATH = ROOT / "data/state/pipeline.db"

_STATE_RANK: dict[str, int] = {
    "IDEA_RECEIVED": 0,
    "MARKET_RESEARCHED": 1,
    "SPEC_WRITTEN": 2,
    "MARKET_CONTENT_READY": 3,
    "METHODOLOGY_REVIEWED": 4,
    "ARCH_DESIGNED": 5,
    "DESIGN_CRITIQUED": 6,
    "CODE_COMMITTED": 7,
    "CODE_TESTING": 8,
    "QA_TESTING": 9,
    "BUG_FOUND": 10,
    "DEV_FIXING": 11,
    "SECURITY_SCANNED": 12,
    "HUMAN_REVIEW_PENDING": 13,
    "SALES_ACTIVE": 14,
    "SANDBOX_RUNNING": 15,
    "TELEMETRY_COLLECTING": 16,
    "EVOLUTION_ANALYZING": 17,
    "COMPLETED": 18,
    "DEPLOYED_PRODUCTION": 19,
}

_REPAIR_LOOP_STATES = frozenset(
    {"DEV_FIXING", "BUG_FOUND", "QA_TESTING", "CODE_TESTING", "SECURITY_SCANNED"}
)


def _established_pids() -> list[str]:
    out: list[str] = []
    if not FOLLOWUP_DIR.is_dir():
        return out
    for p in FOLLOWUP_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("storefront_established_listing") or data.get("admin_force_list"):
            out.append(p.stem)
    return sorted(out)


def _max_state_from_memory(pids: set[str]) -> dict[str, str]:
    best: dict[str, tuple[int, str]] = {}
    if not MEMORY_PATH.is_file():
        return {}
    for line in MEMORY_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = str(row.get("product_id") or "")
        if pid not in pids:
            continue
        st = str(row.get("target_state") or "").strip().upper()
        if not st or st in _REPAIR_LOOP_STATES:
            continue
        rank = _STATE_RANK.get(st, -1)
        if rank < 0:
            continue
        prev = best.get(pid)
        if prev is None or rank > prev[0]:
            best[pid] = (rank, st)
    return {pid: st for pid, (_, st) in best.items()}


def main() -> int:
    pids = _established_pids()
    if not pids:
        print("No established showroom products in product_followup/")
        return 0
    if not DB_PATH.is_file():
        print(f"Missing {DB_PATH}")
        return 1

    pid_set = set(pids)
    memory_states = _max_state_from_memory(pid_set)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    now = time.time()
    repaired = 0
    try:
        for pid in pids:
            prod = conn.execute("SELECT id, state FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                print(f"skip {pid}: no product row")
                continue
            cur_state = str(prod["state"] or "").upper()
            target = memory_states.get(pid) or "SANDBOX_RUNNING"
            if _STATE_RANK.get(target, -1) < _STATE_RANK.get("SALES_ACTIVE", 14):
                target = "SALES_ACTIVE"

            tasks_changed = 0
            for t in conn.execute(
                "SELECT id, agent_type, state, status FROM tasks WHERE product_id = ?",
                (pid,),
            ).fetchall():
                if str(t["status"] or "").lower() != "running":
                    continue
                agent = str(t["agent_type"] or "").lower()
                tgt = str(t["state"] or "").upper()
                if agent in ("qa", "developer", "dev", "hardening", "security") and tgt in _REPAIR_LOOP_STATES:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = 'cancelled',
                            error = 'repair_showroom: stale repair task cancelled',
                            completed_at = ?
                        WHERE id = ?
                        """,
                        (now, t["id"]),
                    )
                    tasks_changed += 1

            if cur_state != target:
                conn.execute(
                    "UPDATE products SET state = ?, updated_at = ? WHERE id = ?",
                    (target, now, pid),
                )
                print(f"{pid}: {cur_state} → {target} (memory milestone)")
                repaired += 1
            elif tasks_changed:
                print(f"{pid}: kept {cur_state}, cancelled {tasks_changed} repair task(s)")
                repaired += 1
        conn.commit()
    finally:
        conn.close()
    print(f"Repaired {repaired} product(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
