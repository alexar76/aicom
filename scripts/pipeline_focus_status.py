#!/usr/bin/env python3
"""Pipeline focus mode status — safe CLI (no curl | python heredoc pitfalls)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")


def _load_local_status() -> dict:
    from core.config_merge import load_merged_config
    from core.paths import config_path, pipeline_db_path
    from core.pipeline_product_pause import get_factory_focus_product_id
    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
    from web.backend.services.pipeline_focus import focus_mode_status
    from web.backend.services.product_followup import read_followup

    cfg = load_merged_config(config_path())
    status = focus_mode_status(config=cfg)
    focus_id = get_factory_focus_product_id(config=cfg)
    products = _load_pipeline_products_for_metrics()

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        pending_by_pid, running_by_pid = sm.get_active_task_counts_by_product()
    finally:
        sm.close()

    terminal = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"})

    focus_detail = None
    if focus_id and focus_id in products:
        p = products[focus_id]
        spec = p.get("spec") or {}
        if isinstance(spec, str):
            spec = {}
        fu = read_followup(focus_id) or {}
        focus_detail = {
            "id": focus_id,
            "state": p.get("state"),
            "delivery_profile": p.get("delivery_profile")
            or (spec.get("delivery_profile") if isinstance(spec, dict) else None),
            "quality_repair_round": p.get("quality_repair_round"),
            "pipeline_on_hold": bool(fu.get("pipeline_on_hold")),
            "running_tasks": running_by_pid.get(focus_id, 0),
            "pending_tasks": pending_by_pid.get(focus_id, 0),
        }

    not_held = []
    for pid, p in products.items():
        if pid == focus_id:
            continue
        fu = read_followup(pid) or {}
        if not fu.get("pipeline_on_hold") and str(p.get("state") or "").upper() not in terminal:
            not_held.append(pid)

    general = cfg.get("general") if isinstance(cfg.get("general"), dict) else {}
    return {
        **status,
        "factory_on_hold": bool(general.get("factory_on_hold", False)),
        "focus_product": focus_detail,
        "products_without_hold_flag": not_held,
        "ui_location": "/admin?tab=pipeline (panel «Режим фокуса» at top of Pipeline tab)",
    }


def _load_api_status(base_url: str, token: str) -> dict:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _get(path: str) -> dict:
        req = urllib.request.Request(f"{base}{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        if not raw.strip():
            raise ValueError(f"Empty response from {path}")
        return json.loads(raw)

    focus = _get("/api/admin/pipeline/focus-mode")
    settings = _get("/api/admin/settings")
    products_resp = _get("/api/admin/pipeline/products?limit=100&light=1")
    products = products_resp.get("products") or []

    focus_row = next((p for p in products if p.get("pipeline_focus_active")), None)
    focus_detail = None
    if focus_row:
        tc = focus_row.get("task_counts") or {}
        sf = focus_row.get("storefront_followup") or {}
        spec = focus_row.get("spec") or {}
        focus_detail = {
            "id": focus_row.get("id"),
            "state": focus_row.get("state"),
            "delivery_profile": focus_row.get("delivery_profile")
            or (spec.get("delivery_profile") if isinstance(spec, dict) else None),
            "quality_repair_round": focus_row.get("quality_repair_round"),
            "pipeline_on_hold": bool(sf.get("pipeline_on_hold")),
            "running_tasks": int(tc.get("running") or 0),
            "pending_tasks": int(tc.get("pending") or 0),
        }

    terminal = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"})
    not_held = [
        p.get("id")
        for p in products
        if not p.get("pipeline_focus_active")
        and not (p.get("storefront_followup") or {}).get("pipeline_on_hold")
        and str(p.get("state") or "").upper() not in terminal
    ]

    return {
        **focus,
        "factory_on_hold": bool(settings.get("factory_on_hold")),
        "focus_product": focus_detail,
        "products_without_hold_flag": [x for x in not_held if x],
        "ui_location": "/admin?tab=pipeline (panel «Режим фокуса» at top of Pipeline tab)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        help="Fetch via HTTP (e.g. http://127.0.0.1:9081). Requires --token or AICOM_ADMIN_TOKEN.",
    )
    parser.add_argument("--token", help="Admin bearer token (or env AICOM_ADMIN_TOKEN).")
    parser.add_argument("--human", action="store_true", help="Print human-readable summary to stderr.")
    args = parser.parse_args()

    try:
        if args.api_url:
            import os

            token = args.token or os.environ.get("AICOM_ADMIN_TOKEN", "").strip()
            if not token:
                print("error: --api-url requires --token or AICOM_ADMIN_TOKEN", file=sys.stderr)
                return 2
            report = _load_api_status(args.api_url, token)
        else:
            report = _load_local_status()
    except (urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.human:
        fp = report.get("focus_product") or {}
        print(
            f"\nFocus: {report.get('focus_product_id') or '—'} | "
            f"active={report.get('active_count')} paused={report.get('paused_count')} "
            f"total={report.get('total_products')} | factory_on_hold={report.get('factory_on_hold')}",
            file=sys.stderr,
        )
        if fp:
            print(
                f"  state={fp.get('state')} running_tasks={fp.get('running_tasks')} "
                f"pending_tasks={fp.get('pending_tasks')}",
                file=sys.stderr,
            )
        print(f"  UI: {report.get('ui_location')}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
