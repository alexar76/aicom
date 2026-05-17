"""
First-run admin bootstrap — never ships a known default password in production.

Priority:
  1. ``AIFACTORY_DEV_BOOTSTRAP_PASSWORD`` — explicit dev/demo password (non-interactive).
  2. Interactive TTY — prompt in the console (``docker compose run --rm -it`` / local ``./run.sh``).
  3. Non-interactive — random password written to ``/app/data/secrets/bootstrap_admin.txt`` (0600).
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path

from core.paths import admin_users_path, bootstrap_admin_secret_path, legacy_admin_path

logger = logging.getLogger(__name__)

ADMIN_JSON = legacy_admin_path()
USERS_JSON = admin_users_path()
BOOTSTRAP_SECRET = bootstrap_admin_secret_path()


def _users_json_path() -> Path:
    return Path(os.environ.get("ADMIN_USERS_PATH", str(USERS_JSON)))


def _admin_already_configured() -> bool:
    users_path = _users_json_path()
    if users_path.is_file():
        try:
            data = json.loads(users_path.read_text(encoding="utf-8"))
            users = data.get("users") if isinstance(data, dict) else []
            if isinstance(users, list) and users:
                return True
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if ADMIN_JSON.is_file():
        try:
            cfg = json.loads(ADMIN_JSON.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("password_hash"):
                return True
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return False


_MIN_PASSWORD_LEN = 8
_MAX_PROMPT_ATTEMPTS = 3


def _prompt_password_interactive() -> str | None:
    """
    Ask for admin password on a TTY. Returns None → caller should generate a random secret.
    """
    if not sys.stdin.isatty():
        return None

    print("", file=sys.stderr)
    print("┌──────────────────────────────────────────────────────────────────────────┐", file=sys.stderr)
    print("│ AI-Factory — first admin account (no credentials on this data volume)     │", file=sys.stderr)
    print("│                                                                          │", file=sys.stderr)
    print("│  Create the initial super_admin user (username: admin).                    │", file=sys.stderr)
    print("│  Password is hidden while typing. Minimum 8 characters.                  │", file=sys.stderr)
    print("└──────────────────────────────────────────────────────────────────────────┘", file=sys.stderr)
    print("", file=sys.stderr)

    for attempt in range(1, _MAX_PROMPT_ATTEMPTS + 1):
        try:
            p1 = getpass.getpass("Admin password: ")
            p2 = getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBootstrap cancelled.", file=sys.stderr)
            return None

        if len(p1) < _MIN_PASSWORD_LEN:
            print(f"Password too short (min {_MIN_PASSWORD_LEN} characters).", file=sys.stderr)
            continue
        if p1 != p2:
            print("Passwords do not match — try again.", file=sys.stderr)
            continue
        return p1

    print(
        f"No valid password after {_MAX_PROMPT_ATTEMPTS} attempts; "
        f"generating a random password to {BOOTSTRAP_SECRET}.",
        file=sys.stderr,
    )
    return None


def _resolve_initial_password() -> tuple[str, str]:
    """
    Returns (password, source) where source is one of:
    dev_env | interactive | generated
    """
    dev_pw = (os.environ.get("AIFACTORY_DEV_BOOTSTRAP_PASSWORD") or "").strip()
    if dev_pw:
        if len(dev_pw) < _MIN_PASSWORD_LEN:
            raise ValueError(
                f"AIFACTORY_DEV_BOOTSTRAP_PASSWORD must be at least {_MIN_PASSWORD_LEN} characters"
            )
        return dev_pw, "dev_env"

    prompted = _prompt_password_interactive()
    if prompted:
        return prompted, "interactive"

    return secrets.token_urlsafe(18), "generated"


def _write_bootstrap_secret(username: str, password: str) -> None:
    BOOTSTRAP_SECRET.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_SECRET.write_text(
        f"username={username}\npassword={password}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(BOOTSTRAP_SECRET, 0o600)
    except OSError:
        pass


def bootstrap_admin_if_needed() -> int:
    """
    Create initial super_admin when no credentials exist.
    Returns 0 on success / skip, 1 on failure.
    """
    if _admin_already_configured():
        return 0

    try:
        password, source = _resolve_initial_password()
    except ValueError as e:
        print(f"Admin bootstrap failed: {e}", file=sys.stderr)
        return 1

    if source == "dev_env":
        logger.warning(
            "Using AIFACTORY_DEV_BOOTSTRAP_PASSWORD for initial admin — dev/demo only; change immediately."
        )

    try:
        from web.backend.core.security import SecurityManager
        from web.backend.services import admin_users_store as aus

        security = SecurityManager()
        username = "admin"
        pwd_hash = security.hash_password(password)
        aus.USERS_PATH = _users_json_path()
        aus.ensure_legacy_admin_users_file()
        raw = aus._load_raw()
        if not raw.get("users"):
            raw["users"] = [
                {
                    "id": aus._new_id(),
                    "username": username,
                    "password_hash": pwd_hash,
                    "role": "super_admin",
                    "enabled": True,
                    "created_at": time.time(),
                    "updated_at": time.time(),
                }
            ]
            aus._save_raw(raw)

        legacy = {
            "username": username,
            "password_hash": pwd_hash,
            "hash_type": "pbkdf2_sha256",
            "totp_enabled": False,
            "created_at": time.time(),
        }
        ADMIN_JSON.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_JSON.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
        try:
            os.chmod(ADMIN_JSON, 0o600)
        except OSError:
            pass

        if source == "generated":
            _write_bootstrap_secret(username, password)
            print(
                f"Bootstrap admin created: username={username}. "
                f"One-time password written to {BOOTSTRAP_SECRET} (chmod 600). "
                "Change it after first login.",
                file=sys.stderr,
            )
        elif source == "interactive":
            print(
                f"Bootstrap admin created: username={username} (password set from console).",
                file=sys.stderr,
            )
        else:
            print(
                f"Dev bootstrap admin: username={username} (password from AIFACTORY_DEV_BOOTSTRAP_PASSWORD).",
                file=sys.stderr,
            )
        return 0
    except Exception as e:
        logger.error("Admin bootstrap failed: %s", e)
        print(f"Admin bootstrap failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(bootstrap_admin_if_needed())
