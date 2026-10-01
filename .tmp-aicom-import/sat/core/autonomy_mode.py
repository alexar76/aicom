"""Full autonomy mode — AI surrogate replaces human evaluators at pipeline gates."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from core.config_merge import load_merged_config
from core.factory_hold import _truthy_env
from core.paths import config_path

logger = logging.getLogger(__name__)

AutonomyMode = Literal["supervised", "full"]
_VALID_MODES = frozenset({"supervised", "full"})


def _normalize_mode(raw: str | None) -> AutonomyMode:
    v = (raw or "supervised").strip().lower()
    return "full" if v == "full" else "supervised"


def get_autonomy_mode(*, config: dict[str, Any] | None = None) -> AutonomyMode:
    """
    Resolve autonomy mode. Precedence: env ``AIFACTORY_AUTONOMY_MODE`` > config
    ``general.autonomy_mode`` > ``supervised``.
    """
    env_raw = os.environ.get("AIFACTORY_AUTONOMY_MODE", "").strip()
    if env_raw:
        return _normalize_mode(env_raw)
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict):
            return _normalize_mode(str(general.get("autonomy_mode") or "supervised"))
        flat = config.get("general.autonomy_mode")
        if flat is not None:
            return _normalize_mode(str(flat))
    try:
        merged = load_merged_config(config_path())
    except Exception as exc:
        logger.debug("autonomy_mode config read failed: %s", exc)
        return "supervised"
    general = merged.get("general")
    if isinstance(general, dict):
        return _normalize_mode(str(general.get("autonomy_mode") or "supervised"))
    return "supervised"


def is_full_autonomy(*, config: dict[str, Any] | None = None) -> bool:
    """True when the AI surrogate resolves human gates (never skips hard policy).

    Full autonomy is effective only when autonomous development (``general.auto_pipeline``)
    is enabled — the surrogate replaces operator judgment on an autonomous factory run.
    """
    if _truthy_env("AIFACTORY_FACTORY_ON_HOLD"):
        return False
    if get_autonomy_mode(config=config) != "full":
        return False
    return _auto_pipeline_enabled(config=config)


def _auto_pipeline_enabled(*, config: dict[str, Any] | None = None) -> bool:
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict) and "auto_pipeline" in general:
            return bool(general.get("auto_pipeline"))
        flat = config.get("general.auto_pipeline")
        if flat is not None:
            return bool(flat)
    try:
        merged = load_merged_config(config_path())
    except Exception as exc:
        logger.debug("autonomy_mode auto_pipeline read failed: %s", exc)
        return False
    general = merged.get("general")
    if isinstance(general, dict):
        return bool(general.get("auto_pipeline"))
    return False
