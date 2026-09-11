"""
Resolved quality / gates settings (YAML under ``quality:`` + optional env overrides).

Env vars always win when set to a non-empty value so operators can force behavior in Docker
without changing saved Admin settings.
"""

from __future__ import annotations

import os
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path

# Bundled presets when Admin toggles pipeline cost optimized mode (see ``apply_pipeline_cost_preset``).
OPTIMIZED_QUALITY_PRESETS: dict[str, Any] = {
    "max_pipeline_cost_usd": 5.0,
    "max_pipeline_repair_rounds": 10,
    "max_pipeline_repair_rounds_landing": 8,
    "monitoring_dev_refresh_enabled": False,
}
LEGACY_QUALITY_PRESETS: dict[str, Any] = {
    "max_pipeline_cost_usd": 0.0,
    "max_pipeline_repair_rounds": 25,
    "max_pipeline_repair_rounds_landing": 25,
    "monitoring_dev_refresh_enabled": True,
}

DEFAULT_QUALITY: dict[str, Any] = {
    **OPTIMIZED_QUALITY_PRESETS,
    "demo_quality_min_score": 55,
    "strict_demo_gates": True,
    "visual_quality_gate": True,
    "visual_quality_strict": False,
    "visual_quality_app_checks": True,
    "browser_e2e_enabled": True,
    "browser_max_pages": 100,
    "browser_max_depth": 10,
    "marketplace_quality_gate": True,
    "marketplace_require_full_qa": False,
    "marketplace_min_spec_coverage": 15,
    "marketplace_require_design_novelty": True,
    "marketplace_min_design_novelty": 0.18,
    "marketplace_require_qa_realism": True,
    "marketplace_require_release_score": True,
    "marketplace_min_release_score": 70,
    "marketplace_require_non_placeholder_name": True,
    "marketplace_require_methodology": True,
    "marketplace_require_quality_constitution": False,
    "marketplace_require_release_cockpit": False,
    "quality_constitution_pipeline_enabled": True,
    "auto_recovery_enabled": True,
    "auto_recovery_min_repair_round": 3,
    "auto_recovery_require_storefront_eligible": True,
    "auto_recovery_require_tests": True,
}

_CACHE_MTIME: float | None = None
_CACHE_SLICE: dict[str, Any] | None = None


