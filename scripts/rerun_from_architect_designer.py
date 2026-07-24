#!/usr/bin/env python3
"""
Re-queue every product that already has a PM spec so the pipeline runs Architect again
(with ui_experience / designer handoff) and then continues Developer → QA → …

This does NOT re-run Analyst or PM: existing specification.json on disk is kept.

What it does per matching product:
  - Sets product.state to MARKET_CONTENT_READY
  - Removes ALL tasks for that product_id from task_queue (clean slate for this rerun)
  - Appends one pending architect task (target state ARCH_DESIGNED)
  - Deletes data/arch/<product_id>/architecture.json so the Architect regenerates fresh output

After editing pipeline.json, syncs SQLite when USE_SQLITE=1 (same path as policy_audit).

Usage (repo root, data under ./data):
  python3 scripts/rerun_from_architect_designer.py --dry-run
  python3 scripts/rerun_from_architect_designer.py

Inside Docker:
  docker compose exec app python3 /app/scripts/rerun_from_architect_designer.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rerun-architect")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _has_spec(data_root: Path, product_id: str) -> bool:
    p = data_root / "specs" / product_id / "specification.json"
    return p.is_file()


def _sync_sqlite() -> None:
    if not _truthy("USE_SQLITE", "0"):
        return
    try:
        from web.backend.services.policy_audit import sync_sqlite_from_pipeline_json

        sync_sqlite_from_pipeline_json()
        logger.info("SQLite synced from pipeline.json")
    except Exception as e:
        logger.exception("SQLite sync failed: %s", e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-queue Architect+downstream for all products with a spec")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument(
        "--data-root",
        default=os.environ.get("AIFACTORY_DATA_ROOT", str(ROOT / "data")),
        type=Path,
        help="Data directory (default: AIFACTORY_DATA_ROOT or ./data)",
    )
    ap.add_argument(
        "--wipe-code",
        action="store_true",
        help="Also delete data/code/<id> before rerun (full regen of deliverables)",
    )
    args = ap.parse_args()

    data_root: Path = args.data_root
    json_path = Path(os.environ.get("PIPELINE_JSON", data_root / "state" / "pipeline.json"))
    if not json_path.is_file():
        logger.error("Pipeline state not found: %s", json_path)
        return 1

    state = json.loads(json_path.read_text(encoding="utf-8"))
    products: dict = state.get("products") or {}
    task_queue: list = state.get("task_queue") or []

    targets: list[str] = []
    for pid, product in products.items():
        if not isinstance(product, dict):
            continue
        if not _has_spec(data_root, pid):
            logger.info("skip %s (no specification.json)", pid)
            continue
        targets.append(pid)

    if not targets:
        logger.warning("No products with specs found — nothing to do.")
        return 0

    logger.info("Will rerun Architect→… for %s product(s): %s", len(targets), ", ".join(targets[:20]) + (" …" if len(targets) > 20 else ""))

    if args.dry_run:
        for pid in targets:
            arch = data_root / "arch" / pid / "architecture.json"
            logger.info("[dry-run] %s: state→METHODOLOGY_REVIEWED, drop tasks, queue architect, rm %s", pid, arch)
        return 0

    now = time.time()
    new_queue = [t for t in task_queue if t.get("product_id") not in targets]

    for pid in targets:
        product = products[pid]
        product["state"] = "METHODOLOGY_REVIEWED"
        product["updated_at"] = now
        product["quality_repair_round"] = 0
        product.pop("failure_reason", None)

        arch_file = data_root / "arch" / pid / "architecture.json"
        if arch_file.is_file():
            try:
                arch_file.unlink()
                logger.info("removed %s", arch_file)
            except OSError as e:
                logger.warning("could not remove %s: %s", arch_file, e)

        if args.wipe_code:
            code_dir = data_root / "code" / pid
            if code_dir.is_dir():
                shutil.rmtree(code_dir, ignore_errors=True)
                logger.info("removed tree %s", code_dir)

        task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "product_id": pid,
            "agent_type": "architect",
            "state": "ARCH_DESIGNED",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {
                "product_id": pid,
                "idea": product.get("idea", ""),
            },
            "created_at": now,
            "priority": 5,
        }
        new_queue.append(task)
        logger.info("queued architect for %s", pid)

    state["products"] = products
    state["task_queue"] = new_queue
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    logger.info("Wrote %s", json_path)

    _sync_sqlite()
    logger.info("Done. Ensure pipeline-worker is running to process architect tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
