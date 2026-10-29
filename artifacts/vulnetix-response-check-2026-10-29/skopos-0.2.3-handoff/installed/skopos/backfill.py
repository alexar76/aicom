from __future__ import annotations

from .asn_db import get_resolver as get_asn_resolver
from .config import load_config
from .db import connect, init_db
from .ecosystem import ecosystem_segment
from .enrich import parse_user_agent, referer_domain
from .geoip import GeoIPResolver, is_private_ip
from .host_infer import infer_host


def _row_val(row, name: str, idx: int = 0):
    if isinstance(row, dict):
        return row.get(name)
    return row[idx]


def _server_ip_map(db_path: str, mmdb_path: str | None = None) -> dict[str, str]:
    try:
        cfg = load_config("./servers.yaml")
        return {s.name: s.ssh.host for s in cfg.servers}
    except Exception:
        return {}


def backfill_ua_and_referer(db_path: str, limit: int = 200000) -> int:
    con = connect(db_path)
    init_db(con)
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT id, user_agent, referer
        FROM http_requests
        WHERE log_source LIKE 'file:%'
          AND (
            ua_browser IS NULL OR ua_os IS NULL OR ua_device IS NULL OR ua_is_bot IS NULL
            OR (
              COALESCE(ua_is_bot, 0) = 0
              AND (
                LOWER(COALESCE(user_agent, '')) LIKE '%bot%'
                OR LOWER(COALESCE(user_agent, '')) LIKE '%crawl%'
                OR LOWER(COALESCE(user_agent, '')) LIKE '%spider%'
                OR LOWER(COALESCE(ua_browser, '')) LIKE '%bot%'
                OR LOWER(COALESCE(ua_browser, '')) LIKE '%spider%'
              )
            )
          )
        ORDER BY id DESC
        LIMIT {int(limit)}
        """
    )
    rows = cur.fetchall()
    updated = 0
    for _id, ua_s, ref in rows:
        ua = parse_user_agent(ua_s)
        ref_dom = referer_domain(ref)
        cur.execute(
            """
            UPDATE http_requests
            SET ua_browser = ?, ua_os = ?, ua_device = ?, ua_is_bot = ?,
                referer_domain = COALESCE(referer_domain, ?)
            WHERE id = ?
            """,
            (
                ua.browser,
                ua.os,
                ua.device,
                (1 if ua.is_bot else 0) if ua.is_bot is not None else None,
                ref_dom,
                _id,
            ),
        )
        updated += 1
    con.commit()
    con.close()
    return updated


def backfill_hosts(db_path: str, limit: int = 250000) -> int:
    """Re-infer virtual host from referer + path for all nginx rows."""
    con = connect(db_path)
    init_db(con)
    cur = con.cursor()
    ips = _server_ip_map(db_path)
    cur.execute(
        f"""
        SELECT id, server_name, path, ecosystem_segment, referer
        FROM http_requests
        WHERE log_source LIKE 'file:%'
        ORDER BY id DESC
        LIMIT {int(limit)}
        """
    )
    rows = cur.fetchall()
    updated = 0
    for _id, server_name, path, seg, referer in rows:
        host = infer_host(path, server_name=server_name, ecosystem_segment=seg, referer=referer)
        sip = ips.get(server_name)
        if not host and not sip:
            continue
        cur.execute(
            "UPDATE http_requests SET host = ?, server_ip = COALESCE(server_ip, ?) WHERE id = ?",
            (host, sip, _id),
        )
        updated += 1
    con.commit()
    con.close()
    return updated


def backfill_server_ips(db_path: str) -> int:
    ips = _server_ip_map(db_path)
    if not ips:
        return 0
    con = connect(db_path)
    init_db(con)
    cur = con.cursor()
    updated = 0
    for name, ip in ips.items():
        cur.execute(
            "UPDATE http_requests SET server_ip = ? WHERE server_name = ? AND (server_ip IS NULL OR server_ip = '')",
            (ip, name),
        )
        updated += cur.rowcount
    con.commit()
    con.close()
    return updated


def backfill_ecosystem(db_path: str, limit: int = 250000) -> int:
    con = connect(db_path)
    init_db(con)
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT id, server_name, path, host, log_source, ecosystem_segment
        FROM http_requests
        WHERE ecosystem_segment IS NULL OR log_source IS NULL
        ORDER BY id DESC
        LIMIT {int(limit)}
        """
    )
    rows = cur.fetchall()
    updated = 0
    for _id, server_name, path, host, log_source, seg in rows:
        src = log_source or "file:/var/log/nginx/access.log"
        new_seg = seg or ecosystem_segment(path, host=host, log_source=src)
        cur.execute(
            """
            UPDATE http_requests
            SET log_source = COALESCE(log_source, ?),
                ecosystem_segment = COALESCE(ecosystem_segment, ?)
            WHERE id = ?
            """,
            (src, new_seg, _id),
        )
        updated += 1
    con.commit()
    con.close()
    return updated


