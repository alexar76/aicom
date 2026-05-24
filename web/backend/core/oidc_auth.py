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
    if claims.get("nonce") != nonce:
        raise ValueError("OIDC nonce missing or mismatched")
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


def map_groups_to_role(groups: list[str]) -> str:
    raw = (os.environ.get("AIFACTORY_OIDC_ROLE_MAP") or "").strip()
    if raw:
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError:
            mapping = {}
        for g in groups:
            if g in mapping:
                return str(mapping[g])
    default = (os.environ.get("AIFACTORY_OIDC_DEFAULT_ROLE") or "viewer").strip()
    return default


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


def _trusted_cidrs() -> list[Any]:
    raw = (os.environ.get("AIFACTORY_SSO_TRUSTED_CIDRS") or "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").strip()
    nets = []
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
    return nets


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
