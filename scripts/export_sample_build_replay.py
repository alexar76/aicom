#!/usr/bin/env python3
"""Export a deterministic public build-replay JSON for docs/sample-output/."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "sample-output" / "build-replay-spliteasy.json"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    tmp = ROOT / "docs" / "sample-output" / ".tmp-replay-seed"
    tmp.mkdir(parents=True, exist_ok=True)

    import os

    os.environ["AIFACTORY_DATA_ROOT"] = str(tmp)
    os.environ["SQLITE_PATH"] = str(tmp / "pipeline.db")

    from core.paths import pipeline_db_path
    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.services.build_replay import get_build_replay

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    now = time.time()
    sm.upsert_product(
        {
            "id": "sample-spliteasy",
            "idea": "A tool to split bills with friends",
            "state": "COMPLETED",
            "created_at": now - 3000,
            "updated_at": now,
            "metadata": {"category": "saas", "spec": {"product_name": "SplitEasy"}},
        }
    )
    sm.upsert_task(
        {
            "id": "t1",
            "product_id": "sample-spliteasy",
            "agent_type": "analyst",
            "status": "COMPLETED",
            "state": "market_researched",
            "created_at": now - 3000,
            "started_at": now - 2990,
            "completed_at": now - 2900,
            "output_data": {"verdict": "go", "score": 0.91, "category": "saas"},
        }
    )
    sm.upsert_task(
        {
            "id": "t2",
            "product_id": "sample-spliteasy",
            "agent_type": "developer",
            "status": "COMPLETED",
            "state": "code_committed",
            "created_at": now - 2800,
            "started_at": now - 2700,
            "completed_at": now - 1800,
            "retry_count": 1,
            "output_data": {"files_written": 7, "tech_stack_label": "Next.js + FastAPI"},
        }
    )
    sm.upsert_task(
        {
            "id": "t3",
            "product_id": "sample-spliteasy",
            "agent_type": "landing_developer",
            "status": "COMPLETED",
            "state": "code_committed",
            "created_at": now - 1700,
            "started_at": now - 1700,
            "completed_at": now - 1600,
            "output_data": {"files_written": 3},
        }
    )
    sm.upsert_task(
        {
            "id": "t4",
            "product_id": "sample-spliteasy",
            "agent_type": "security",
            "status": "COMPLETED",
            "state": "security_scanned",
            "created_at": now - 1500,
            "started_at": now - 1400,
            "completed_at": now - 1200,
            "output_data": {"findings_count": 0, "passed": True},
        }
    )

    replay = get_build_replay("sample-spliteasy")
    if not replay:
        print("get_build_replay returned empty", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
