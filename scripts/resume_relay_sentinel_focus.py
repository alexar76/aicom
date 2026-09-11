#!/usr/bin/env python3
"""Raise LLM cap, reopen Relay + Sentinel for developer rework, focus factory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELAY_PID = "prod-e1a3b0abf16a"
SENTINEL_PID = "prod-bdb1634806de"
FOCUS_PID = RELAY_PID

RELAY_NOTES = """Production UI audit (Aug 2026): public /share/{token} returns 500 — PublicReadOut schema mismatch; receipt.json and embed-snippet return 500 (UUID JSON + HandoffOut coercion); SPA routes /handoffs/{id}, /branding, /embed render empty. Fix backend schemas/routers and React operator routes. Ship Vercel redeploy with passing QA on share + receipt + embed."""

SENTINEL_NOTES = """Resume from FAILED: LLM cap tripped at $20; close mesh/auth QA gates, invoke aimarket_participant capability (not constants-only), dedupe duplicate_modules, add toast UX feedback, refresh live_gate after auth fix. Permissions on VPS code tree are writable now."""


def _bump_llm_cap(target_usd: float = 40.0) -> dict:
    os.environ["AIFACTORY_MAX_PIPELINE_COST_USD"] = str(target_usd)
    overlay = Path(os.environ.get("AICOM_DATA", "/app/data")) / "config" / "admin_config_overlay.yaml"
    text = ""
    if overlay.is_file():
        text = overlay.read_text(encoding="utf-8")
    key = "max_pipeline_cost_usd:"
    line = f"  max_pipeline_cost_usd: {target_usd}"
    if key in text:
        import re

        text = re.sub(r"^\s*max_pipeline_cost_usd:\s*[\d.]+", line, text, count=1, flags=re.M)
    else:
        if "quality:" in text:
            text = text.replace("quality:\n", f"quality:\n{line}\n", 1)
        else:
            text = (text.rstrip() + f"\n\nquality:\n{line}\n").lstrip()
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(text, encoding="utf-8")
    try:
        from core.quality_settings import bump_quality_cache_after_config_write

        bump_quality_cache_after_config_write()
    except Exception:
        pass
    from core.quality_settings import max_pipeline_cost_usd

    return {"overlay": str(overlay), "effective_cap_usd": max_pipeline_cost_usd()}


def main() -> int:
    from core.factory_hold import is_factory_on_hold
    from core.pipeline_product_pause import get_factory_focus_product_id
    from core.pipeline_worker_notify import notify_pipeline_worker_wake
    from core.paths import code_dir
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
    from web.backend.core.config import AppConfig
    from web.backend.services.pipeline_focus import apply_pipeline_focus_mode
    from web.backend.services.pipeline_reopen import reopen_product_for_rework
    from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix

    cap = _bump_llm_cap(40.0)

    for pid in (RELAY_PID, SENTINEL_PID):
        try:
            apply_visual_gate_autofix(code_dir(pid))
        except Exception as exc:
            print(f"WARN visual_gate_autofix {pid}: {exc}", file=sys.stderr)

    relay = reopen_product_for_rework(RELAY_PID, RELAY_NOTES, agent_type="developer")
    sentinel = reopen_product_for_rework(SENTINEL_PID, SENTINEL_NOTES, agent_type="developer")

    if not relay.get("ok"):
        print(json.dumps({"ok": False, "relay": relay}, indent=2, ensure_ascii=False))
        return 1
    if not sentinel.get("ok"):
        print(json.dumps({"ok": False, "sentinel": sentinel}, indent=2, ensure_ascii=False))
        return 1

    products = _load_pipeline_products_for_metrics()
    cfg = AppConfig()
    focus = apply_pipeline_focus_mode(
        cfg,
        focus_product_id=FOCUS_PID,
        resume_factory=False,
        products=products,
    )
    notify_pipeline_worker_wake()

    print(
        json.dumps(
            {
                "ok": True,
                "llm_cap": cap,
                "relay": relay,
                "sentinel": sentinel,
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