def _coerce_bool(val: Any, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _coerce_int(val: Any, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _coerce_float(val: Any, default: float, *, lo: float, hi: float) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def quality_yaml_slice() -> dict[str, Any]:
    """Merged ``quality`` block from layered config (defaults + YAML), no env overrides."""
    global _CACHE_MTIME, _CACHE_SLICE
    primary = config_path()
    try:
        mtime = primary.stat().st_mtime
    except OSError:
        mtime = 0.0
    if mtime == _CACHE_MTIME and _CACHE_SLICE is not None:
        return dict(_CACHE_SLICE)
    merged = load_merged_config(primary)
    raw = merged.get("quality")
    out = dict(DEFAULT_QUALITY)
    if isinstance(raw, dict):
        for k, base in DEFAULT_QUALITY.items():
            if k not in raw:
                continue
            v = raw[k]
            if isinstance(base, bool):
                out[k] = _coerce_bool(v, bool(base))
            elif isinstance(base, int):
                bounds = {
                    "max_pipeline_repair_rounds": (1, 100),
                    "max_pipeline_repair_rounds_landing": (1, 100),
                    "demo_quality_min_score": (0, 100),
                    "browser_max_pages": (1, 500),
                    "browser_max_depth": (1, 30),
                    "marketplace_min_spec_coverage": (0, 100),
                    "marketplace_min_release_score": (0, 100),
                    "auto_recovery_min_repair_round": (1, 100),
                }.get(k, (0, 10**9))
                out[k] = _coerce_int(v, int(base), lo=bounds[0], hi=bounds[1])
            elif isinstance(base, float):
                float_bounds = {
                    "max_pipeline_cost_usd": (0.0, 100_000.0),
                    "marketplace_min_design_novelty": (0.0, 1.0),
                }
                lo, hi = float_bounds.get(k, (0.0, 1.0))
                out[k] = _coerce_float(v, float(base), lo=lo, hi=hi)
    _CACHE_MTIME = mtime
    _CACHE_SLICE = out
    return dict(out)


def _env_nonempty(name: str) -> bool:
    v = os.environ.get(name)
    return v is not None and str(v).strip() != ""


def _env_int(name: str) -> int | None:
    if not _env_nonempty(name):
        return None
    try:
        return int(os.environ[name])
    except (TypeError, ValueError):
        return None


def _env_float(name: str) -> float | None:
    if not _env_nonempty(name):
        return None
    try:
        return float(os.environ[name])
    except (TypeError, ValueError):
        return None


def _env_bool(name: str) -> bool | None:
    if not _env_nonempty(name):
        return None
    return os.environ[name].strip().lower() in ("1", "true", "yes", "on")


def max_pipeline_cost_usd() -> float:
    """
    Per-product LLM spend cap (USD). ``0`` disables the guard.

    Resolution: ``AIFACTORY_MAX_PIPELINE_COST_USD`` env (when set) overrides
    Admin → Settings → Pipeline & product quality → Max LLM cost per product.
    """
    e = _env_float("AIFACTORY_MAX_PIPELINE_COST_USD")
    if e is not None:
        return max(0.0, e)
    return max(0.0, float(quality_yaml_slice().get("max_pipeline_cost_usd", 0.0)))


def max_pipeline_repair_rounds() -> int:
    e = _env_int("AIFACTORY_MAX_QUALITY_LOOPS")
    if e is not None:
        return max(1, e)
    return max(1, int(quality_yaml_slice()["max_pipeline_repair_rounds"]))


def max_pipeline_repair_rounds_for_delivery_profile(delivery_profile: str | None) -> int:
    """
    Landing / brochure builds should not burn days in QA repair ping-pong.

    - ``AIFACTORY_LANDING_MAX_QUALITY_LOOPS``: explicit cap for ``marketing_landing`` (never above global max).
    - Default: same as global max — landings should ship, not fail early on a lower cap.
    """
    base = max_pipeline_repair_rounds()
    try:
        from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile
    except ImportError:
        return base
    if normalize_delivery_profile(delivery_profile) != MARKETING_LANDING:
        return base
    e = _env_int("AIFACTORY_LANDING_MAX_QUALITY_LOOPS")
    if e is not None:
        return max(1, min(base, e))
    try:
        landing_cap = int(quality_yaml_slice().get("max_pipeline_repair_rounds_landing", base))
    except (TypeError, ValueError):
        landing_cap = base
    return max(1, min(base, landing_cap))


def max_pipeline_repair_rounds_for_product(product: dict | None) -> int:
    """Per-product repair budget. Honors a process-bandit arm override
    (``max_quality_loops_override``) but never above an explicit hard env cap; falls
    back to the delivery-profile default otherwise (L4 apply step)."""
    if isinstance(product, dict):
        ov = product.get("max_quality_loops_override")
        if isinstance(ov, int) and ov >= 1:
            hard = _env_int("AIFACTORY_MAX_QUALITY_LOOPS")
            if hard is not None:
                return max(1, min(ov, max(1, hard)))
            return max(1, ov)
    try:
        from orchestrator.worker_utils import delivery_profile_from_product_dict

        profile = delivery_profile_from_product_dict(product) if isinstance(product, dict) else None
    except Exception:
        profile = product.get("delivery_profile") if isinstance(product, dict) else None
    return max_pipeline_repair_rounds_for_delivery_profile(profile)


def demo_quality_min_score() -> int:
    e = _env_int("AIFACTORY_DEMO_QUALITY_MIN_SCORE")
    if e is not None:
        return max(0, min(100, e))
    return int(quality_yaml_slice()["demo_quality_min_score"])


def strict_demo_gates() -> bool:
    e = _env_bool("AIFACTORY_STRICT_DEMO_GATES")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["strict_demo_gates"])


def visual_quality_gate() -> bool:
    e = _env_bool("AIFACTORY_VISUAL_QUALITY_GATE")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["visual_quality_gate"])


