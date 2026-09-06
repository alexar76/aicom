"""Startup LLM provider sync — respects fleet profile marker (openrouter-all vs deepseek)."""

from __future__ import annotations

import logging
from typing import Any

from core.paths import data_root

logger = logging.getLogger(__name__)

PROFILE_MARKER_REL = "config/llm_active_profile"
OPENROUTER_PROFILE = "openrouter-all"


def active_llm_profile() -> str | None:
    path = data_root() / PROFILE_MARKER_REL
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def sync_provider_at_startup(*, reset_circuit: bool = True) -> dict[str, Any]:
    """Sync OpenRouter or DeepSeek config based on active fleet profile."""
    profile = active_llm_profile()
    if profile == OPENROUTER_PROFILE:
        from llm.persist_openrouter import sync_openrouter_provider_config

        return sync_openrouter_provider_config(reset_circuit=reset_circuit)
    from llm.persist_deepseek import sync_deepseek_provider_config

    return sync_deepseek_provider_config(reset_circuit=reset_circuit)


def main() -> int:
    result = sync_provider_at_startup()
    if not result.get("ok"):
        logger.error("Provider sync failed: %s", result.get("error"))
        return 1
    logger.info("Provider sync ok: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
