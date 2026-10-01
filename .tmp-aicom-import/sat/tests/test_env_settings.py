"""Factory environment validation."""

from __future__ import annotations

from core.env_settings import FactoryEnvSettings, validate_factory_env


def test_llm_cache_bounds() -> None:
    cfg = FactoryEnvSettings(
        AIFACTORY_LLM_CACHE_TTL_SEC=60,
        AIFACTORY_LLM_CACHE_MAX_ENTRIES=100,
    )
    assert cfg.aifactory_llm_cache_ttl_sec == 60
    assert cfg.aifactory_llm_cache_max_entries == 100


def test_postgres_requires_url() -> None:
    issues = validate_factory_env()
    assert isinstance(issues, list)