def visual_quality_strict() -> bool:
    e = _env_bool("AIFACTORY_VISUAL_QUALITY_STRICT")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["visual_quality_strict"])


def visual_quality_app_checks() -> bool:
    e = _env_bool("AIFACTORY_VISUAL_QUALITY_APP_CHECKS")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["visual_quality_app_checks"])


def browser_e2e_enabled() -> bool:
    e = _env_bool("AIFACTORY_BROWSER_E2E")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["browser_e2e_enabled"])


def browser_max_pages() -> int:
    e = _env_int("AIFACTORY_BROWSER_MAX_PAGES")
    if e is not None:
        return max(1, min(500, e))
    return int(quality_yaml_slice()["browser_max_pages"])


def browser_max_depth() -> int:
    e = _env_int("AIFACTORY_BROWSER_MAX_DEPTH")
    if e is not None:
        return max(1, min(30, e))
    return int(quality_yaml_slice()["browser_max_depth"])


def marketplace_quality_gate() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_QUALITY_GATE")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_quality_gate"])


def marketplace_require_full_qa() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_FULL_QA")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_full_qa"])


def marketplace_min_spec_coverage() -> int:
    e = _env_int("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE")
    if e is not None:
        return max(0, min(100, e))
    return int(quality_yaml_slice()["marketplace_min_spec_coverage"])


def marketplace_require_design_novelty() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_design_novelty"])


def marketplace_min_design_novelty() -> float:
    e = _env_float("AIFACTORY_MARKETPLACE_MIN_DESIGN_NOVELTY")
    if e is not None:
        return max(0.0, min(1.0, e))
    return float(quality_yaml_slice()["marketplace_min_design_novelty"])


def marketplace_require_qa_realism() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_qa_realism"])


def marketplace_require_release_score() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_SCORE")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_release_score"])


def marketplace_min_release_score() -> int:
    e = _env_int("AIFACTORY_MARKETPLACE_MIN_RELEASE_SCORE")
    if e is not None:
        return max(0, min(100, e))
    return int(quality_yaml_slice()["marketplace_min_release_score"])


def marketplace_require_non_placeholder_name() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_NON_PLACEHOLDER_NAME")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_non_placeholder_name"])


def marketplace_require_methodology() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_methodology"])


def marketplace_require_quality_constitution() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_QUALITY_CONSTITUTION")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_quality_constitution"])


def marketplace_require_release_cockpit() -> bool:
    e = _env_bool("AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_COCKPIT")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["marketplace_require_release_cockpit"])


def quality_constitution_pipeline_enabled() -> bool:
    e = _env_bool("AIFACTORY_QUALITY_CONSTITUTION_ENABLED")
    if e is not None:
        return e
    return bool(quality_yaml_slice()["quality_constitution_pipeline_enabled"])


def auto_recovery_enabled() -> bool:
    e = _env_bool("AIFACTORY_AUTO_RECOVERY_ENABLED")
    if e is not None:
        return e
    return bool(quality_yaml_slice().get("auto_recovery_enabled", True))


def auto_recovery_min_repair_round() -> int:
    e = _env_int("AIFACTORY_AUTO_RECOVERY_MIN_REPAIR_ROUND")
    if e is not None:
        return max(1, min(100, e))
    return max(1, int(quality_yaml_slice().get("auto_recovery_min_repair_round", 3)))


def auto_recovery_require_storefront_eligible() -> bool:
    e = _env_bool("AIFACTORY_AUTO_RECOVERY_REQUIRE_STOREFRONT")
    if e is not None:
        return e
    return bool(quality_yaml_slice().get("auto_recovery_require_storefront_eligible", True))


