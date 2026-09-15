"""Small helpers shared by pipeline worker modules."""

from __future__ import annotations

import os


def env_truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def monitoring_refresh_decision(output_data: dict) -> tuple[bool, dict]:
    """Build QA-shaped payload when analyst monitoring requests a shipped-slice refresh."""
    if output_data.get("request_implementation_refresh") is not True:
        return False, {}
    brief = str(output_data.get("implementation_refresh_brief") or "").strip()
    issues = [brief] if brief else ["Regenerate shipped slice per analyst monitoring (no brief provided)."]
    return True, {
        "passed": False,
        "demo_quality": {"issues": issues, "source": "analyst_monitoring"},
        "reasons": ["analyst_monitoring_refresh"],
        "validation_snapshot": output_data.get("validation"),
        "improvement_suggestions_snapshot": output_data.get("improvement_suggestions"),
    }


def delivery_profile_from_product_dict(product: dict) -> str:
    """Resolved pipeline delivery profile (explicit metadata wins, else infer from copy)."""
    from agents.product_profile import infer_delivery_profile
    from core.delivery_profile import normalize_delivery_profile

    dp_raw = product.get("delivery_profile")
    if dp_raw:
        return normalize_delivery_profile(str(dp_raw))
    md = product.get("metadata")
    if isinstance(md, dict) and md.get("delivery_profile"):
        return normalize_delivery_profile(str(md.get("delivery_profile")))
    return infer_delivery_profile(product.get("admin_instructions"), product.get("idea"))
