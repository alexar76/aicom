"""
Central budgets for LLM generations across the factory.

Providers may clamp `max_tokens` / context to their API limits; these are the
**requested** upper bounds so new installs and admin defaults start aggressive.
"""

# Admin UI + model_providers template defaults (OpenAI-compatible APIs often allow 128k / 32k on top tiers)
FACTORY_CONTEXT_WINDOW_DEFAULT = 128_000
FACTORY_MAX_OUTPUT_TOKENS_HEAVY = 32_000
FACTORY_MAX_OUTPUT_TOKENS_LIGHT = 16_000

# Agent timeouts (seconds) — large JSON outputs need headroom
FACTORY_TIMEOUT_CODE_GENERATION_SEC = 300.0
FACTORY_TIMEOUT_ARCHITECTURE_SEC = 240.0
FACTORY_TIMEOUT_PM_SPEC_SEC = 180.0
FACTORY_TIMEOUT_ANALYST_SEC = 180.0
FACTORY_TIMEOUT_QA_SEC = 180.0
FACTORY_TIMEOUT_DEFAULT_AGENT_SEC = 120.0
