"""Database-backed dashboard credentials.

The dashboard password can come from three places, in order of precedence:

1. A salted hash stored in the database (set via the admin panel / wizard).
   This is the recommended source — plaintext never touches disk.
2. The legacy ``SKOPOS_DASHBOARD_PASSWORD`` env var (bootstrap / IaC).
3. Nothing configured — the dashboard is open (a setup notice is shown).

Only a PBKDF2-HMAC-SHA256 hash is persisted; the plaintext is compared with
:func:`hmac.compare_digest` and immediately discarded. Password age is tracked
so the app can warn (and notify over Telegram) when a rotation is due.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import time
from datetime import datetime, timezone

_HASH_KEY = "dashboard_password_hash"
_SET_AT_KEY = "dashboard_password_set_at_utc"

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 240_000
_SALT_BYTES = 16

_DEFAULT_MAX_AGE_DAYS = 90
_EXPIRY_WARN_DAYS = 7

# Short-lived cache so the login gate does not hit the DB on every rerun.
_CACHE_TTL_SECONDS = 15.0
_cache: dict[str, object] = {"target": None, "record": None, "at": 0.0}


# ── DB target / connection ───────────────────────────────────────────────────
def _settings_db_target() -> str:
    override = (
        os.environ.get("SKOPOS_DATABASE_URL")
        or os.environ.get("SKOPOS_DB_URL")
        or os.environ.get("DATABASE_URL")
    )
    if override and override.strip():
        return override.strip()
    try:
        from skopos.config import load_config
        from skopos.db_dialect import resolve_db_target

        return resolve_db_target(load_config("./servers.yaml"))
    except Exception:
        return "./skopos.sqlite3"


def _ensure_table(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY,
          value TEXT,
          updated_at_utc TEXT NOT NULL
        )
        """
    )
    con.commit()


def _get_setting(con, key: str) -> str | None:
    row = con.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return row.get("value")
    return row[0]


def _set_setting(con, key: str, value: str) -> None:
    from .db import now_utc_iso

    con.execute(
        """
        INSERT INTO app_settings(key, value, updated_at_utc)
        VALUES (?,?,?)
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at_utc = excluded.updated_at_utc
        """,
        (key, value, now_utc_iso()),
    )
    con.commit()


def _delete_setting(con, key: str) -> None:
    con.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    con.commit()


def _invalidate_cache() -> None:
    _cache["target"] = None
    _cache["record"] = None
    _cache["at"] = 0.0


# ── Password hashing ─────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "{}${}${}${}".format(
        _PBKDF2_ALGO,
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algo, iter_s, salt_b64, hash_b64 = encoded.split("$", 3)
        if algo != _PBKDF2_ALGO:
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def generate_strong_password(length: int = 20) -> str:
    """Generate a password guaranteed to satisfy the policy (letters + digits + symbols)."""
    length = max(16, min(64, length))
    symbols = "!@#$%^&*-_=+?"
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, symbols]
    alphabet = "".join(pools)
    while True:
        chars = [secrets.choice(pool) for pool in pools]
        chars += [secrets.choice(alphabet) for _ in range(length - len(pools))]
        secrets.SystemRandom().shuffle(chars)
        pw = "".join(chars)
        # Defensive: ensure the weak-list / policy checks pass.
        from .password_policy import validate_dashboard_password

        ok, _ = validate_dashboard_password(pw)
        if ok:
            return pw


# ── Stored record access ─────────────────────────────────────────────────────
def _read_record(db_target: str | None = None) -> dict[str, str | None]:
    target = db_target or _settings_db_target()
    now = time.monotonic()
    if (
        db_target is None
        and _cache["target"] == target
        and (now - float(_cache["at"])) < _CACHE_TTL_SECONDS
    ):
        return _cache["record"]  # type: ignore[return-value]

    from .db_connection import connect

    record: dict[str, str | None] = {"hash": None, "set_at": None}
    try:
        con = connect(target)
        _ensure_table(con)
        record["hash"] = _get_setting(con, _HASH_KEY)
        record["set_at"] = _get_setting(con, _SET_AT_KEY)
        con.close()
    except Exception:
        record = {"hash": None, "set_at": None}

    if db_target is None:
        _cache["target"] = target
        _cache["record"] = record
        _cache["at"] = now
    return record


