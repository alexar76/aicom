"""Load HTTP request rows for analytics — slim columns, no global sort.

KPIs and charts should use ``analytics_queries`` (SQL aggregates). This module
only loads row-level data when needed (legacy paths / tests). Journal uses
``fetch_period_journal`` with ORDER BY + LIMIT.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .db import DbConnection, read_sql_query

# Chart/filter path — no fat referer/user_agent blobs (derived ua_* kept).
_SELECT_COLS = """
  server_name, server_ip, log_source, ecosystem_segment,
  ts_utc, remote_addr, host,
  country_code, country_name,
  ua_browser, ua_os, ua_device, ua_is_bot,
  referer_domain,
  method, path, status, bytes_sent
"""


@dataclass(frozen=True)
class PeriodLoadMeta:
    total_in_period: int
    returned_rows: int


def _server_placeholders(known_servers: tuple[str, ...]) -> str:
    return ",".join("?" * len(known_servers)) if known_servers else "''"


def _period_where(known_servers: tuple[str, ...]) -> str:
    """Prefer ts_utc so (server_name, ts_utc) / partial file indexes apply."""
    placeholders = _server_placeholders(known_servers)
    return f"""
      log_source LIKE 'file:%'
        AND server_name IN ({placeholders})
        AND ts_utc IS NOT NULL
        AND ts_utc >= ?
        AND ts_utc <= ?
    """


def count_period_requests(
    con: DbConnection,
    known_servers: tuple[str, ...],
    since_utc_iso: str,
    until_utc_iso: str,
) -> int:
    q = f"SELECT COUNT(*) AS n FROM http_requests WHERE {_period_where(known_servers)}"
    params = list(known_servers) + [since_utc_iso, until_utc_iso]
    df = read_sql_query(q, con, params=params)
    if df.empty:
        return 0
    return int(df.iloc[0]["n"])


def fetch_period_requests(
    con: DbConnection,
    known_servers: tuple[str, ...],
    since_utc_iso: str,
    until_utc_iso: str,
) -> tuple[pd.DataFrame, PeriodLoadMeta]:
    """Return every request row in ``[since, until]`` (no row cap, no ORDER BY)."""
    where = _period_where(known_servers)
    params = list(known_servers) + [since_utc_iso, until_utc_iso]

    q = f"""
      SELECT {_SELECT_COLS}
      FROM http_requests
      WHERE {where}
    """
    df = read_sql_query(q, con, params=params)
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], errors="coerce", utc=True)

    n = len(df)
    return df, PeriodLoadMeta(total_in_period=n, returned_rows=n)
