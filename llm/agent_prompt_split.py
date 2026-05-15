"""
Split Architect / Developer LLM prompts: system (role + VISUAL_QUALITY_SYSTEM) vs user (JSON data only).
"""

from __future__ import annotations

import json
from typing import Any

from llm.visual_quality_system import USER_DATA_JSON_MARKER, VISUAL_QUALITY_SYSTEM


def _style_preset_from_spec(spec: dict, idea: str, landing_charter: bool) -> dict[str, Any]:
    """Compact style hints for Architect user payload (full rules stay in VISUAL_QUALITY_SYSTEM)."""
    preset: dict[str, Any] = {
        "delivery_profile": spec.get("delivery_profile") if isinstance(spec, dict) else None,
        "landing_charter": landing_charter,
    }
    if isinstance(spec, dict):
        for key in ("product_name", "category", "tags", "target_audience"):
            if spec.get(key) is not None:
                preset[key] = spec.get(key)
    if idea:
        preset["idea_excerpt"] = idea[:500]
    return preset


def build_architect_user_data(
    *,
    idea: str,
    spec: dict,
    admin_instructions: str,
    landing_charter: bool,
    peer_feedback: Any,
    research_context: str,
    methodology_block: str,
    landing_note: str,
    full_note: str,
    ux_note: str,
) -> dict[str, Any]:
    return {
        "user_brief": {
            "idea": idea,
            "admin_instructions": admin_instructions or None,
            "specification": spec if isinstance(spec, dict) else {},
            "peer_review_feedback": peer_feedback if isinstance(peer_feedback, dict) else None,
            "market_research": research_context.strip() or None,
            "methodology_spec_review": methodology_block.strip() or None,
            "factory_notes": {
                "landing_note": landing_note.strip() or None,
                "full_software_note": full_note.strip() or None,
                "ui_experience_note": ux_note.strip() or None,
            },
        },
        "style_preset": _style_preset_from_spec(spec if isinstance(spec, dict) else {}, idea, landing_charter),
    }


def build_architect_system_prompt(role_prompt: str) -> str:
    return (
        f"{role_prompt.strip()}\n\n{VISUAL_QUALITY_SYSTEM}\n\n"
        "Respond with a single JSON object matching the role schema. "
        "No markdown fences or commentary outside JSON."
    )


def format_user_data_message(user_data: dict[str, Any]) -> str:
    return f"{USER_DATA_JSON_MARKER}\n{json.dumps(user_data, ensure_ascii=False, indent=2)}"


def build_developer_user_data(
    *,
    idea: str,
    category: str,
    tags: list,
    admin_instructions: str,
    architecture: dict,
    specification: dict,
    delivery_mode: str,
    delivery_profile: str,
    implementation_plan: dict,
    analyst_brief: str | None,
    remediation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brief: dict[str, Any] = {
        "idea": idea or None,
        "category": category or None,
        "tags": tags[:16] if tags else [],
        "admin_instructions": admin_instructions or None,
        "delivery_mode": delivery_mode,
        "delivery_profile": delivery_profile,
        "specification": specification if isinstance(specification, dict) else {},
        "implementation_plan": implementation_plan,
    }
    if analyst_brief:
        brief["analyst_developer_investigation_brief"] = analyst_brief
    if remediation:
        brief["remediation"] = remediation

    return {
        "user_brief": brief,
        "architecture": architecture if isinstance(architecture, dict) else {},
    }


def build_developer_system_prompt(
    *,
    core_prompt: str,
    stack_rules: str,
    reference_shell_block: str,
    fs_appendix: str,
    polyglot_block: str,
    patch_mode_note: str,
    correction_note: str = "",
) -> str:
    parts = [
        core_prompt.strip(),
        VISUAL_QUALITY_SYSTEM,
        stack_rules.strip(),
        reference_shell_block.strip(),
        fs_appendix.strip(),
        polyglot_block.strip(),
        patch_mode_note.strip(),
        correction_note.strip(),
        "Output contract: return one JSON object with keys files, dependencies, setup_instructions, "
        "test_commands, documentation. No markdown fences.",
    ]
    return "\n\n".join(p for p in parts if p)
