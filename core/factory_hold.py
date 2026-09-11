"""Factory hold (pause) — stop all pipeline agent/LLM work without shutting down services."""

from __future__ import annotations

import logging
import os
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path

logger = logging.getLogger(__name__)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_factory_hard_stopped() -> bool:
    """
    HARD stop via env ``AIFACTORY_FACTORY_ON_HOLD=1`` — an emergency kill switch.

    Unlike the UI/config hold, this pauses **everything**, including explicitly
    requested on-demand work (admin "New product", guest fast-path landings).
    The pipeline worker bails out entirely when this is set.
    """
    return _truthy_env("AIFACTORY_FACTORY_ON_HOLD")


def is_factory_on_hold(*, config: dict[str, Any] | None = None) -> bool:
    """
    When True, Director analysis/discovery/auto-enqueue and the pipeline worker skip
    agent/LLM task phases until resume.

    Env ``AIFACTORY_FACTORY_ON_HOLD=1`` overrides config (emergency stop without UI).

    Note: config soft-hold and env hard-stop both pause agent work. The env flag
    additionally skips the entire worker cycle (including non-LLM recovery).
    """
    if _truthy_env("AIFACTORY_FACTORY_ON_HOLD"):
        return True
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict):
            return bool(general.get("factory_on_hold", False))
        return bool(config.get("general.factory_on_hold", False))
    try:
        merged = load_merged_config(config_path())
    except Exception as exc:
        logger.debug("factory_on_hold config read failed: %s", exc)
        return False
    general = merged.get("general")
    if isinstance(general, dict):
        return bool(general.get("factory_on_hold", False))
    return False
