"""Short-lived HMAC tokens gating the floating agent's HTTP backend.

The floating assistant is a self-contained browser widget (see ``agent_widget``)
that talks to the ``/agent/*`` endpoints on the SKOPOS API server. Those
endpoints expose sensitive fleet context and burn LLM budget, so they must only
answer authenticated operators.

The Streamlit dashboard and the API server run in the same container and share
one database, so we mint a stateless HMAC token on the authenticated Streamlit
page and verify it on the API server with a shared secret:

    token = "<expiry_epoch>.<hex_hmac_sha256(secret, expiry)>"

No session table is required and the token self-expires. The secret comes from
``SKOPOS_AGENT_TOKEN_SECRET`` (explicit, recommended for multi-process setups)
or is generated once and persisted in ``app_settings`` so both processes agree.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from hashlib import sha256

_SECRET_KEY = "agent_token_secret"
_DEFAULT_TTL_SECONDS = 3600  # 1 hour — matches a typical dashboard session
_MAX_TTL_SECONDS = 12 * 3600

# Process-local cache so we do not hit the DB on every mint/verify.
_cache: dict[str, str | None] = {"secret": None}


def _env_secret() -> str | None:
    val = (os.environ.get("SKOPOS_AGENT_TOKEN_SECRET") or "").strip()
    return val or None


def _load_or_create_persistent_secret() -> str:
    """Fetch the shared secret from app_settings, generating it once if absent."""
    from skopos.auth_store import _ensure_table, _get_setting, _set_setting, _settings_db_target
    from skopos.db_connection import connect

    target = _settings_db_target()
    con = connect(target)
    try:
        _ensure_table(con)
        existing = _get_setting(con, _SECRET_KEY)
        if existing and existing.strip():
            return existing.strip()
        fresh = secrets.token_hex(32)
        _set_setting(con, _SECRET_KEY, fresh)
        return fresh
    finally:
        try:
            con.close()
        except Exception:
            pass


def agent_secret() -> str:
    """Resolve the shared HMAC secret (env override wins; else persisted)."""
    env = _env_secret()
    if env:
        return env
    cached = _cache.get("secret")
    if cached:
        return cached
    try:
        secret = _load_or_create_persistent_secret()
    except Exception:
        # Last-resort ephemeral secret: tokens still work within one process.
        secret = _cache.get("secret") or secrets.token_hex(32)
    _cache["secret"] = secret
    return secret


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()


def issue_token(ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    """Mint a token valid for ``ttl_seconds`` (clamped to a sane maximum)."""
    ttl = max(60, min(int(ttl_seconds), _MAX_TTL_SECONDS))
    exp = int(time.time()) + ttl
    return f"{exp}.{_sign(agent_secret(), str(exp))}"


def token_ttl_seconds() -> int:
    return _DEFAULT_TTL_SECONDS


def verify_token(token: str | None) -> bool:
    """True when the token is well-formed, unexpired and correctly signed."""
    if not token or "." not in token:
        return False
    exp_str, _, sig = token.partition(".")
    if not exp_str.isdigit() or not sig:
        return False
    if int(exp_str) < int(time.time()):
        return False
    expected = _sign(agent_secret(), exp_str)
    return hmac.compare_digest(expected, sig)


def reset_cache() -> None:
    """Testing helper — drop the in-process secret cache."""
    _cache["secret"] = None
