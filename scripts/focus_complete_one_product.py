#!/usr/bin/env python3
"""Unpause factory, focus one near-complete product, wait for COMPLETED, pause again."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.factory_hold import is_factory_on_hold
from core.paths import pipeline_db_path
from core.pipeline_worker_notify import notify_pipeline_worker_wake
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.core.config import AppConfig
from web.backend.services.pipeline_focus import apply_pipeline_focus_mode
from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics

_TERMINAL = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"})
_LATE = {
    "QA_TESTING": 80,
    "DEV_FIXING": 70,
    "BUG_FOUND": 65,
    "EVOLUTION_ANALYZING": 60,
    "DEV_BUILDING": 50,
    "PM_SPEC": 40,
    "IDEA_RECEIVED": 10,
}


def _product_state(pid: str) -> dict | None:
    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            return None
        tasks = sm.get_tasks_by_product(pid)
        pending = sum(1 for t in tasks if str(t.get("status") or "").lower() == "pending")
        running = sum(1 for t in tasks if str(t.get("status") or "").lower() == "running")
        done = sum(1 for t in tasks if str(t.get("status") or "").lower() == "completed")
        return {
            "state": str(product.get("state") or "").upper(),
            "pending": pending,
            "running": running,
            "done": done,
            "total": len(tasks),
        }
    finally:
        sm.close()


def pick_closest_product(*, include_failed: bool = True) -> str | None:
    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        products = _load_pipeline_products_for_metrics()
        best_id: str | None = None
        best_score = -1.0
        for pid, product in products.items():
            state = str(product.get("state") or "").upper()
            if state in ("COMPLETED", "DEPLOYED_PRODUCTION", "CANCELLED"):
                continue
            if state == "FAILED" and not include_failed:
                continue
            tasks = sm.get_tasks_by_product(pid)
            total = len(tasks)
            done = sum(1 for t in tasks if str(t.get("status") or "").lower() == "completed")
            pct = (100.0 * done / total) if total else 0.0
            score = pct + _LATE.get(state, 30)
            if state == "FAILED":
                score += 5  # prefer revivable FAILED near the finish line
            if score > best_score:
                best_score = score
                best_id = str(pid)
        return best_id
    finally:
        sm.close()


def _reopen_if_failed(pid: str) -> bool:
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics

    product = _load_pipeline_products_for_metrics().get(pid)
    if not product or str(product.get("state") or "").upper() != "FAILED":
        return False
    from web.backend.services.pipeline_reopen import reopen_failed_product

    notes = (
        "Operator focus run: finish remaining pipeline work and reach COMPLETED. "
        "Pass QA / release gates; do not stop for non-blocking polish."
    )
    res = reopen_failed_product(pid, notes, agent_type="qa", target_state="QA_TESTING")
    print("reopen_failed=", json.dumps(res, ensure_ascii=False))
    return bool(res.get("ok"))


def pause_factory(cfg: AppConfig) -> None:
    apply_pipeline_focus_mode(cfg, focus_product_id=None, resume_factory=False)
    cfg.set("general.factory_on_hold", True)
    notify_pipeline_worker_wake()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", help="Pipeline product id (default: closest to COMPLETED)")
    parser.add_argument("--poll-sec", type=float, default=20.0)
    parser.add_argument("--timeout-sec", type=float, default=7200.0)
    args = parser.parse_args()

    pid = (args.product_id or "").strip() or pick_closest_product()
    if not pid:
        print("ERROR: no in-progress product found", file=sys.stderr)
        return 2

    cfg = AppConfig()
    print(f"product={pid}")
    print(f"factory_on_hold_before={is_factory_on_hold()}")

    products = _load_pipeline_products_for_metrics()
    if pid not in products:
        print(f"ERROR: unknown product {pid}", file=sys.stderr)
        return 2

    if _reopen_if_failed(pid):
        products = _load_pipeline_products_for_metrics()
        notify_pipeline_worker_wake()
        time.sleep(5)
    focus = apply_pipeline_focus_mode(cfg, focus_product_id=pid, resume_factory=True, products=products)
    print("focus_mode=", json.dumps(focus, ensure_ascii=False))
    print(f"factory_on_hold_running={is_factory_on_hold()}")
    notify_pipeline_worker_wake()

    deadline = time.time() + float(args.timeout_sec)
    last_line = ""
    while time.time() < deadline:
        st = _product_state(pid)
        if st is None:
            print("ERROR: product missing", file=sys.stderr)
            pause_factory(cfg)
            return 2
        line = (
            f"state={st['state']} tasks={st['done']}/{st['total']} "
            f"pending={st['pending']} running={st['running']}"
        )
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if st["state"] in ("COMPLETED", "DEPLOYED_PRODUCTION"):
            print(f"SUCCESS {st['state']}")
            pause_factory(cfg)
            print(f"factory_on_hold_after={is_factory_on_hold()}")
            return 0
        if st["state"] == "FAILED":
            print("FAILED", file=sys.stderr)
            pause_factory(cfg)
            return 1
        notify_pipeline_worker_wake()
        time.sleep(float(args.poll_sec))

    print("TIMEOUT", file=sys.stderr)
    pause_factory(cfg)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