def set_dashboard_password(password: str, *, db_target: str | None = None) -> None:
    """Persist only the salted hash + the set timestamp; caller validates policy."""
    from .db import now_utc_iso
    from .db_connection import connect

    target = db_target or _settings_db_target()
    con = connect(target)
    _ensure_table(con)
    _set_setting(con, _HASH_KEY, hash_password(password))
    _set_setting(con, _SET_AT_KEY, now_utc_iso())
    con.close()
    _invalidate_cache()


def clear_dashboard_password(*, db_target: str | None = None) -> None:
    from .db_connection import connect

    target = db_target or _settings_db_target()
    con = connect(target)
    _ensure_table(con)
    _delete_setting(con, _HASH_KEY)
    _delete_setting(con, _SET_AT_KEY)
    con.close()
    _invalidate_cache()


def dashboard_hash_set(*, db_target: str | None = None) -> bool:
    return bool(_read_record(db_target).get("hash"))


def verify_dashboard_password(password: str, *, db_target: str | None = None) -> bool:
    """Verify against the DB hash (preferred), else the legacy env plaintext."""
    encoded = _read_record(db_target).get("hash")
    if encoded:
        return verify_password(password, encoded)
    env_pw = os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip()
    if env_pw:
        return hmac.compare_digest(password, env_pw)
    return False


def dashboard_password_configured(*, db_target: str | None = None) -> bool:
    if dashboard_hash_set(db_target=db_target):
        return True
    return bool(os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip())


def password_source(*, db_target: str | None = None) -> str:
    """Return 'db' | 'env' | 'none'."""
    if dashboard_hash_set(db_target=db_target):
        return "db"
    if os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip():
        return "env"
    return "none"


def session_secret_material(*, db_target: str | None = None) -> bytes:
    """Stable server-side secret for signing browser session tokens.

    Bound to the CURRENT credential so rotating the password (or clearing it)
    invalidates every outstanding "remember me" cookie for free. Precedence:
    explicit ``SKOPOS_DASHBOARD_SESSION_SECRET`` → the stored PBKDF2 hash →
    a digest of the legacy env password. Never returns the plaintext.
    """
    override = os.environ.get("SKOPOS_DASHBOARD_SESSION_SECRET", "").strip()
    if override:
        return b"override:" + override.encode("utf-8")
    encoded = _read_record(db_target).get("hash")
    if encoded:
        return b"dbhash:" + encoded.encode("utf-8")
    env_pw = os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip()
    if env_pw:
        return b"envpw:" + hashlib.sha256(env_pw.encode("utf-8")).hexdigest().encode("ascii")
    return b"skopos-session-no-credential"


# ── Age / expiry ─────────────────────────────────────────────────────────────
def password_max_age_days() -> int:
    raw = os.environ.get("SKOPOS_DASHBOARD_PASSWORD_MAX_AGE_DAYS", str(_DEFAULT_MAX_AGE_DAYS))
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_MAX_AGE_DAYS
    return max(0, min(3650, n))


def expiry_warn_days() -> int:
    raw = os.environ.get("SKOPOS_DASHBOARD_PASSWORD_WARN_DAYS", str(_EXPIRY_WARN_DAYS))
    try:
        n = int(raw)
    except ValueError:
        n = _EXPIRY_WARN_DAYS
    return max(0, min(365, n))


