"""
Production startup guard — refuse known weak credentials when ``AIFACTORY_PROD=1``.

Demo hosts (magic-ai-factory.com) should use ``AIFACTORY_DEMO_READONLY=1`` without
``AIFACTORY_PROD=1``. Self-hosted production must never ship with ``demo123`` / ``admin123``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from core.paths import admin_users_path, legacy_admin_path
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

KNOWN_INSECURE_PASSWORDS: frozenset[str] = frozenset(
    {"demo123", "admin123", "password", "changeme", "admin", "factory"}
)


def is_production_mode() -> bool:
    return os.environ.get("AIFACTORY_PROD", "").strip() == "1"


def _load_password_hashes() -> list[str]:
    hashes: list[str] = []
    users_path = Path(os.environ.get("ADMIN_USERS_PATH", str(admin_users_path())))
    if users_path.is_file():
        try:
            data = json.loads(users_path.read_text(encoding="utf-8"))
            for u in data.get("users") or []:
                if isinstance(u, dict) and u.get("password_hash"):
                    hashes.append(str(u["password_hash"]))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log_suppressed(logger, "prod guard users.json", exc_info=exc)
    legacy = legacy_admin_path()
    if legacy.is_file():
        try:
            cfg = json.loads(legacy.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("password_hash"):
                hashes.append(str(cfg["password_hash"]))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log_suppressed(logger, "prod guard admin.json", exc_info=exc)
    return hashes


def _admin_uses_insecure_password() -> str | None:
    """Return the matched weak password literal, or None."""
    hashes = _load_password_hashes()
    if not hashes:
        return None
    try:
        from web.backend.core.security import SecurityManager

        sec = SecurityManager()
        for weak in KNOWN_INSECURE_PASSWORDS:
            for h in hashes:
                if sec.verify_password(weak, h):
                    return weak
    except Exception as exc:
        logger.warning("prod_startup_guard: could not verify admin password: %s", exc)
    return None


def production_startup_issues() -> list[str]:
    """Collect blocking issues for production mode (empty = OK)."""
    if not is_production_mode():
        return []

    issues: list[str] = []

    dev_pw = (os.environ.get("AIFACTORY_DEV_BOOTSTRAP_PASSWORD") or "").strip()
    if dev_pw and dev_pw.lower() in KNOWN_INSECURE_PASSWORDS:
        issues.append(
            f"AIFACTORY_DEV_BOOTSTRAP_PASSWORD is a known demo password ({dev_pw!r}). "
            "Unset it or use a unique secret before AIFACTORY_PROD=1."
        )

    if os.environ.get("AIFACTORY_DEMO_READONLY", "").strip() == "1":
        issues.append(
            "AIFACTORY_PROD=1 together with AIFACTORY_DEMO_READONLY=1 is contradictory — "
            "use DEMO_READONLY only on intentional public demo hosts, not production."
        )

    weak = _admin_uses_insecure_password()
    if weak:
        issues.append(
            f"Admin account still uses a known weak password ({weak!r}). "
            "Change it via Settings or re-bootstrap before running with AIFACTORY_PROD=1."
        )

    # Payment: refuse production with stub verification
    if os.environ.get("AIFACTORY_PAYMENT_VERIFY_STUB", "1").strip() == "1":
        issues.append(
            "AIFACTORY_PAYMENT_VERIFY_STUB=1 in production mode — all payment "
            "transactions would be accepted without on-chain verification. "
            "Set AIFACTORY_PAYMENT_VERIFY_STUB=0 before running with AIFACTORY_PROD=1."
        )

    # Payment: refuse production without a configured recipient
    recipient = (os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "").strip()
    if not recipient or recipient.startswith("0x000000000000000000000000000000000000"):
        issues.append(
            "AIMARKET_PAYMENT_RECIPIENT is not set or is the zero address — "
            "real payments have nowhere to settle. Set a valid wallet address."
        )

    # Payment: refuse production testnet mode
    if os.environ.get("AIFACTORY_PAYMENT_TESTNET", "1").strip() == "1":
        issues.append(
            "AIFACTORY_PAYMENT_TESTNET=1 in production mode — testnet mode "
            "accepts demo transaction hashes. Set AIFACTORY_PAYMENT_TESTNET=0."
        )

    return issues


def assert_production_startup_safe(*, exit_on_failure: bool = True) -> None:
    issues = production_startup_issues()
    if not issues:
        return
    msg = "Production startup refused:\n  - " + "\n  - ".join(issues)
    logger.error(msg)
    if exit_on_failure:
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    raise RuntimeError(msg)