def auto_recovery_require_tests() -> bool:
    e = _env_bool("AIFACTORY_AUTO_RECOVERY_REQUIRE_TESTS")
    if e is not None:
        return e
    return bool(quality_yaml_slice().get("auto_recovery_require_tests", True))


def pipeline_cost_optimized(*, config: Any | None = None) -> bool:
    """Admin toggle: token-efficient pre-ship repair + cautious post-ship refresh (default on)."""
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict):
            return _coerce_bool(general.get("pipeline_cost_optimized"), True)
        return _coerce_bool(config.get("general.pipeline_cost_optimized"), True)
    merged = load_merged_config(config_path())
    general = merged.get("general")
    if isinstance(general, dict):
        return _coerce_bool(general.get("pipeline_cost_optimized"), True)
    return True


def monitoring_dev_refresh_enabled() -> bool:
    """
    Post-ship analyst monitoring may queue a full developer regen (expensive).

    Default **off** in optimized mode — analyst still runs; dev refresh is opt-in per YAML.
    Env ``AIFACTORY_MONITORING_DEV_REFRESH_ENABLED`` overrides when set.
    """
    e = _env_bool("AIFACTORY_MONITORING_DEV_REFRESH_ENABLED")
    if e is not None:
        return e
    return bool(quality_yaml_slice().get("monitoring_dev_refresh_enabled", False))


def apply_pipeline_cost_preset(*, optimized: bool) -> dict[str, Any]:
    """Merge optimized or legacy spend/repair presets into the quality block."""
    preset = OPTIMIZED_QUALITY_PRESETS if optimized else LEGACY_QUALITY_PRESETS
    out = dict(DEFAULT_QUALITY)
    out.update(quality_yaml_slice())
    out.update(preset)
    return out


def admin_quality_panel_dict() -> dict[str, Any]:
    """Values shown in Admin → Settings (saved YAML slice, defaults applied)."""
    return quality_yaml_slice()


def normalize_quality_settings_payload(raw: Any) -> dict[str, Any] | None:
    """Validate admin POST ``quality`` object; return normalized dict or None if invalid."""
    if not isinstance(raw, dict):
        return None
    out = dict(DEFAULT_QUALITY)
    for k, base in DEFAULT_QUALITY.items():
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(base, bool):
            out[k] = _coerce_bool(v, bool(base))
        elif isinstance(base, int):
            bounds = {
                "max_pipeline_repair_rounds": (1, 100),
                "demo_quality_min_score": (0, 100),
                "browser_max_pages": (1, 500),
                "browser_max_depth": (1, 30),
                "marketplace_min_spec_coverage": (0, 100),
                "marketplace_min_release_score": (0, 100),
            }.get(k, (0, 10**9))
            out[k] = _coerce_int(v, int(base), lo=bounds[0], hi=bounds[1])
        elif isinstance(base, float):
            float_bounds = {
                "max_pipeline_cost_usd": (0.0, 100_000.0),
                "marketplace_min_design_novelty": (0.0, 1.0),
            }
            lo, hi = float_bounds.get(k, (0.0, 1.0))
            out[k] = _coerce_float(v, float(base), lo=lo, hi=hi)
    return out


def gate_failing_model() -> str | None:
    """Model name to use when a product has failed a QA gate at least once.

    ``AIFACTORY_GATE_FAILING_MODEL`` — set to a stronger model (e.g. ``claude-opus-4-7``)
    to give repair rounds a higher chance of passing without burning the entire loop budget.
    Returns None when not configured, meaning the default routing rule model applies.
    """
    v = os.environ.get("AIFACTORY_GATE_FAILING_MODEL")
    if v and str(v).strip():
        return str(v).strip()
    return None


def bump_quality_cache_after_config_write() -> None:
    """Call after saving config so the next read sees fresh on-disk values."""
    global _CACHE_MTIME, _CACHE_SLICE
    _CACHE_MTIME = None
    _CACHE_SLICE = None
