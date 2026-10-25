"""
Persistent admin panel user accounts (password hash + role).
Stored in JSON alongside legacy admin.json for backward compatibility.
"""

from __future__ import annotations

import json
import fcntl
import functools
import logging
import os
import re
import time
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from core.paths import admin_users_path, legacy_admin_path
from core.json_state import write_json_atomic

logger = logging.getLogger(__name__)

USERS_PATH = admin_users_path()
LEGACY_ADMIN_PATH = legacy_admin_path()

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,64}$")
_mutation_lock = threading.RLock()


def _serialized_mutation(function):
    """Serialize the complete read/change/replace across threads and workers.

    Atomic rename protects readers from partial JSON, but alone still lets a
    concurrent account update overwrite a committed disable/password/session change.
    """
    @functools.wraps(function)
    def locked(*args, **kwargs):
        with _mutation_lock:
            USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(str(USERS_PATH) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                return function(*args, **kwargs)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
    return locked


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _load_raw() -> dict[str, Any]:
    if not USERS_PATH.exists():
        return {"version": 1, "users": []}
    try:
        data = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "users": []}
        users = data.get("users")
        if not isinstance(users, list):
            users = []
        return {"version": int(data.get("version") or 1), "users": users}
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.warning("Could not read admin users store: %s", e)
        return {"version": 1, "users": []}


def _save_raw(data: dict[str, Any]) -> None:
    write_json_atomic(USERS_PATH, data, mode=0o600)


@_serialized_mutation
def ensure_legacy_admin_users_file() -> None:
    """Seed admin_users.json from legacy admin.json when the user list is empty."""
    raw = _load_raw()
    if raw.get("users"):
        return
    if not LEGACY_ADMIN_PATH.exists():
        return
    try:
        legacy = json.loads(LEGACY_ADMIN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return
    pwd_hash = legacy.get("password_hash") or ""
    if not pwd_hash:
        return
    username = str(legacy.get("username") or "admin").strip().lower()
    store = {
        "version": 1,
        "users": [
            {
                "id": _new_id(),
                "username": username,
                "password_hash": pwd_hash,
                "role": "super_admin",
                "enabled": True,
                "created_at": _now(),
                "session_version": uuid.uuid4().hex,
            }
        ],
    }
    _save_raw(store)
    logger.info("Seeded admin_users.json from legacy admin.json (user=%s)", username)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username):
        raise ValueError(
            "Username must be 3–64 characters: letters, digits, underscore, dot, hyphen"
        )


def list_users_public() -> list[dict[str, Any]]:
    """Users without password hashes."""
    raw = _load_raw()
    out: list[dict[str, Any]] = []
    for u in raw.get("users", []):
        if not isinstance(u, dict):
            continue
        out.append(
            {
                "id": u.get("id"),
                "username": u.get("username"),
                "role": u.get("role") or "viewer",
                "enabled": bool(u.get("enabled", True)),
                "created_at": u.get("created_at"),
            }
        )
    return out


def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    un = normalize_username(username)
    for u in _load_raw().get("users", []):
        if not isinstance(u, dict):
            continue
        if str(u.get("username") or "").lower() == un:
            return u
    return None


def get_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    for u in _load_raw().get("users", []):
        if isinstance(u, dict) and str(u.get("id")) == user_id:
            return u
    return None


@_serialized_mutation
def create_user(
    *,
    username: str,
    password_hash: str,
    role: str,
) -> dict[str, Any]:
    validate_username(username)
    un = normalize_username(username)
    raw = _load_raw()
    users = raw.setdefault("users", [])
    for u in users:
        if isinstance(u, dict) and str(u.get("username") or "").lower() == un:
            raise ValueError("Username already exists")
    row = {
        "id": _new_id(),
        "username": un,
        "password_hash": password_hash,
        "role": role,
        "enabled": True,
        "created_at": _now(),
        "session_version": uuid.uuid4().hex,
    }
    users.append(row)
    _save_raw(raw)
    logger.info("Created admin user %s role=%s", un, role)
    return row


@_serialized_mutation
def update_user(
    user_id: str,
    *,
    role: Optional[str] = None,
    enabled: Optional[bool] = None,
    password_hash: Optional[str] = None,
) -> dict[str, Any]:
    raw = _load_raw()
    users = raw.setdefault("users", [])
    found: Optional[dict[str, Any]] = None
    for u in users:
        if isinstance(u, dict) and str(u.get("id")) == user_id:
            found = u
            break
    if not found:
        raise LookupError("User not found")

    def _other_super_admins() -> int:
        return sum(
            1
            for u in users
            if isinstance(u, dict)
            and u is not found
            and str(u.get("role")) == "super_admin"
            and u.get("enabled", True)
        )

    if role is not None:
        old_role = str(found.get("role"))
        new_role = role
        if old_role == "super_admin" and new_role != "super_admin":
            if found.get("enabled", True) and _other_super_admins() < 1:
                raise ValueError("Cannot demote the last super_admin")
        found["role"] = new_role

    if enabled is not None:
        if not enabled and str(found.get("role")) == "super_admin":
            if _other_super_admins() < 1:
                raise ValueError("Cannot disable the last super_admin")
        found["enabled"] = bool(enabled)

    if password_hash is not None:
        found["password_hash"] = password_hash

    # Rotating on each security mutation also prevents an old session reviving
    # when an account is re-enabled or its former role/password is restored.
    if role is not None or enabled is not None or password_hash is not None:
        found["session_version"] = uuid.uuid4().hex

    _save_raw(raw)
    return found


@_serialized_mutation
def delete_user(user_id: str) -> None:
    raw = _load_raw()
    users_list = raw.setdefault("users", [])
    victim: Optional[dict[str, Any]] = None
    kept: list[dict[str, Any]] = []
    for u in users_list:
        if not isinstance(u, dict):
            continue
        if str(u.get("id")) == user_id:
            victim = u
        else:
            kept.append(u)
    if not victim:
        raise LookupError("User not found")
    if str(victim.get("role")) == "super_admin":
        raise ValueError("Cannot delete a super_admin account")
    raw["users"] = kept
    _save_raw(raw)
    logger.info("Deleted admin user id=%s", user_id)
