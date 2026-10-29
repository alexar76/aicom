"""SQL dialect helpers — SQLite (dev) and PostgreSQL (prod)."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import AppConfig

Backend = str  # "sqlite" | "postgresql"

INTEGRITY_ERRORS: tuple[type[BaseException], ...] = (sqlite3.IntegrityError,)

try:
    from psycopg.errors import UniqueViolation

    INTEGRITY_ERRORS = (sqlite3.IntegrityError, UniqueViolation)
except ImportError:  # pragma: no cover - optional prod driver
    UniqueViolation = None  # type: ignore[misc, assignment]


def is_postgres_url(target: str) -> bool:
    return target.startswith(("postgresql://", "postgres://"))


def backend_for_target(target: str) -> Backend:
    return "postgresql" if is_postgres_url(target) else "sqlite"


def resolve_db_target(cfg: AppConfig) -> str:
    url = getattr(cfg, "database_url", None)
    if url and str(url).strip():
        return str(url).strip()
    return cfg.db_path


def adapt_sql(sql: str, backend: Backend) -> str:
    if backend != "postgresql":
        return sql
    out = sql.replace("?", "%s")
    # psycopg treats % as placeholder syntax — escape literals (e.g. LIKE 'file:%').
    return re.sub(r"%(?!s|b|t)", "%%", out)


def placeholders(n: int, backend: Backend) -> str:
    ch = "%s" if backend == "postgresql" else "?"
    return ",".join([ch] * n)


def cutoff_iso(*, hours: int | None = None, days: int | None = None) -> str:
    delta = timedelta(hours=hours or 0, days=days or 0)
    return (datetime.now(tz=timezone.utc) - delta).isoformat()


def scan_day_expr(column: str, backend: Backend) -> str:
    if backend == "postgresql":
        return f"LEFT({column}, 10)"
    return f"date({column})"


def group_concat_distinct(column: str, backend: Backend) -> str:
    if backend == "postgresql":
        return f"string_agg(DISTINCT {column}::text, ',')"
    return f"GROUP_CONCAT(DISTINCT {column})"


def is_integrity_error(exc: BaseException) -> bool:
    return isinstance(exc, INTEGRITY_ERRORS)


def require_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PostgreSQL requires psycopg. Install: pip install 'psycopg[binary]>=3.2'"
        ) from exc
    return psycopg


def split_sql_script(script: str) -> list[str]:
    parts: list[str] = []
    for chunk in script.split(";"):
        stmt = chunk.strip()
        if not stmt or stmt.startswith("--"):
            continue
        parts.append(stmt)
    return parts


def normalize_row(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return {"value": row[0] if row else None}
