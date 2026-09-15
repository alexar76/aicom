#!/usr/bin/env python3
"""Clear Sentinel hold/lock, reopen for developer rework, focus factory on Sentinel only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SENTINEL_PID = "prod-bdb1634806de"

SENTINEL_NOTES = """Operator reopen: GitHub house packaging. README must have working docs/badges/*.svg on disk, docs/gallery/hero.svg + embedded gallery images (not bare paths), docs/admin.md, docs/user-guide.md, docs/use-cases.md, and README Docs links to all three. Keep AtlasClient → get_participant().invoke mesh wiring; do not replace advisory with static placeholder. Live Vercel advisory must leave UNKNOWN when escrow is funded (≥$1 USDC). Prefer mesh invoke + toast UX; do not salvage-revert advisory.py / atlas_client.py / aimarket_participant.py."""


def main() -> int:
    from core.factory_hold import is_factory_on_hold
    from core.pipeline_product_pause import get_factory_focus_product_id
    from core.pipeline_worker_notify import notify_pipeline_worker_wake
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
    from web.backend.core.config import AppConfig
    from web.backend.services.pipeline_focus import apply_pipeline_focus_mode
    from web.backend.services.pipeline_reopen import reopen_product_for_rework
    from web.backend.services.product_followup import (
        is_product_pipeline_on_hold,
        set_product_improvement_on_hold,
        set_product_pipeline_on_hold,
    )

    set_product_pipeline_on_hold(SENTINEL_PID, False)
    set_product_improvement_on_hold(SENTINEL_PID, False)

    # So a race with idle-heal still carries operator intent (heal tasks copy product charter).
    try:
        from orchestrator.sqlite_manager import SQLiteManager
        from core.paths import pipeline_db_path

        sm = SQLiteManager(str(pipeline_db_path()))
        sm.connect()
        product = sm.get_product(SENTINEL_PID)
        if product:
            product["admin_instructions"] = SENTINEL_NOTES
            product["operator_locked"] = False
            product.pop("operator_locked_at", None)
            meta = dict(product.get("metadata") or {})
            meta.pop("operator_locked", None)
            meta.pop("operator_locked_at", None)
            product["metadata"] = meta
            sm.upsert_product(product)
        sm.close()
    except Exception as exc:
        print(f"WARN preseed admin_instructions: {exc}", file=sys.stderr)

    sentinel = reopen_product_for_rework(SENTINEL_PID, SENTINEL_NOTES, agent_type="developer")
    if not sentinel.get("ok"):
        print(json.dumps({"ok": False, "sentinel": sentinel}, indent=2, ensure_ascii=False))
        return 1

    products = _load_pipeline_products_for_metrics()
    cfg = AppConfig()
    focus = apply_pipeline_focus_mode(
        cfg,
        focus_product_id=SENTINEL_PID,
        resume_factory=True,
        products=products,
    )
    notify_pipeline_worker_wake()

    print(
        json.dumps(
            {
                "ok": True,
                "sentinel": sentinel,
                "pipeline_on_hold": is_product_pipeline_on_hold(SENTINEL_PID),
                "focus_product_id": get_factory_focus_product_id(),
                "factory_on_hold": is_factory_on_hold(),
                "paused_count": focus.get("paused_count"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
