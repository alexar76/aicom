"""
Pipeline database backend resolution (SQLite default, optional PostgreSQL).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from core.logging_utils import log_suppressed
from core.paths import pipeline_db_path

logger = logging.getLogger(__name__)

PipelineDbBackend = Literal["sqlite", "postgres", "json"]


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def pipeline_database_url() -> str:
    return (
        os.environ.get("PIPELINE_DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )


def pipeline_db_backend() -> PipelineDbBackend:
    explicit = os.environ.get("PIPELINE_DB_BACKEND", "").strip().lower()
    if explicit in ("sqlite", "postgres", "json"):
        return explicit  # type: ignore[return-value]
    if _truthy("USE_SQLITE", "true"):
        return "sqlite"
    if pipeline_database_url() and _truthy("PIPELINE_USE_POSTGRES", "false"):
        return "postgres"
    return "json"


def pipeline_uses_sql_store() -> bool:
    return pipeline_db_backend() in ("sqlite", "postgres")


def apply_pipeline_db_config_from_app_config(config: Any | None = None) -> dict[str, str]:
    """
    Apply Admin → Settings pipeline DB fields to process environment.
    Called from entrypoint and optionally on config reload.

    When ``PIPELINE_DB_ENV_PINNED=1`` (set by ``docker-compose.prod.yml``),
    compose-injected ``PIPELINE_DB_BACKEND`` / URL values win over Admin YAML.
    """
    if _truthy("PIPELINE_DB_ENV_PINNED", "false"):
        backend = os.environ.get("PIPELINE_DB_BACKEND", "sqlite").strip().lower()
        if backend not in ("sqlite", "postgres", "json"):
            backend = "sqlite"
        url = pipeline_database_url()
        if backend == "postgres":
            os.environ["USE_SQLITE"] = "false"
            os.environ["PIPELINE_USE_POSTGRES"] = "true"
        elif backend == "sqlite":
            os.environ["USE_SQLITE"] = "true"
            os.environ["PIPELINE_USE_POSTGRES"] = "false"
        else:
            os.environ["USE_SQLITE"] = "false"
            os.environ["PIPELINE_USE_POSTGRES"] = "false"
        return {"backend": backend, "database_url_set": "1" if url else "0", "source": "env_pinned"}

    backend = "sqlite"
    url = ""
    if config is not None:
        try:
            backend = str(config.get("general.pipeline_db_backend", "sqlite") or "sqlite").strip().lower()
        except Exception:
            backend = "sqlite"
        try:
            url = str(config.get("general.pipeline_database_url", "") or "").strip()
        except Exception:
            url = ""

    if backend not in ("sqlite", "postgres", "json"):
        backend = "sqlite"

    os.environ["PIPELINE_DB_BACKEND"] = backend
    if url:
        os.environ["PIPELINE_DATABASE_URL"] = url

    if backend == "postgres":
        os.environ["USE_SQLITE"] = "false"
        os.environ["PIPELINE_USE_POSTGRES"] = "true"
        if url:
            os.environ["PIPELINE_DATABASE_URL"] = url
    elif backend == "sqlite":
        os.environ["USE_SQLITE"] = "true"
        os.environ["PIPELINE_USE_POSTGRES"] = "false"
    else:
        os.environ["USE_SQLITE"] = "false"
        os.environ["PIPELINE_USE_POSTGRES"] = "false"

    return {"backend": backend, "database_url_set": "1" if url else "0", "source": "admin_config"}


def create_sync_pipeline_manager():
    """Factory for sync SQLiteManager or PostgresManager."""
    backend = pipeline_db_backend()
    if backend == "postgres":
        url = pipeline_database_url()
        if not url:
            raise ValueError("PIPELINE_DB_BACKEND=postgres requires PIPELINE_DATABASE_URL")
        from orchestrator.postgres_manager import PostgresManager

        mgr = PostgresManager(url)
        mgr.connect()
        return mgr
    from orchestrator.sqlite_manager import SQLiteManager

    mgr = SQLiteManager(str(pipeline_db_path()))
    mgr.connect()
    return mgr


def create_async_pipeline_store():
    """Factory for AsyncSQLiteManager or AsyncPostgresManager."""
    backend = pipeline_db_backend()
    if backend == "postgres":
        url = pipeline_database_url()
        if not url:
            raise ValueError("PIPELINE_DB_BACKEND=postgres requires PIPELINE_DATABASE_URL")
        from orchestrator.async_postgres_manager import AsyncPostgresManager

        return AsyncPostgresManager(url)
    from orchestrator.async_sqlite_manager import AsyncSQLiteManager

    return AsyncSQLiteManager(str(pipeline_db_path()))


def mask_database_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse, urlunparse

        p = urlparse(url)
        if p.password:
            netloc = p.netloc.replace(f":{p.password}@", ":***@")
            if "@" not in netloc and p.username:
                netloc = f"{p.username}:***@{p.hostname or ''}" + (f":{p.port}" if p.port else "")
            return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (core/pipeline_database.py)", exc_info=_suppressed_exc)
    return url[:8] + "…" if len(url) > 12 else "***"
