"""
Validated factory environment variables (subset of docker-compose / .env).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FactoryEnvSettings(BaseSettings):
    """Core tunables loaded at process start; invalid values fail fast in strict mode."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aifactory_data_root: str = Field(default="/app/data", alias="AIFACTORY_DATA_ROOT")
    aifactory_workspace_id: str = Field(default="default", alias="AIFACTORY_WORKSPACE_ID")
    pipeline_db_backend: Literal["sqlite", "postgres", "json"] = Field(
        default="sqlite",
        alias="PIPELINE_DB_BACKEND",
    )
    pipeline_database_url: str = Field(default="", alias="PIPELINE_DATABASE_URL")
    use_sqlite: bool = Field(default=True, alias="USE_SQLITE")
    aifactory_llm_cache_ttl_sec: int = Field(default=300, ge=1, le=86400, alias="AIFACTORY_LLM_CACHE_TTL_SEC")
    aifactory_llm_cache_max_entries: int = Field(
        default=500,
        ge=1,
        le=100_000,
        alias="AIFACTORY_LLM_CACHE_MAX_ENTRIES",
    )
    aifactory_sandbox_preview_api: bool = Field(default=True, alias="AIFACTORY_SANDBOX_PREVIEW_API")
    aifactory_worker_health_port: int = Field(default=8091, ge=0, le=65535, alias="AIFACTORY_WORKER_HEALTH_PORT")
    aifactory_max_running_tasks: int = Field(default=24, ge=1, le=500, alias="AIFACTORY_MAX_RUNNING_TASKS")
    aifactory_pipeline_json_compact: bool = Field(default=False, alias="AIFACTORY_PIPELINE_JSON_COMPACT")

    @field_validator("pipeline_db_backend", mode="before")
    @classmethod
    def normalize_backend(cls, v: object) -> str:
        return str(v or "sqlite").strip().lower()

    @field_validator("use_sqlite", mode="before")
    @classmethod
    def parse_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v or "").strip().lower() in ("1", "true", "yes")


@lru_cache(maxsize=1)
def get_factory_env() -> FactoryEnvSettings:
    return FactoryEnvSettings()


def validate_factory_env(*, strict_postgres: bool = False) -> list[str]:
    """Return human-readable configuration issues (empty list = OK)."""
    issues: list[str] = []
    cfg = get_factory_env()
    if cfg.pipeline_db_backend == "postgres" and not cfg.pipeline_database_url.strip():
        issues.append("PIPELINE_DB_BACKEND=postgres requires PIPELINE_DATABASE_URL")
    if strict_postgres and cfg.pipeline_db_backend == "postgres":
        url = cfg.pipeline_database_url.lower()
        if "localhost" in url and os.environ.get("AIFACTORY_ALLOW_LOCAL_PG") != "1":
            issues.append("Postgres URL points at localhost; set AIFACTORY_ALLOW_LOCAL_PG=1 for dev only")
    return issues