def backfill_countries(db_path: str, mmdb_path: str | None = None, limit: int = 250000) -> int:
    con = connect(db_path)
    init_db(con)
    geo = GeoIPResolver(mmdb_path)

    cur = con.execute(
        """
        SELECT DISTINCT remote_addr
        FROM http_requests
        WHERE remote_addr IS NOT NULL
          AND (country_code IS NULL OR country_code = '')
        """
    )
    ips = [_row_val(row, "remote_addr", 0) for row in cur.fetchall()]
    ips = [ip for ip in ips if ip]
    mapping = geo.prefetch_map(ips)

    cur = con.execute(
        f"""
        SELECT id, remote_addr
        FROM http_requests
        WHERE (country_code IS NULL OR country_code = '') AND remote_addr IS NOT NULL
        ORDER BY id DESC
        LIMIT {int(limit)}
        """
    )
    rows = cur.fetchall()
    updated = 0
    for row in rows:
        _id = _row_val(row, "id", 0)
        ip = _row_val(row, "remote_addr", 1)
        if is_private_ip(ip):
            cc, cn = "INT", "Internal"
        else:
            info = mapping.get(ip) or geo.country_for_ip(ip)
            cc, cn = info.iso_code, info.name
        con.execute(
            "UPDATE http_requests SET country_code = ?, country_name = ? WHERE id = ?",
            (cc, cn, _id),
        )
        updated += 1

    geo.close()
    con.commit()
    con.close()
    return updated


def backfill_asn(db_path: str, tsv_path: str | None = None) -> int:
    """Fill asn/asn_org for rows ingested before ASN enrichment existed.

    One UPDATE per distinct IP (idx_http_requests_remote_addr keeps it fast).
    No-op when the iptoasn TSV is not installed.
    """
    resolver = get_asn_resolver(tsv_path)
    if not resolver.has_data:
        return 0

    con = connect(db_path)
    init_db(con)
    cur = con.execute(
        """
        SELECT DISTINCT remote_addr
        FROM http_requests
        WHERE remote_addr IS NOT NULL AND asn IS NULL
        """
    )
    ips = [_row_val(row, "remote_addr", 0) for row in cur.fetchall()]
    updated = 0
    for ip in ips:
        if not ip or is_private_ip(ip):
            continue
        info = resolver.lookup(ip)
        if info.asn is None:
            continue
        cur = con.execute(
            "UPDATE http_requests SET asn = ?, asn_org = ? WHERE remote_addr = ? AND asn IS NULL",
            (info.asn, info.org, ip),
        )
        updated += max(0, cur.rowcount)
    con.commit()
    con.close()
    return updated


def backfill_all(db_path: str, mmdb_path: str | None = None, asn_tsv_path: str | None = None) -> dict[str, int]:
    return {
        "server_ips": backfill_server_ips(db_path),
        "hosts": backfill_hosts(db_path),
        "ua": backfill_ua_and_referer(db_path),
        "countries": backfill_countries(db_path, mmdb_path=mmdb_path),
        "ecosystem": backfill_ecosystem(db_path),
        "asn": backfill_asn(db_path, tsv_path=asn_tsv_path),
    }
