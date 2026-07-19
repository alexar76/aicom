"""Slim landing-only pipeline (mini-spec → architect → developer → QA)."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LANDING_FAST_JSON = Path(__file__).resolve().parents[1] / "config" / "pipeline_flow_landing_fast.json"


@lru_cache(maxsize=1)
def landing_fast_agent_flow() -> dict[str, tuple[str, str]]:
    raw = json.loads(_LANDING_FAST_JSON.read_text(encoding="utf-8"))
    flow_raw = raw.get("agent_flow") or {}
    out: dict[str, tuple[str, str]] = {}
    for state, pair in flow_raw.items():
        if isinstance(pair, list) and len(pair) == 2:
            out[str(state)] = (str(pair[0]), str(pair[1]))
    return out


def is_landing_fast_product(product: dict[str, Any] | None) -> bool:
    return bool(product and product.get("landing_fast_path"))


def agent_flow_for_product(product: dict[str, Any]) -> dict[str, tuple[str, str]]:
    if is_landing_fast_product(product):
        return landing_fast_agent_flow()
    from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW

    return PIPELINE_AGENT_FLOW


def resolve_style_preset(
    preset_id: str | None,
    *,
    product_id: str,
    idea: str,
) -> dict[str, str]:
    from web.backend.services.reference_templates import load_style_presets

    presets = load_style_presets()
    if not presets:
        return {
            "id": "aurora-glass",
            "title": "Aurora glassmorphism",
            "neural_prompt": "Frosted glass panels with flowing aurora gradients.",
        }
    if preset_id:
        for preset in presets:
            if str(preset.get("id") or "") == preset_id:
                return {
                    "id": str(preset.get("id") or ""),
                    "title": str(preset.get("title") or preset.get("id") or ""),
                    "neural_prompt": str(preset.get("neural_prompt") or ""),
                }
    # SECURITY: use hashlib instead of hash() — Python's hash() is randomised
    # per process (PYTHONHASHSEED), so the same product/idea would pick different
    # style presets across worker restarts, breaking reproducibility.
    idx = int(
        hashlib.md5(f"{product_id}:{idea}".encode(), usedforsecurity=False).hexdigest(), 16
    ) % len(presets)
    chosen = presets[idx]
    return {
        "id": str(chosen.get("id") or ""),
        "title": str(chosen.get("title") or chosen.get("id") or ""),
        "neural_prompt": str(chosen.get("neural_prompt") or ""),
    }


def write_landing_mini_spec(
    product_id: str,
    *,
    idea: str,
    preset: dict[str, str],
    data_root: Path,
    admin_instructions: str = "",
    agent_to_website: bool = False,
) -> dict[str, Any]:
    """Programmatic marketing landing spec — no LLM round-trip."""
    from agents.product_profile import MARKETING_LANDING

    title = idea.strip()[:80] or "Landing"
    spec_inner: dict[str, Any] = {
        "product_name": title,
        "description": idea.strip(),
        "delivery_profile": MARKETING_LANDING,
        "category": "marketing",
        "style_preset": preset,
        "core_features": [
            {
                "name": "Hero",
                "description": f"Above-the-fold value proposition for {title}",
            },
            {
                "name": "Benefits",
                "description": "Three benefit sections with supporting copy",
            },
            {
                "name": "Call to action",
                "description": "Primary conversion button and contact/footer block",
            },
        ],
        "ui_experience": {
            "mood": preset.get("neural_prompt", ""),
            "style_preset_id": preset.get("id", ""),
            "layout": "single-page marketing landing",
        },
    }
    if agent_to_website:
        spec_inner["ui_experience"]["agent_widget"] = {
            "enabled": True,
            "note": (
                "Optional floating #aicom-agent demo chat; pipeline injects audited widget before </body> if missing."
            ),
        }
    if admin_instructions.strip():
        spec_inner["admin_instructions"] = admin_instructions.strip()

    spec_dir = data_root / "specs" / product_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    payload = {"specification": spec_inner, "delivery_profile": MARKETING_LANDING}
    (spec_dir / "specification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return spec_inner
