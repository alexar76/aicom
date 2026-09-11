"""
Central budgets for LLM generations across the factory.

Providers may clamp `max_tokens` / context to their API limits; these are the
**requested** upper bounds so new installs and admin defaults start aggressive.
"""

# Admin UI + model_providers template defaults (OpenAI-compatible APIs often allow 128k / 32k on top tiers)
FACTORY_CONTEXT_WINDOW_DEFAULT = 128_000

# DeepSeek V4 (official API, Apr 2026): 1M context on Pro and Flash — https://api-docs.deepseek.com/news/news260424
DEEPSEEK_V4_PRO_CONTEXT_WINDOW = 1_000_000
DEEPSEEK_V4_FLASH_CONTEXT_WINDOW = 1_000_000
# Upper request budget; router clamps per model via llm.token_budget (DeepSeek → 128k output).
FACTORY_MAX_OUTPUT_TOKENS_HEAVY = 128_000
FACTORY_MAX_OUTPUT_TOKENS_LIGHT = 32_000

# Agent timeouts (seconds) — large JSON outputs need headroom
FACTORY_TIMEOUT_CODE_GENERATION_SEC = 600.0
FACTORY_TIMEOUT_ARCHITECTURE_SEC = 240.0
FACTORY_TIMEOUT_PM_SPEC_SEC = 180.0
FACTORY_TIMEOUT_ANALYST_SEC = 180.0
FACTORY_TIMEOUT_QA_SEC = 180.0
FACTORY_TIMEOUT_DEFAULT_AGENT_SEC = 120.0
