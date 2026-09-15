"""OIDC / trusted-header SSO for admin panel."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

OIDC_STATE_COOKIE = "oidc_state"
OIDC_NONCE_COOKIE = "oidc_nonce"


def _is_production_env() -> bool:
    """Production when ``AIFACTORY_PROD=1`` — matches security/prod_startup_guard.py."""
    try:
        from security.prod_startup_guard import is_production_mode

        return is_production_mode()
    except Exception:
        return (os.environ.get("AIFACTORY_PROD") or "").strip() == "1"


def oidc_enabled() -> bool:
    return os.environ.get("AIFACTORY_OIDC_ENABLED", "").strip().lower() in ("1", "true", "yes")


def oidc_config() -> dict[str, str]:
    issuer = (os.environ.get("AIFACTORY_OIDC_ISSUER") or "").strip().rstrip("/")
    client_id = (os.environ.get("AIFACTORY_OIDC_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("AIFACTORY_OIDC_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.environ.get("AIFACTORY_OIDC_REDIRECT_URI") or "").strip()
    if not all([issuer, client_id, redirect_uri]):
        raise ValueError(
            "OIDC enabled but AIFACTORY_OIDC_ISSUER, CLIENT_ID, or REDIRECT_URI missing"
        )
    return {
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": (os.environ.get("AIFACTORY_OIDC_SCOPES") or "openid profile email").strip(),
    }


def _discovery(issuer: str) -> dict[str, Any]:
    url = f"{issuer}/.well-known/openid-configuration"
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def build_authorize_url(state: str, nonce: str) -> str:
    cfg = oidc_config()
    doc = _discovery(cfg["issuer"])
    auth_ep = doc["authorization_endpoint"]
    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "scope": cfg["scopes"],
        "redirect_uri": cfg["redirect_uri"],
        "state": state,
        "nonce": nonce,
    }
    return f"{auth_ep}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    cfg = oidc_config()
    doc = _discovery(cfg["issuer"])
    token_ep = doc["token_endpoint"]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
    }
    if cfg["client_secret"]:
        data["client_secret"] = cfg["client_secret"]
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(token_ep, data=data)
        resp.raise_for_status()
        return resp.json()


def verify_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    cfg = oidc_config()
    doc = _discovery(cfg["issuer"])
    jwks_uri = doc["jwks_uri"]
    issuer = doc.get("issuer", cfg["issuer"])
    client = PyJWKClient(jwks_uri)
    signing_key = client.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "ES256", "EdDSA"],
        audience=cfg["client_id"],
        issuer=issuer,
        options={"require": ["exp", "iat", "sub"]},
    )
    if not nonce or claims.get("nonce") != nonce:
        raise ValueError("OIDC nonce missing or mismatched")

    try:
        from core.persistent_security_store import get_persistent_security_store

        store = get_persistent_security_store()
    except Exception as exc:
        store = None
        store_error: Exception | None = exc
    else:
        store_error = None

    if store is None:
        # Replay protection is unavailable. Fail CLOSED in production — a replayable
        # id_token is an account-takeover vector — but stay usable (fail open with a
        # warning) on dev/staging where the persistent store may be absent.
        if _is_production_env():
            logger.error(
                "OIDC nonce-replay store unavailable in production — refusing login: %s",
                store_error,
            )
            raise ValueError("OIDC replay protection unavailable")
        logger.warning(
            "OIDC nonce-replay store unavailable (fail-open, non-production): %s",
            store_error,
        )
    else:
        exp = float(claims.get("exp") or (time.time() + 3600))
        ttl = min(max(exp - time.time(), 60.0), 3600.0)
        if not store.claim_nonce(nonce, ttl):
            raise ValueError("nonce already used")

    return claims


def safe_post_login_url(raw: str | None) -> str:
    """Return a same-origin admin path; reject operator misconfig open redirects."""
    url = (raw or "/admin").strip()
    if url.startswith("/") and not url.startswith("//"):
        return url
    own = (
        os.environ.get("AIFACTORY_PUBLIC_BASE_URL")
        or os.environ.get("AIFACTORY_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if own and (url == own or url.startswith(own + "/")):
        return url
    logger.warning("Unsafe AIFACTORY_OIDC_POST_LOGIN_URL %r — falling back to /admin", url)
    return "/admin"


def _validate_role(value: str, *, source: str) -> str | None:
    """Return the canonical AdminRole value, or None (with a warning) if invalid."""
    try:
        from web.backend.core.admin_roles import AdminRole

        return AdminRole(value.strip().lower()).value
    except Exception:
        logger.warning(
            "Ignoring invalid OIDC role %r from %s — not a known admin role", value, source
        )
        return None


def map_groups_to_role(groups: list[str]) -> str:
    raw = (os.environ.get("AIFACTORY_OIDC_ROLE_MAP") or "").strip()
    if raw:
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError:
            mapping = {}
        for g in groups:
            if g in mapping:
                role = _validate_role(str(mapping[g]), source=f"AIFACTORY_OIDC_ROLE_MAP[{g!r}]")
                if role is not None:
                    return role
    default_raw = (os.environ.get("AIFACTORY_OIDC_DEFAULT_ROLE") or "viewer").strip()
    return _validate_role(default_raw, source="AIFACTORY_OIDC_DEFAULT_ROLE") or "viewer"


def claims_to_username(claims: dict[str, Any]) -> str:
    for key in ("preferred_username", "email", "sub"):
        val = claims.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()[:64]
    return "oidc-user"


def new_oidc_state() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)


# ── Trusted reverse-proxy header SSO ─────────────────────────────────────


def trusted_header_enabled() -> bool:
    return bool((os.environ.get("AIFACTORY_SSO_TRUSTED_HEADER") or "").strip())


def trusted_header_name() -> str:
    return (os.environ.get("AIFACTORY_SSO_TRUSTED_HEADER") or "X-Remote-User").strip()


# Loopback only by default: the trusted-header SSO path turns any X-Remote-User into
# an authenticated admin, so the reverse proxy MUST be the only thing that can reach
# the backend on these addresses. Operators fronting the app with a remote proxy must
# explicitly opt into a wider, tightly-scoped CIDR via AIFACTORY_SSO_TRUSTED_CIDRS.
_DEFAULT_TRUSTED_CIDRS = "127.0.0.1,::1"

# Networks broad enough that "any LAN/Internet host can forge the header" — warn loudly.
_WIDE_TRUSTED_PREFIXES = (
    (IPv4Address, 24),  # IPv4 networks larger than a /24
    (IPv6Address, 64),  # IPv6 networks larger than a /64
)

_TRUSTED_CIDR_WARNED = False


def _trusted_cidrs() -> list[Any]:
    raw = (os.environ.get("AIFACTORY_SSO_TRUSTED_CIDRS") or _DEFAULT_TRUSTED_CIDRS).strip()
    nets: list[Any] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "/" in part:
                nets.append(ip_network(part, strict=False))
            else:
                nets.append(ip_address(part))
        except ValueError:
            continue
    _warn_on_wide_trusted_cidrs(nets)
    return nets


def _warn_on_wide_trusted_cidrs(nets: list[Any]) -> None:
    """Emit a one-time startup warning if a wide or public trusted CIDR is configured."""
    global _TRUSTED_CIDR_WARNED
    if _TRUSTED_CIDR_WARNED or not trusted_header_enabled():
        return
    risky: list[str] = []
    for net in nets:
        if isinstance(net, (IPv4Address, IPv6Address)):
            continue  # single host — narrow by definition
        if not net.is_private and not net.is_loopback and not net.is_link_local:
            risky.append(f"{net} (public)")
            continue
        for fam, max_prefix in _WIDE_TRUSTED_PREFIXES:
            if isinstance(net.network_address, fam) and net.prefixlen < max_prefix:
                risky.append(str(net))
                break
    if risky:
        logger.warning(
            "AIFACTORY_SSO_TRUSTED_CIDRS allows wide/public ranges %s — any host in these "
            "ranges can forge the %s header and gain admin. Restrict to the reverse proxy's "
            "exact address (e.g. 127.0.0.1 or 10.0.0.10/32).",
            ", ".join(risky),
            trusted_header_name(),
        )
    _TRUSTED_CIDR_WARNED = True


def client_in_trusted_cidr(client_ip: str) -> bool:
    try:
        addr = ip_address(client_ip)
    except ValueError:
        return False
    for net in _trusted_cidrs():
        if isinstance(net, (IPv4Address, IPv6Address)):
            if addr == net:
                return True
        elif addr in net:
            return True
    return False


def username_from_trusted_header(headers: dict[str, str], client_ip: str) -> str | None:
    if not trusted_header_enabled():
        return None
    if not client_in_trusted_cidr(client_ip):
        return None
    hname = trusted_header_name().lower()
    for k, v in headers.items():
        if k.lower() == hname and v.strip():
            return v.strip().lower()[:64]
    return None
