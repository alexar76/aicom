"""Dashboard password policy — validation helpers (no Streamlit)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Align with factory prod guard; lowercase compare for user input.
KNOWN_WEAK_PASSWORDS = frozenset(
    {
        "demo123",
        "admin123",
        "password",
        "password123",
        "changeme",
        "admin",
        "factory",
        "skopos",
        "skopos123",
        "dashboard",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "letmein",
    }
)

_DEFAULT_MIN_LENGTH = 12


@dataclass(frozen=True)
class PasswordRule:
    key: str
    passed: bool


def min_password_length() -> int:
    raw = os.environ.get("SKOPOS_DASHBOARD_PASSWORD_MIN_LENGTH", str(_DEFAULT_MIN_LENGTH))
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_MIN_LENGTH
    return max(8, min(128, n))


def password_rules(password: str) -> list[PasswordRule]:
    pwd = password or ""
    min_len = min_password_length()
    lowered = pwd.lower()
    return [
        PasswordRule("auth.policy.min_length", len(pwd) >= min_len),
        PasswordRule("auth.policy.has_letter", bool(re.search(r"[A-Za-z]", pwd))),
        PasswordRule("auth.policy.has_digit", bool(re.search(r"\d", pwd))),
        PasswordRule(
            "auth.policy.not_weak",
            lowered not in KNOWN_WEAK_PASSWORDS and pwd.lower() not in {"skopos", "dashboard"},
        ),
    ]


def validate_dashboard_password(password: str) -> tuple[bool, list[str]]:
    """Return (ok, list of failing i18n keys)."""
    failed = [rule.key for rule in password_rules(password) if not rule.passed]
    return (not failed, failed)


def configured_password_meets_policy() -> tuple[bool, list[str]]:
    # A DB-stored hash was validated against the policy when it was set, and the
    # plaintext is not recoverable — trust it. Only the legacy env plaintext can
    # still be re-checked here.
    try:
        from skopos.auth_store import dashboard_hash_set

        if dashboard_hash_set():
            return True, []
    except Exception:
        pass
    pwd = os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip()
    if not pwd:
        return True, []
    return validate_dashboard_password(pwd)


def password_strength_label(passed_count: int, total: int = 4) -> str:
    if passed_count >= total:
        return "strong"
    if passed_count >= 3:
        return "good"
    if passed_count >= 2:
        return "fair"
    return "weak"
