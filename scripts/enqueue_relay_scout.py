#!/usr/bin/env python3
"""Enqueue Relay Scout ecosystem watchdog and focus the factory pipeline on it."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline_state_writer import append_product_to_pipeline_state
from core.pipeline_worker_notify import notify_pipeline_worker_wake
from llm.content_languages import product_locale_fields
from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
from web.backend.core.config import AppConfig
from web.backend.services.pipeline_focus import apply_pipeline_focus_mode

IDEA = (
    "Relay Scout — autonomous Python health watchdog for the alexar76 AIMarket ecosystem. "
    "Polls AI-Factory, Alien Monitor, DIOSCURI oracle, and AIMarket hub on a schedule; "
    "stores JSON snapshots; diffs changes; prints and optionally webhooks digest alerts when "
    "endpoints go offline or meaningful config drift is detected."
)

ADMIN = """
Build a shippable Python 3.12 CLI/service (full_software, NOT a marketing landing).

Stack: Typer CLI, httpx, pydantic-settings, APScheduler, rich for terminal output.
Ship: src package, pytest tests with httpx mocking, Dockerfile, docker-compose.yml,
README with operator runbook listing default alexar76 endpoints.

Scope:
- relay-scout watch — scheduled polling loop
- relay-scout check — one-shot health pass
- relay-scout diff — compare last two snapshots for a target
- Config via env + optional YAML (targets list: name, url, kind)

Default targets (configurable): magic-ai-factory.com health, monitor graph health,
DIOSCURI /health, hub health if reachable.

Do NOT embed Metis client calls in the shipped product — Metis is factory-only.
Include JSON schema for digest output and webhook payload.
Aim for COMPLETED with working tests and a minimal docker run path.
Category: DevTools. Interface locale: en. Content locale: auto.
""".strip()


def main() -> int:
    product_id = f"prod-relay-scout-{uuid.uuid4().hex[:8]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": IDEA,
        "admin_instructions": ADMIN,
        "delivery_profile": "full_software",
        "production_mode": False,
        **product_locale_fields(interface_locale="en", content_locale="auto"),
        "category": "devtools",
        "tags": ["ecosystem", "watchdog", "python", "relay-scout"],
        "domain_pack_override": "devtools_ops",
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
        "on_demand": True,
    }

    if not append_product_to_pipeline_state(product):
        print("ERROR: failed to append product", file=sys.stderr)
        return 1

    products = _load_pipeline_products_for_metrics()
    cfg = AppConfig()
    focus = apply_pipeline_focus_mode(
        cfg, focus_product_id=product_id, resume_factory=True, products=products
    )
    cfg.set("general.factory_on_hold", False)
    notify_pipeline_worker_wake()
    print(json.dumps({"product_id": product_id, "focus": focus}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
