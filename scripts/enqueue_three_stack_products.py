#!/usr/bin/env python3
"""
Enqueue three full_software-style products with fixed backend stacks.
Uses sqlite3 only (avoids importing orchestrator package → prometheus).

  AIFACTORY_DATA_ROOT=... SQLITE_PATH=... python scripts/enqueue_three_stack_products.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import uuid

PRODUCTS: list[tuple[str, str, str]] = [
    (
        "stack-fastapi",
        "iot",
        """[FACTORY_ADMIN_STACK_CHARTER — Python]
Primary API MUST be Python 3.11+ with FastAPI; persistence SQLite or PostgreSQL; JWT auth for API routes.
Ship docker-compose or Dockerfile for API + browser demo shell (relative URLs only for iframe sandbox).

Product: FleetPulse IoT — dashboard for facility managers: live device grid (battery %, last MQTT ping, RSSI), filters by site/building, drill-down panel with raw telemetry JSON and alert timeline. REST CRUD for devices and sites; WebSocket or SSE for live metric pushes.""",
    ),
    (
        "stack-nestjs",
        "saas",
        """[FACTORY_ADMIN_STACK_CHARTER — Node]
Primary API MUST be NestJS (TypeScript) with modular controllers/services; TypeORM or Prisma with SQLite for demo.

Product: BenchNest SaaS — micro CRM for freelance squads: contacts, deals pipeline kanban, tasks per deal, team invites (stub OAuth OK). JSON REST API under /api; static/HTML dashboard calling relative ./api paths.""",
    ),
    (
        "stack-dotnet",
        "devtools",
        """[FACTORY_ADMIN_STACK_CHARTER — .NET]
Primary API MUST be C# ASP.NET Core 8 Minimal APIs or Web API; EF Core with SQLite for demo; Swagger/OpenAPI enabled.

Product: TraceRelay DevTools — webhook inbox for developers: register endpoints, capture inbound HTTP payloads (headers+body), searchable list, replay to secondary URL (stub). Browser UI + backend under relative paths for sandbox.""",
    ),
]


def _pid(prefix: str) -> str:
    return f"prod-{prefix}-{uuid.uuid4().hex[:10]}"


def main() -> None:
    db_path = os.environ.get("SQLITE_PATH", "")
    if not db_path or not os.path.isfile(db_path):
        print("SQLITE_PATH must point to an existing pipeline.db", file=sys.stderr)
        sys.exit(1)

    ws = os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"
    conn = sqlite3.connect(db_path)
    ts = time.time()
    try:
        for prefix, category, idea in PRODUCTS:
            pid = _pid(prefix)
            conn.execute(
                """INSERT OR REPLACE INTO products
                   (id, workspace_id, idea, state, created_at, updated_at,
                    spec, architecture, tags, category,
                    monetization_scheme, evolution_history, error, current_task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    ws,
                    idea,
                    "IDEA_RECEIVED",
                    ts,
                    ts,
                    None,
                    None,
                    json.dumps(["stack-benchmark", prefix]),
                    category,
                    None,
                    json.dumps([]),
                    None,
                    None,
                ),
            )
            print(pid)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
