#!/usr/bin/env python3
"""Create minimal SQLite + empty data root for isolated 3-stack benchmark."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_schema_src = (ROOT / "orchestrator" / "schema.py").read_text(encoding="utf-8")
_m = re.search(r'SQLITE_SCHEMA\s*=\s*"""(.*?)"""', _schema_src, re.DOTALL)
if not _m:
    raise RuntimeError("Could not parse SQLITE_SCHEMA")
SQLITE_SCHEMA = _m.group(1)

PRODUCTS: list[tuple[str, str, str]] = [
    (
        "stack-fastapi",
        "iot",
        """[FACTORY_ADMIN_STACK_CHARTER — Python]
Primary API MUST be Python 3.11+ with FastAPI; persistence SQLite or PostgreSQL; JWT auth for API routes.
Ship Dockerfile or docker-compose for API + browser demo (relative URLs only for iframe sandbox).

Product: FleetPulse IoT — dashboard for facility managers: live device grid (battery %, last MQTT ping, RSSI), filters by site/building, drill-down with raw telemetry JSON and alert timeline. REST CRUD for devices and sites; WebSocket or SSE for live metric pushes.""",
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


def main() -> None:
    bench_root = Path(os.environ.get("STACKBENCH_ROOT", "/tmp/stackbench_data"))
    db_path = Path(os.environ.get("STACKBENCH_SQLITE", "/tmp/stackbench.db"))

    for sub in (
        "state",
        "specs",
        "arch",
        "code",
        "logs",
        "sandboxes",
        "reports",
        "bugs",
        "telemetry",
    ):
        (bench_root / sub).mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SQLITE_SCHEMA)
    ws = "default"
    ts = time.time()
    for prefix, category, idea in PRODUCTS:
        pid = f"prod-{prefix}-{uuid.uuid4().hex[:10]}"
        conn.execute(
            """INSERT INTO products
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
                json.dumps(["stackbench", prefix]),
                category,
                None,
                json.dumps([]),
                None,
                None,
            ),
        )
        print(pid)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
