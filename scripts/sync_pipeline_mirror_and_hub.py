#!/usr/bin/env python3
"""
Mirror SQLite pipeline → pipeline.json, seed demo SKUs, list shipped products on AIMarket Hub.

  PYTHONPATH=.:aimarket-hub python3 scripts/sync_pipeline_mirror_and_hub.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "aimarket-hub") not in sys.path:
    sys.path.insert(0, str(ROOT / "aimarket-hub"))

DATA = ROOT / "data"
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("SQLITE_PATH", str(DATA / "state" / "pipeline.db"))
os.environ.setdefault("AIFACTORY_DATA_ROOT", str(DATA))
os.environ.setdefault("AIMARKET_DB_PATH", str(DATA / "hub" / "hub.db"))


def mirror_pipeline_json() -> int:
    import json
    import sqlite3

    from aimarket_hub.factory_products_loader import _read_products_from_sqlite
    from core.paths import pipeline_json_path

    products = _read_products_from_sqlite()
    out = pipeline_json_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    prev: dict = {}
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}
    tasks = prev.get("task_queue") if isinstance(prev.get("task_queue"), list) else []
    current_task_id = prev.get("current_task_id")
    payload = {"products": products, "task_queue": tasks, "current_task_id": current_task_id}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK mirrored {len(products)} products → {out}")
    return len(products)


def seed_demos(*, skip_ids: frozenset[str]) -> int:
    from scripts.seed_marketplace_demo import DEMO_PRODUCTS, seed_product_files_sqlite

    count = 0
    for cfg in DEMO_PRODUCTS:
        pid = cfg["id"]
        if pid in skip_ids:
            print(f"SKIP seed {pid} (kept custom preview)")
            continue
        seed_product_files_sqlite(cfg, data_root=DATA)
        print(f"OK seeded {pid}")
        count += 1
    return count


def refresh_lensline() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "refresh_landing_studio_preview.py")],
        check=True,
        cwd=str(ROOT),
    )


def list_on_hub() -> None:
    from aimarket_hub.auto_listing import auto_list_product
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.factory_bridge import import_factory_products
    from aimarket_hub.factory_products_loader import iter_shipped_factory_products
    from core.paths import pipeline_json_path

    db = HubDatabase(os.environ["AIMARKET_DB_PATH"])
    shipped = iter_shipped_factory_products(pipeline_json_path())
    print(f"Shipped products for hub: {len(shipped)}")
    for pid in sorted(shipped):
        res = auto_list_product(pid, db, pipeline_path=str(pipeline_json_path()))
        caps = res.get("listed_capabilities") or []
        errs = res.get("errors") or []
        if caps:
            print(f"  LIST {pid}: {len(caps)} cap(s)")
        elif errs:
            print(f"  FAIL {pid}: {errs[0]}")
    total = import_factory_products(db, pipeline_json_path=str(pipeline_json_path()))
    print(f"OK import_factory_products upserted {total} capability row(s)")
    local = [c for c in db.list_capabilities("local", limit=500) if not c.capability_id.startswith("translate.")]
    print(f"Local factory caps (excl. translate seed): {len(local)}")
    for c in local[:25]:
        if c.product_id.startswith("prod-"):
            print(f"  {c.capability_id} ← {c.product_id}")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Mirror factory pipeline and sync hub catalog")
    ap.add_argument(
        "--mirror-only",
        action="store_true",
        help="Only mirror SQLite → pipeline.json (no demo seed / hub import)",
    )
    ap.add_argument(
        "--hub-import-only",
        action="store_true",
        help="Mirror + import into AIMARKET_DB_PATH (skip demo seed / lensline)",
    )
    args = ap.parse_args()

    if args.mirror_only:
        mirror_pipeline_json()
        return 0
    if args.hub_import_only:
        mirror_pipeline_json()
        list_on_hub()
        return 0

    refresh_lensline()
    seed_demos(skip_ids=frozenset({"prod-demo-landing-studio"}))
    mirror_pipeline_json()
    list_on_hub()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
