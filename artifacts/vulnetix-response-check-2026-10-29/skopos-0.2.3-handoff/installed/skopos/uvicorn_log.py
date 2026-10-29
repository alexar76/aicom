from __future__ import annotations

import re

from .db import ParsedRequest

# Uvicorn / Starlette default access log:
# INFO:     127.0.0.1:50932 - "POST /api/lottery/update HTTP/1.1" 200 OK
_UVICORN_RE = re.compile(
    r'^(?:\S+\s+)?(?P<ip>\d+\.\d+\.\d+\.\d+):\d+\s+-\s+'
    r'"(?P<request>[^"]+)"\s+'
    r"(?P<status>\d{3})\s"
)

_REQ_RE = re.compile(r"^(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/(?P<ver>\d\.\d)$")


def parse_uvicorn_line(line: str) -> ParsedRequest | None:
    line = line.strip("\n")
    if not line.strip():
        return None

    m = _UVICORN_RE.search(line)
    if not m:
        return None

    request_raw = m.group("request") or None
    method = None
    path = None
    if request_raw:
        rm = _REQ_RE.match(request_raw)
        if rm:
            method = rm.group("method")
            path = rm.group("path")

    status = int(m.group("status")) if m.group("status") else None
    return ParsedRequest(
        log_source=None,
        ecosystem_segment=None,
        server_ip=None,
        ts_utc=None,
        remote_addr=m.group("ip") or None,
        host=None,
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
        bytes_sent=None,
        referer=None,
        user_agent=None,
        request_raw=request_raw,
        line_raw=line,
    )
