"""API key authentication for the OpenAI-compatible serve endpoint."""

from __future__ import annotations

import hmac
import ipaddress
import logging
import os
import sys
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("metis.api.auth")

_bearer = HTTPBearer(auto_error=False)

# Emit the "paid endpoints are open" warning only once per process.
_unauth_warning_emitted = False


def _resolve_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def get_api_key_from_env() -> Optional[str]:
    return _resolve_env("METIS_API_KEY", "SUPERBRAIN_API_KEY", "COGNITIVE_API_KEY")


def is_production_mode() -> bool:
    val = _resolve_env(
        "METIS_PRODUCTION",
        "SUPERBRAIN_PRODUCTION",
        "COGNITIVE_PRODUCTION",
        # Ecosystem-standard prod signals — a normal AIFACTORY prod deploy must
        # flip metis into production mode (fail-closed on the paid endpoints).
        "AIFACTORY_PROD",
        "AIFACTORY_PRODUCTION",
    ) or ""
    if val.lower() in ("1", "true", "yes"):
        return True
    env = (os.environ.get("AIFACTORY_ENV") or "").lower()
    return env in ("production", "prod", "live")


_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
_FORWARDING_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "x-forwarded-host")

# The kernel's tables of TCP sockets, with the uid that owns each (Linux).
_PROC_NET_TCP = ("/proc/net/tcp", "/proc/net/tcp6")


def _proc_endpoint(field: str) -> tuple[str, int]:
    """`0100007F:1F90` -> ("127.0.0.1", 8080): each 32-bit word of the address is printed in
    the kernel's byte order, the port in plain hex."""
    hexaddr, _, hexport = field.partition(":")
    raw = bytes.fromhex(hexaddr)
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    addr = ipaddress.ip_address(raw)
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return str(addr), int(hexport, 16)


def _caller_is_this_user(conn: Request) -> bool:
    """The caller's socket belongs to the user this server runs as.

    A reverse proxy on this machine connects over loopback too, and nginx's default proxy_pass
    sends the upstream's own Host (127.0.0.1:port) and no forwarding header, so nothing in the
    request tells it from a local client (Vulnetix, on GCVE-110-PYPI-2026-018883). Its workers
    run as their own user, and on Linux the kernel records which user owns each socket. A proxy
    running as this same user, or a system without the table (macOS, Windows), still needs a key
    to be told apart. A connection the table does not show is refused."""
    tables = [p for p in _PROC_NET_TCP if os.path.exists(p)]
    if not tables:
        return True
    client = conn.client
    if not client:
        return False
    try:
        peer = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    if peer.version == 6 and peer.ipv4_mapped:
        peer = peer.ipv4_mapped
    want = (str(peer), int(client.port or 0))
    server_port = (conn.scope.get("server") or (None, None))[1]
    for path in tables:
        try:
            with open(path, encoding="ascii", errors="replace") as fh:
                next(fh, None)  # the header line
                for line in fh:
                    f = line.split()
                    if len(f) < 8 or f[3] != "01":  # 01 = ESTABLISHED
                        continue
                    try:
                        if _proc_endpoint(f[1]) != want:
                            continue
                        if server_port is not None and _proc_endpoint(f[2])[1] != int(server_port):
                            continue
                        return int(f[7]) == os.geteuid()
                    except ValueError:
                        continue
        except OSError:
            continue
    return False


def _host_is_loopback(hostport: str) -> bool:
    """`localhost[:port]`, `127.0.0.1[:port]` or `[::1][:port]`, as a Host header or netloc."""
    value = hostport.strip().lower()
    if value.startswith("["):
        host = value[1:value.find("]")] if "]" in value else ""
    else:
        host = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    return host in _LOOPBACK_NAMES


def local_caller(request: Request) -> bool:
    """The machine's own user: a loopback packet with a loopback Host, no forwarding headers
    (behind nginx on this host every caller's packet is from 127.0.0.1), no Origin but a
    loopback page (a site open in that user's browser can POST here too) and, on Linux, a
    socket owned by this server's user (nginx's default proxy_pass sends a loopback Host and
    no forwarding header; its workers run as their own user)."""
    peer = request.client.host if request.client else ""
    try:
        if not ipaddress.ip_address(peer).is_loopback:
            return False
    except ValueError:
        return False
    if any(h in request.headers for h in _FORWARDING_HEADERS):
        return False
    if not _host_is_loopback(request.headers.get("host", "")):
        return False
    origin = request.headers.get("origin")
    if origin is not None:
        scheme, _, rest = origin.strip().partition("://")
        if scheme not in ("http", "https") or not _host_is_loopback(rest.split("/", 1)[0]):
            return False
    return _caller_is_this_user(request)


async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> Optional[str]:
    """Validate Bearer token when production mode or key is configured."""
    expected = get_api_key_from_env()
    production = is_production_mode()

    if not production and not expected:
        # No key outside production: callers on this machine only. Every caller used to be
        # served here, on a port bound to 0.0.0.0 by default, spending the operator's model
        # budget (the class of Vulnetix GCVE-110-PYPI-2026-018883, CWE-306).
        if not local_caller(request):
            raise HTTPException(
                status_code=401,
                detail="No METIS_API_KEY is configured, so only callers on this machine are "
                "served. Set METIS_API_KEY to serve others.",
            )
        global _unauth_warning_emitted
        if not _unauth_warning_emitted:
            _unauth_warning_emitted = True
            logger.warning(
                "Metis paid endpoints (/v1/verify, /v1/verify/stream, /aimarket/invoke) "
                "answer local callers UNAUTHENTICATED: no API key configured and not in "
                "production mode. Set METIS_API_KEY before exposing this service."
            )
        return None

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: Bearer sk-...",
        )

    token = credentials.credentials
    if not expected:
        if production:
            raise HTTPException(
                status_code=500,
                detail="METIS_API_KEY must be set in production mode",
            )
        # SECURITY: fail-closed — never accept an unverified token. In dev without
        # a configured key, a local caller is let in by the early return above.
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not hmac.compare_digest(token, expected):  # constant-time
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token
