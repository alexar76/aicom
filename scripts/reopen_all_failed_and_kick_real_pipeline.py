#!/usr/bin/env python3
"""
Re-open every FAILED product, cancel stale pending/running tasks, optionally enqueue
new real (non-demo) products toward a target count in pipeline.

Usage (repo root):
  python3 scripts/reopen_all_failed_and_kick_real_pipeline.py --dry-run
  python3 scripts/reopen_all_failed_and_kick_real_pipeline.py --target-real 10

Docker:
  docker compose exec -T app python3 /app/scripts/reopen_all_failed_and_kick_real_pipeline.py --target-real 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reopen-failed-kick")

DEFAULT_NOTES = (
    "Operator mass-rework: complete specification with testable acceptance_criteria per user story, "
    "full methodology coverage, then architecture and shippable demo UI. Prioritize storefront-ready "
    "deliverable over partial output."
)

NEW_REAL_IDEAS: list[tuple[str, str]] = [
    (
        "full_software",
        "TeamShift Pro — shift scheduling SaaS for retail chains: drag-drop rosters, labor law break rules, "
        "mobile clock-in, manager approvals. Ship React demo with seeded stores and staff.",
    ),
    (
        "full_software",
        "InvoiceFlow — B2B AR automation: invoice PDF generation, Stripe payment links, dunning emails, "
        "CFO dashboard with aging buckets. Demo multi-tenant UI with sample clients.",
    ),
    (
        "landing",
        "Marketing landing — cybersecurity MDR for SMB: hero, threat stats, pricing tiers, book-a-demo form, "
        "compliance badges section.",
    ),
    (
        "full_software",
        "LearnPath LMS lite — course builder, quiz module, student progress table, instructor analytics. "
        "Demo with 2 courses and quiz attempts.",
    ),
    (
        "landing",
        "Marketing landing — legal AI contract review for startups: ROI calculator, testimonial strip, "
        "FAQ, waitlist CTA.",
    ),
]


def _truthy(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def _is_demo(pid: str) -> bool:
    return pid.startswith("prod-demo-")


def _cancel_stale_tasks(sm, product_id: str, *, dry_run: bool) -> int:
    now = time.time()
    tasks = sm.get_tasks_by_product(product_id)
    n = 0
    for t in tasks:
        st = str(t.get("status") or "").lower()
        if st in ("pending", "running"):
            n += 1
            if not dry_run:
                t["status"] = "cancelled"
                t["completed_at"] = now
                sm.upsert_task(t)
    return n


def _count_real_products(sm) -> tuple[int, int, list[str]]:
    """Returns (real_total, real_non_terminal, failed_ids)."""
    failed_ids: list[str] = []
    real_total = 0
    real_active = 0
    terminal = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "CANCELLED"})
    for p in sm.get_all_products():
        pid = str(p.get("id") or "")
        if _is_demo(pid):
            continue
        real_total += 1
        st = str(p.get("state") or "").upper()
        if st == "FAILED":
            failed_ids.append(pid)
        if st not in terminal:
            real_active += 1
    return real_total, real_active, failed_ids


def _enqueue_new_real(sm, *, need: int, dry_run: bool) -> list[str]:
    """Insert new products directly into SQLite (avoid JSON migrate clobbering reopened state)."""
    created: list[str] = []
    if need <= 0:
        return created
    pool = list(NEW_REAL_IDEAS)
    for i in range(need):
        profile, idea = pool[i % len(pool)]
        pid = f"prod-{uuid.uuid4().hex[:12]}"
        ts = time.time()
        product = {
            "id": pid,
            "idea": idea,
            "admin_instructions": DEFAULT_NOTES,
            "delivery_profile": profile,
            "production_mode": True,
            "category": "saas",
            "tags": ["operator-batch", "real-target"],
            "state": "IDEA_RECEIVED",
            "created_at": ts,
            "updated_at": ts,
            "metadata": {},
        }
        logger.info("CREATE %s (%s) %s…", pid, profile, idea[:60])
        if not dry_run:
            sm.upsert_product(product)
        created.append(pid)
    return created


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target-real", type=int, default=10, help="Target count of real products in pipeline")
    ap.add_argument("--notes", default=DEFAULT_NOTES)
    args = ap.parse_args()

    os.environ.setdefault("USE_SQLITE", "1")
    db = Path(os.environ.get("SQLITE_PATH", str(ROOT / "data/state/pipeline.db")))

    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.services.pipeline_reopen import reopen_failed_product

    sm = SQLiteManager(str(db))
    sm.connect()
    try:
        real_total, real_active, failed_ids = _count_real_products(sm)
        logger.info("Real products in DB: %s (non-terminal: %s), FAILED: %s", real_total, real_active, len(failed_ids))

        for pid in failed_ids:
            n = _cancel_stale_tasks(sm, pid, dry_run=args.dry_run)
            logger.info("%s: cancelled %s stale tasks before reopen", pid, n)
            if args.dry_run:
                logger.info("DRY reopen %s", pid)
                continue
            res = reopen_failed_product(pid, args.notes)
            if res.get("ok"):
                logger.info(
                    "REOPEN OK %s → state=%s agent=%s task=%s",
                    pid,
                    res.get("product_state"),
                    res.get("agent_type"),
                    res.get("task_id"),
                )
            else:
                logger.error("REOPEN FAIL %s: %s", pid, res)

        need = max(0, int(args.target_real) - real_total)
        if need:
            logger.info("Enqueueing %s new real product(s) to reach target %s", need, args.target_real)
            _enqueue_new_real(sm, need=need, dry_run=args.dry_run)
        else:
            logger.info("Already at or above target real count (%s >= %s)", real_total, args.target_real)

        # Summary
        real_total2, _, failed2 = _count_real_products(sm)
        completed = sum(
            1
            for p in sm.get_all_products()
            if not _is_demo(str(p.get("id") or ""))
            and str(p.get("state") or "").upper() in ("COMPLETED", "DEPLOYED_PRODUCTION")
        )
        logger.info("After: real=%s completed_real=%s failed_real=%s", real_total2, completed, len(failed2))
    finally:
        sm.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
