from __future__ import annotations

import re
from datetime import datetime, timezone

from dateutil import tz

from .db import ParsedRequest


# Supports two common patterns:
# 1) "combined" log:
#    1.2.3.4 - - [13/Jul/2026:12:34:56 +0000] "GET /path?q=1 HTTP/1.1" 200 123 "-" "UA"
# 2) same but with host prefixed (recommended for "all addresses"):
#    example.com 1.2.3.4 - - [..] "GET ..." 200 123 "-" "UA"

_RE = re.compile(
    r'^(?:(?P<host>\S+)\s+)?'
    r'(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3})\s+'
    r'(?P<bytes>\d+|-)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)"(?:\s+"(?P<trailing_host>[^"]*)")?)?'
    r"\s*$"
)

_REQ_RE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/(?P<ver>\d\.\d)$")


def _parse_ts_to_utc_iso(ts: str) -> str | None:
    # Example: "13/Jul/2026:12:34:56 +0000"
    try:
        dt = datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def parse_access_line(line: str) -> ParsedRequest | None:
    line = line.strip("\n")
    if not line.strip():
        return None

    m = _RE.match(line)
    if not m:
        return ParsedRequest(
            log_source=None,
            ecosystem_segment=None,
            server_ip=None,
            ts_utc=None,
            remote_addr=None,
            host=None,
            country_code=None,
            country_name=None,
            ua_browser=None,
            ua_os=None,
            ua_device=None,
            ua_is_bot=None,
            referer_domain=None,
            method=None,
            path=None,
            status=None,
            bytes_sent=None,
            referer=None,
            user_agent=None,
            request_raw=None,
            line_raw=line,
        )

    request_raw = m.group("request") or None
    method = None
    path = None
    if request_raw:
        rm = _REQ_RE.match(request_raw)
        if rm:
            method = rm.group("method")
            path = rm.group("path")

    status = int(m.group("status")) if m.group("status") else None
    bytes_s = m.group("bytes")
    bytes_sent = None if bytes_s in (None, "-") else int(bytes_s)

    host = m.group("host") or m.group("trailing_host") or None
    if host in (None, "-"):
        host = None

    return ParsedRequest(
        log_source=None,
        ecosystem_segment=None,
        server_ip=None,
        ts_utc=_parse_ts_to_utc_iso(m.group("ts")) if m.group("ts") else None,
        remote_addr=m.group("ip") or None,
        host=host,
        country_code=None,
        country_name=None,
        ua_browser=None,
        ua_os=None,
        ua_device=None,
        ua_is_bot=None,
        referer_domain=None,
        method=method,
        path=path,
        status=status,
        bytes_sent=bytes_sent,
        referer=(m.group("referer") if m.group("referer") is not None else None),
        user_agent=(m.group("ua") if m.group("ua") is not None else None),
        request_raw=request_raw,
        line_raw=line,
    )

