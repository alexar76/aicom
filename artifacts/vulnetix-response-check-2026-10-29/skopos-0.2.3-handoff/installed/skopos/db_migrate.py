"""Copy SKOPOS data between SQLite and PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import init_db
from .db_connection import DbConnection, connect
from .db_dialect import backend_for_target, is_integrity_error, is_postgres_url
from .security.store import init_security_db

# Insert order respects FK: findings → snapshots.
MIGRATION_TABLES: tuple[str, ...] = (
    "collector_status",
    "ingested_lines",
    "http_requests",
    "security_snapshots",
    "security_findings",
    "port_knock_events",
)

SERIAL_TABLES = frozenset(
    {
        "ingested_lines",
        "http_requests",
        "security_snapshots",
        "security_findings",
        "port_knock_events",
    }
)


@dataclass
class MigrationResult:
    ok: bool
    rows_copied: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def _row_to_dict(row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _table_columns(con: DbConnection, table: str) -> list[str]:
    if con.backend == "postgresql":
        rows = con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
        return [r["column_name"] for r in rows]
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _count_rows(con: DbConnection, table: str) -> int:
    row = con.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    if isinstance(row, dict):
        return int(row.get("c") or 0)
    return int(row[0])


def _reset_pg_sequences(con: DbConnection) -> None:
    if con.backend != "postgresql":
        return
    for table in SERIAL_TABLES:
        con.execute(
            f"""
            SELECT setval(
              pg_get_serial_sequence('{table}', 'id'),
              COALESCE((SELECT MAX(id) FROM {table}), 1),
              true
            )
            """
        )


def _truncate_dest(con: DbConnection) -> None:
    if con.backend == "postgresql":
        tables = ", ".join(MIGRATION_TABLES)
        con.execute(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
    else:
        for table in reversed(MIGRATION_TABLES):
            con.execute(f"DELETE FROM {table}")
    con.commit()


def check_database_connection(target: str) -> tuple[bool, str]:
    try:
        con = connect(target)
        init_db(con)
        init_security_db(con)
        backend = backend_for_target(target)
        label = "PostgreSQL" if backend == "postgresql" else "SQLite"
        path = target if backend == "sqlite" else target.split("@")[-1]
        con.close()
        return True, f"{label} OK — {path}"
    except Exception as exc:
        return False, str(exc)


def migrate_database(
    source_target: str,
    dest_target: str,
    *,
    replace_dest: bool = True,
) -> MigrationResult:
    if source_target.strip() == dest_target.strip():
        return MigrationResult(ok=True, rows_copied={})

    src = connect(source_target)
    dst = connect(dest_target)
    copied: dict[str, int] = {}
    try:
        init_db(dst)
        init_security_db(dst)

        dest_total = sum(_count_rows(dst, t) for t in MIGRATION_TABLES)
        if dest_total and replace_dest:
            _truncate_dest(dst)
        elif dest_total:
            return MigrationResult(
                ok=False,
                error="Destination database is not empty. Enable replace to migrate.",
            )

        for table in MIGRATION_TABLES:
            src_count = _count_rows(src, table)
            if src_count == 0:
                copied[table] = 0
                continue

            cols = _table_columns(src, table)
            dst_cols = set(_table_columns(dst, table))
            use_cols = [c for c in cols if c in dst_cols]
            if not use_cols:
                copied[table] = 0
                continue

            col_sql = ", ".join(use_cols)
            ph = ", ".join("?" * len(use_cols))
            rows = src.execute(f"SELECT {col_sql} FROM {table}").fetchall()
            n = 0
            for row in rows:
                data = _row_to_dict(row)
                vals = tuple(data.get(c) for c in use_cols)
                try:
                    dst.execute(
                        f"INSERT INTO {table} ({col_sql}) VALUES ({ph})",
                        vals,
                    )
                    n += 1
                except Exception as exc:
                    if is_integrity_error(exc) and dst.backend == "postgresql":
                        dst.connection.rollback()
                        continue
                    if is_integrity_error(exc):
                        continue
                    raise
            copied[table] = n

        _reset_pg_sequences(dst)
        dst.commit()
        return MigrationResult(ok=True, rows_copied=copied)
    except Exception as exc:
        try:
            dst.connection.rollback()
        except Exception:
            pass
        return MigrationResult(ok=False, error=str(exc), rows_copied=copied)
    finally:
        src.close()
        dst.close()


def source_row_total(target: str) -> int:
    con = connect(target)
    try:
        init_db(con)
        init_security_db(con)
        return sum(_count_rows(con, t) for t in MIGRATION_TABLES)
    finally:
        con.close()
