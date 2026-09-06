#!/usr/bin/env python3
"""Enqueue Relay (Verified Handoff Desk) and focus the factory on it only."""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELAY_IDEA = """Build **Relay** — a Verified Handoff Desk for teams that share AI-generated briefs with clients:
paste an AI draft, run a skeptic verification pass, approve or reject in an operator inbox,
then publish a branded public share link or embeddable widget. Visitors see the handoff text,
verification status, and what was human-approved — plus JSON receipt export for audit.
Core screens: operator login, handoff queue (pending/approved/rejected), create handoff form,
public `/share/{token}` page, and optional embed snippet. Product name in UI: **Relay**."""

ADMIN_INSTRUCTIONS = """Engineering charter — greenfield full_software (post-Sentinel), Vercel deploy required.

Stack:
- Python 3.12 + FastAPI backend, SQLite (`relay.db`), session auth for operators (Argon2/bcrypt).
- React + Vite SPA in `frontend/` (public share page + operator console routes).
- Ship for **Vercel fullstack**: `public/` dist + `api/index.py` ASGI mount; relative asset paths only.

Product flows (implement fully, not stubs):
1. Operator creates handoff from pasted AI text → backend stores draft + runs **verification** service
   (call external Metis verify HTTP if `METIS_VERIFY_URL` env set; else deterministic local skeptic
   heuristics with clear UI badge "local" vs "metis" — never fake success on HTTP errors).
2. Operator approves/rejects → status transitions + audit log row.
3. Public share page loads by token (no auth) with approved content only; 404 for draft/rejected.
4. Embed page or `/embed.js` snippet docs for third-party sites.
5. Export receipt JSON from operator UI.

Quality / gates:
- Distinct art direction: trust/notary metaphor — wax-seal accent, warm paper + deep ink palette;
  **not** another dark-glass-cyan AI clone. Architect: bold `ui_experience` + `svg_creative_brief`.
- `data-testid` on primary buttons; responsive; `prefers-reduced-motion`.
- Seed data: 1 operator account, 3 sample handoffs (pending/approved/rejected).
- README: local dev + Vercel notes. pytest for handoff state machine + token access rules.

Scope: richest vertical slice — queue + share + one verification path — over many empty screens."""


def main() -> int:
    from core.factory_hold import is_factory_on_hold
    from core.pipeline_product_pause import get_factory_focus_product_id
    from core.pipeline_state_writer import append_product_to_pipeline_state
    from core.pipeline_worker_notify import notify_pipeline_worker_wake
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics
    from web.backend.core.config import AppConfig
    from web.backend.services.pipeline_focus import apply_pipeline_focus_mode

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": RELAY_IDEA.strip(),
        "admin_instructions": ADMIN_INSTRUCTIONS.strip(),
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": "saas",
        "tags": ["owner-request", "relay", "vercel"],
        "on_demand": True,
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
            "source": "owner_relay_enqueue",
        },
    }

    if not append_product_to_pipeline_state(product):
        print("ERROR: append_product_to_pipeline_state failed", file=sys.stderr)
        return 1

    products = _load_pipeline_products_for_metrics()
    cfg = AppConfig()
    focus = apply_pipeline_focus_mode(
        cfg,
        focus_product_id=product_id,
        resume_factory=False,
        products=products,
    )
    notify_pipeline_worker_wake()

    print(
        json.dumps(
            {
                "product_id": product_id,
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
