"""Database settings helpers — URL build/parse, active backend."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus, unquote_plus, urlparse

from .config import AppConfig
from .db_dialect import backend_for_target, is_postgres_url, resolve_db_target


@dataclass(frozen=True)
class DbSettings:
    mode: str  # "sqlite" | "postgres"
    db_path: str
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_database: str

    @property
    def target(self) -> str:
        if self.mode == "postgres":
            return build_postgres_url(
                self.pg_host,
                self.pg_port,
                self.pg_user,
                self.pg_password,
                self.pg_database,
            )
        return self.db_path

    @property
    def backend(self) -> str:
        return backend_for_target(self.target)


def build_postgres_url(host: str, port: int, user: str, password: str, database: str) -> str:
    host = host.strip() or "localhost"
    user = user.strip() or "skopos"
    database = database.strip() or "skopos"
    pw = quote_plus(password)
    return f"postgresql://{quote_plus(user)}:{pw}@{host}:{int(port)}/{quote_plus(database)}"


def parse_postgres_url(url: str) -> dict[str, str | int] | None:
    if not is_postgres_url(url):
        return None
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    user = unquote_plus(parsed.username or "skopos")
    password = unquote_plus(parsed.password or "")
    db = (parsed.path or "/skopos").lstrip("/") or "skopos"
    port = parsed.port or 5432
    return {
        "pg_host": parsed.hostname,
        "pg_port": int(port),
        "pg_user": user,
        "pg_password": password,
        "pg_database": db,
    }


def db_settings_from_config(cfg: AppConfig) -> DbSettings:
    url = cfg.database_url
    if url and is_postgres_url(url):
        parsed = parse_postgres_url(url) or {}
        return DbSettings(
            mode="postgres",
            db_path=cfg.db_path,
            pg_host=str(parsed.get("pg_host", "localhost")),
            pg_port=int(parsed.get("pg_port", 5432)),
            pg_user=str(parsed.get("pg_user", "skopos")),
            pg_password=str(parsed.get("pg_password", "")),
            pg_database=str(parsed.get("pg_database", "skopos")),
        )
    return DbSettings(
        mode="sqlite",
        db_path=cfg.db_path or "./skopos.sqlite3",
        pg_host="localhost",
        pg_port=5432,
        pg_user="skopos",
        pg_password="",
        pg_database="skopos",
    )


def active_backend_label(cfg: AppConfig) -> str:
    return backend_for_target(resolve_db_target(cfg))


def config_from_db_settings(cfg: AppConfig, settings: DbSettings) -> AppConfig:
    database_url = settings.target if settings.mode == "postgres" else None
    return AppConfig(
        db_path=settings.db_path.strip() or "./skopos.sqlite3",
        database_url=database_url,
        geoip_mmdb_path=cfg.geoip_mmdb_path,
        poll_interval_seconds=cfg.poll_interval_seconds,
        batch_lines_per_server=cfg.batch_lines_per_server,
        security_auto_scan=cfg.security_auto_scan,
        security_scan_interval_minutes=cfg.security_scan_interval_minutes,
        telegram_enabled=cfg.telegram_enabled,
        telegram_bot_token_env=cfg.telegram_bot_token_env,
        telegram_chat_id=cfg.telegram_chat_id,
        telegram_notify_interval_minutes=cfg.telegram_notify_interval_minutes,
        servers=list(cfg.servers),
    )