def password_set_at(*, db_target: str | None = None) -> datetime | None:
    raw = _read_record(db_target).get("set_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def password_age_days(*, db_target: str | None = None) -> float | None:
    dt = password_set_at(db_target=db_target)
    if dt is None:
        return None
    return (datetime.now(tz=timezone.utc) - dt).total_seconds() / 86400.0


def password_expires_in_days(*, db_target: str | None = None) -> float | None:
    """Days until rotation is due (negative = overdue). None if tracking disabled."""
    max_age = password_max_age_days()
    if max_age <= 0:
        return None
    age = password_age_days(db_target=db_target)
    if age is None:
        return None
    return max_age - age


def password_expired(*, db_target: str | None = None) -> bool:
    remaining = password_expires_in_days(db_target=db_target)
    return remaining is not None and remaining < 0


def password_expiring_soon(*, db_target: str | None = None) -> bool:
    remaining = password_expires_in_days(db_target=db_target)
    if remaining is None:
        return False
    return 0 <= remaining <= expiry_warn_days()


# ── Login lockout (shared across Streamlit sessions / tabs) ───────────────────
_LOCKOUT_PREFIX = "login_lockout:"
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_LOCKOUT_SECONDS = 300


def _lockout_key(client_ip: str) -> str:
    # Hash so we never store raw IPs as setting keys longer than needed, and so
    # IPv6 / weird characters cannot break the key format.
    digest = hashlib.sha256((client_ip or "unknown").encode("utf-8")).hexdigest()[:32]
    return f"{_LOCKOUT_PREFIX}{digest}"


#: Every failed login also counts here, whatever address it came from. The per-address lockout
#: is only as good as the address, and where SKOPOS is reached without our proxy in front a
#: caller names its own (Vulnetix GCVE-110-PYPI-2026-021896, CWE-307): this budget bounds the
#: guessing anyway. Over it, logins slow down instead of stopping: each further failure makes the
#: submitted try wait longer, up to a minute. The caller snapshots that delay once and then
#: verifies the submitted password, even if other failures arrive meanwhile. Checking this
#: as a shared admission deadline instead let anyone lock the operator out
#: (Vulnetix GCVE-110-VULN-PYPI-2026-000644). An address that logged in successfully within
#: SKOPOS_LOGIN_KNOWN_DAYS is never held up.
_ALL_ADDRESSES = "*all-addresses*"
_DEFAULT_GLOBAL_MAX_ATTEMPTS = 30
_DEFAULT_GLOBAL_WINDOW_SECONDS = 900
_PACE_MAX_SECONDS = 60
_KNOWN_PREFIX = "login_known:"
_DEFAULT_KNOWN_DAYS = 30


def _known_key(client_ip: str) -> str:
    digest = hashlib.sha256((client_ip or "unknown").encode("utf-8")).hexdigest()[:32]
    return f"{_KNOWN_PREFIX}{digest}"


def _known_days() -> float:
    try:
        return max(0.0, float(os.environ.get("SKOPOS_LOGIN_KNOWN_DAYS", str(_DEFAULT_KNOWN_DAYS))))
    except ValueError:
        return float(_DEFAULT_KNOWN_DAYS)


def _is_known(con, client_ip: str) -> bool:
    raw = _get_setting(con, _known_key(client_ip))
    if not raw or not client_ip:
        return False
    try:
        at = float(json.loads(raw).get("at") or 0)
    except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
        return False
    return time.time() - at <= _known_days() * 86400


def _remaining_for(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        payload = json.loads(raw) if raw.startswith("{") else {"until": float(raw)}
        until = float(payload.get("until") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0
    return max(0, int(until - time.time()))


def login_lockout_remaining_seconds(client_ip: str, *, db_target: str | None = None) -> int:
    """Seconds remaining on this address's own lockout, or 0."""
    from skopos.db import connect

    target = db_target or _settings_db_target()
    try:
        con = connect(target)
        try:
            _ensure_table(con)
            mine = _get_setting(con, _lockout_key(client_ip))
        finally:
            con.close()
    except Exception:
        return 0
    return _remaining_for(mine)


def login_pace_seconds(client_ip: str, *, db_target: str | None = None) -> int:
    """Delay to apply once to a submitted attempt (at most a minute), or 0.

    This is not an admission/lockout deadline: callers must allow the attempt to proceed
    after its own delay, without checking this value again. Recently successful addresses
    are exempt.
    """
    from skopos.db import connect

    target = db_target or _settings_db_target()
    try:
        con = connect(target)
        try:
            _ensure_table(con)
            if _is_known(con, client_ip):
                return 0
            everyone = _get_setting(con, _lockout_key(_ALL_ADDRESSES))
        finally:
            con.close()
    except Exception:
        return 0
    return min(_PACE_MAX_SECONDS, _remaining_for(everyone))


def _count_failure(con, key: str, max_attempts: int, lockout_sec: int, window_sec: int = 0) -> int:
    """One failed login against ``key``. Returns the lockout seconds when this one locks it.

    With ``window_sec`` the count starts over once its first failure is that old, so a
    budget shared by everyone is not tripped by months of honest typos.
    """
    raw = _get_setting(con, key)
    attempts, until, since = 0, 0.0, 0.0
    if raw:
        try:
            payload = json.loads(raw)
            attempts = int(payload.get("attempts") or 0)
            until = float(payload.get("until") or 0)
            since = float(payload.get("since") or 0)
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
            attempts = 0
    now = time.time()
    if until > now:
        return int(until - now)
    if window_sec and since and now - since > window_sec:
        attempts = 0
    if attempts == 0:
        since = now
    attempts += 1
    if attempts >= max_attempts:
        _set_setting(con, key, json.dumps({"attempts": 0, "until": now + lockout_sec}))
        return lockout_sec
    _set_setting(con, key, json.dumps({"attempts": attempts, "until": 0, "since": since}))
    return 0


def _pace_failure(con, budget: int, window_sec: int) -> int:
    """One failed login against the all-addresses budget. Over the budget it sets how long the next
    try from an address that has not logged in before waits: 2, 4, 8 … seconds, at most a minute.
    Returns that wait, or 0 within the budget."""
    key = _lockout_key(_ALL_ADDRESSES)
    raw = _get_setting(con, key)
    attempts, since = 0, 0.0
    if raw:
        try:
            payload = json.loads(raw)
            attempts = int(payload.get("attempts") or 0)
            since = float(payload.get("since") or 0)
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
            attempts, since = 0, 0.0
    now = time.time()
    if since and now - since > window_sec:
        attempts, since = 0, 0.0
    if attempts == 0:
        since = now
    attempts += 1
    over = attempts - budget
    wait = 0 if over <= 0 else min(_PACE_MAX_SECONDS, 2 ** min(over, 6))
    _set_setting(con, key, json.dumps({"attempts": attempts, "since": since,
                                       "until": now + wait if wait else 0}))
    return wait


def register_failed_login(client_ip: str, *, db_target: str | None = None) -> int:
    """Record a failed login for ``client_ip`` and for all addresses together.

    Returns this address's lockout seconds if it just locked (or already was). Failures over the
    all-addresses budget slow logins down instead (``login_pace_seconds``); they lock no one.
    """
    from skopos.db import connect

    max_attempts = int(os.environ.get("SKOPOS_LOGIN_MAX_ATTEMPTS", str(_DEFAULT_MAX_ATTEMPTS)))
    lockout_sec = int(os.environ.get("SKOPOS_LOGIN_LOCKOUT_SECONDS", str(_DEFAULT_LOCKOUT_SECONDS)))
    max_attempts = max(3, min(20, max_attempts))
    lockout_sec = max(60, min(3600, lockout_sec))
    global_max = int(os.environ.get(
        "SKOPOS_LOGIN_GLOBAL_MAX_ATTEMPTS", str(_DEFAULT_GLOBAL_MAX_ATTEMPTS)))
    global_max = max(max_attempts, min(500, global_max))

    target = db_target or _settings_db_target()
    try:
        con = connect(target)
        try:
            _ensure_table(con)
            mine = _count_failure(con, _lockout_key(client_ip), max_attempts, lockout_sec)
            _pace_failure(con, global_max, _DEFAULT_GLOBAL_WINDOW_SECONDS)
            return mine
        finally:
            con.close()
    except Exception:
        return 0


def clear_login_lockout(client_ip: str, *, db_target: str | None = None) -> None:
    """After a successful login: clear this address's lockout and remember it as known, so failures
    from other addresses never hold it up (``login_pace_seconds``)."""
    from skopos.db import connect

    target = db_target or _settings_db_target()
    try:
        con = connect(target)
        try:
            _ensure_table(con)
            _delete_setting(con, _lockout_key(client_ip))
            if client_ip:
                _set_setting(con, _known_key(client_ip), json.dumps({"at": time.time()}))
        finally:
            con.close()
    except Exception:
        pass


__all__ = [
    "login_pace_seconds",
    "hash_password",
    "verify_password",
    "generate_strong_password",
    "set_dashboard_password",
    "clear_dashboard_password",
    "dashboard_hash_set",
    "verify_dashboard_password",
    "dashboard_password_configured",
    "password_source",
    "password_max_age_days",
    "expiry_warn_days",
    "password_set_at",
    "password_age_days",
    "password_expires_in_days",
    "password_expired",
    "password_expiring_soon",
    "login_lockout_remaining_seconds",
    "register_failed_login",
    "clear_login_lockout",
]
