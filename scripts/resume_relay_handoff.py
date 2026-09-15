#!/usr/bin/env python3
"""Reopen Relay (Verified Handoff Desk) from FAILED, focus factory, queue QA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELAY_PID = "prod-e1a3b0abf16a"
NOTES = (
    "Factory reopen: spa dist accepts Vercel public/; policy_audit no longer "
    "terminal-FAILED; LLM test-hygiene findings dropped; repair budget reset. "
    "Re-run QA only — do not rewrite product charter."
)


def main() -> int:
    from core.factory_hold import is_factory_on_hold
    from core.pipeline_product_pause import get_factory_focus_product_id
    from core.pipeline_worker_notify import notify_pipeline_worker_wake
    from core.paths import code_dir
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
    from web.backend.core.config import AppConfig
    from web.backend.services.pipeline_focus import apply_pipeline_focus_mode
    from web.backend.services.pipeline_reopen import reopen_failed_product
    from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix

    try:
        apply_visual_gate_autofix(code_dir(RELAY_PID))
    except Exception as exc:
        print(f"WARN visual_gate_autofix: {exc}", file=sys.stderr)

    reopen = reopen_failed_product(
        RELAY_PID,
        NOTES,
        agent_type="qa",
        target_state="QA_TESTING",
    )
    if not reopen.get("ok"):
        print(json.dumps({"ok": False, "reopen": reopen}, indent=2, ensure_ascii=False))
        return 1

    products = _load_pipeline_products_for_metrics()
    cfg = AppConfig()
    focus = apply_pipeline_focus_mode(
        cfg,
        focus_product_id=RELAY_PID,
        resume_factory=False,
        products=products,
    )
    notify_pipeline_worker_wake()

    print(
        json.dumps(
            {
                "ok": True,
                "product_id": RELAY_PID,
                "reopen": reopen,
                "factory_on_hold": is_factory_on_hold(),
                "focus_product_id": get_factory_focus_product_id(),
                "paused_count": focus.get("paused_count"),
                "active_count": focus.get("active_count"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
