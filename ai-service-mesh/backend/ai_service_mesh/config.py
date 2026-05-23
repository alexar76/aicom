"""Runtime configuration from environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str | None:
    """Locate .env without assuming a fixed package depth."""
    explicit = os.environ.get("MESH_ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / ".env",
        here.parents[1] / ".env",
        Path.cwd() / ".env",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


_ENV_FILE = _resolve_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MESH_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8090
    env: str = "production"
    cors_origins: str = "http://localhost:5173"
    api_token: str = ""
    admin_token: str = ""
    hub_url: str = "http://127.0.0.1:9080"
    skip_demo_capabilities: bool = True
    reject_demo_invoke_output: bool = True
    allow_localhost_agents: bool = False
    allow_insecure_tokens: bool = False
    data_dir: Path = Path(".mesh_data")
    database_url: str = ""
    rate_limit: int = 120
    max_agent_attempts: int = 12
    task_stale_seconds: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
