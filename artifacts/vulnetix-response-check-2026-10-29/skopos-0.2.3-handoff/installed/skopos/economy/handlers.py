"""Capability handlers — reuse SKOPOS DB and briefing logic."""

from __future__ import annotations

from typing import Any, Callable


def handle_fleet_status(*, config_path: str, agent_yaml: str, inp: dict[str, Any]) -> dict[str, Any]:
    from skopos.public_status import build_fleet_status

    return build_fleet_status(config_path=config_path)


def handle_security_posture(
    *,
    config_path: str,
    agent_yaml: str,
    inp: dict[str, Any],
) -> dict[str, Any]:
    from skopos.config import load_app_env, load_config
    from skopos.db_dialect import resolve_db_target
    from skopos.security.posture_loader import load_security_posture

    load_app_env()
    cfg = load_config(config_path)
    posture = load_security_posture(resolve_db_target(cfg), cfg, agent_yaml_path=agent_yaml)
    server_filter = (inp.get("server_name") or "").strip()
    alerts = []
    for a in posture.alerts[:20]:
        if server_filter and a.server_name and a.server_name != server_filter:
            continue
        alerts.append(
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "server_name": a.server_name,
                "category": a.category,
            }
        )
    return {
        "fleet_score": posture.fleet_score,
        "grade": posture.grade,
        "critical_count": posture.critical_count,
        "high_count": posture.high_count,
        "alerts": alerts,
        "remarks": list(posture.remarks[:12]),
    }


def handle_traffic_summary(
    *,
    config_path: str,
    agent_yaml: str,
    inp: dict[str, Any],
) -> dict[str, Any]:
    from skopos.agent.ecosystem_briefing import traffic_snapshot_from_df
    from skopos.config import load_app_env, load_config
    from skopos.db import connect_for_config, init_db, read_sql_query
    from skopos.db_dialect import cutoff_iso

    hours = int(inp.get("hours") or 24)
    hours = max(1, min(168, hours))
    load_app_env()
    cfg = load_config(config_path)
    con = connect_for_config(cfg)
    init_db(con)
    names = [s.name for s in cfg.servers]
    if not names:
        con.close()
        return {
            "requests": 0,
            "unique_ips": 0,
            "top_segment": None,
            "top_segment_share_pct": 0.0,
            "error_rate_pct": 0.0,
            "active_hosts": 0,
        }
    ph = ",".join("?" * len(names))
    since = cutoff_iso(hours=hours)
    q = f"""
      SELECT ts_utc, remote_addr, status, host, ecosystem_segment
      FROM http_requests
      WHERE server_name IN ({ph}) AND ts_utc >= ?
    """
    try:
        df = read_sql_query(q, con, params=[*names, since])
    except Exception:
        df = None
    con.close()
    snap = traffic_snapshot_from_df(df)
    return {
        "requests": snap.requests,
        "unique_ips": snap.unique_ips,
        "top_segment": snap.top_segment,
        "top_segment_share_pct": snap.top_segment_share_pct,
        "error_rate_pct": snap.error_rate_pct,
        "active_hosts": snap.active_hosts,
        "hours": hours,
    }


def handle_briefing(
    *,
    config_path: str,
    agent_yaml: str,
    inp: dict[str, Any],
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from skopos.agent.ecosystem_briefing import generate_ecosystem_briefing, traffic_snapshot_from_df
    from skopos.config import load_app_env, load_config
    from skopos.db import connect_for_config, init_db, read_sql_query
    from skopos.db_dialect import cutoff_iso, resolve_db_target
    from skopos.security.posture_loader import load_security_posture

    lang = (inp.get("language") or "en").strip().lower()
    if lang not in ("en", "ru", "es"):
        lang = "en"
    load_app_env()
    cfg = load_config(config_path)
    posture = load_security_posture(resolve_db_target(cfg), cfg, agent_yaml_path=agent_yaml)
    con = connect_for_config(cfg)
    init_db(con)
    names = [s.name for s in cfg.servers]
    ph = ",".join("?" * len(names)) if names else "?"
    since = cutoff_iso(hours=24)
    traffic = None
    if names:
        q = f"SELECT ts_utc, remote_addr, status, host, ecosystem_segment FROM http_requests WHERE server_name IN ({ph}) AND ts_utc >= ?"
        try:
            df = read_sql_query(q, con, params=[*names, since])
            traffic = traffic_snapshot_from_df(df)
        except Exception:
            traffic = None
    con.close()
    period = f"last 24h (as of {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})"
    briefing = generate_ecosystem_briefing(
        cfg,
        posture,
        agent_yaml_path=agent_yaml,
        locale=lang,
        period_label=period,
        traffic=traffic,
    )
    return {
        "text": briefing.text,
        "mood": briefing.mood,
        "fleet_score": briefing.fleet_score,
        "grade": briefing.grade,
        "source": briefing.source,
        "error": briefing.error,
    }


HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "skopos.fleet.status@v1": handle_fleet_status,
    "skopos.security.posture@v1": handle_security_posture,
    "skopos.traffic.summary@v1": handle_traffic_summary,
    "skopos.briefing@v1": handle_briefing,
}
