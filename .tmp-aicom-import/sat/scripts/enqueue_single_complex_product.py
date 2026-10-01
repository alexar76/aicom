#!/usr/bin/env python3
"""
Enqueue exactly one pipeline product (same shape as Admin → create product).

Writes ``data/state/pipeline.json`` and runs JSON→SQLite migrate so USE_SQLITE=1
workers pick it up.

Usage (host, repo root):
  python3 scripts/enqueue_single_complex_product.py

Docker:
  docker compose exec -T app python /app/scripts/enqueue_single_complex_product.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMPLEX_IDEA = """Build **FleetMind Ops** — a multi-tenant SaaS for small logistics teams:
live shipment map (WebSockets), driver mobile checklist (PWA-friendly), SLA alerts,
role-based admin (owner / dispatcher / driver), CSV import, and a minimal billing
stub (plan tiers stored in SQLite + mock Stripe webhook). Must ship a working
**FastAPI + Jinja + HTMX** web UI with auth sessions, plus OpenAPI docs at /docs.
Include seed data for 2 tenants, 6 drivers, 40 shipments. Dark theme UI, accessible
forms, and Playwright-friendly `data-testid` hooks."""

ADMIN_INSTRUCTIONS = """Engineering charter (demo run):
- Stack: Python 3.12, FastAPI, SQLite, server-rendered pages + HTMX; no SPA framework.
- Security: CSRF on mutating routes, Argon2 password hashing, rate-limit login.
- Quality: type hints, pytest for services, ruff-clean; README with `uvicorn` run.
- Delivery profile: **full_software** — browser-runnable MVP under sandbox iframe rules
  (relative URLs only in shipped HTML).
Ship the richest vertical slice you can within the pipeline budget; prefer fewer
screens done well over many stubs."""


def main() -> int:
    from orchestrator.migrate import migrate

    try:
        from core.paths import pipeline_db_path, pipeline_json_path
    except ImportError:
        print("Run from repo root so package `core` resolves.", file=sys.stderr)
        return 1

    state_file = pipeline_json_path()
    db_path = pipeline_db_path()

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": COMPLEX_IDEA.strip(),
        "admin_instructions": ADMIN_INSTRUCTIONS.strip(),
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": "saas",
        "tags": [],
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "metadata": {
            "delivery_profile": "full_software",
            "category": "saas",
        },
    }

    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        state = {"products": {}, "task_queue": [], "current_task_id": None}
    state.setdefault("products", {})
    state.setdefault("task_queue", [])
    state["products"][product_id] = product

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote product {product_id} to {state_file}")

    migrate(json_path=str(state_file), db_path=str(db_path))
    print(f"Synced to SQLite {db_path}")
    print("Open Admin → Pipeline Monitor to watch stages; ensure the pipeline worker is running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
