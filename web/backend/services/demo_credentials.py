"""Shared defaults for sandbox demo login (compose preview env injection)."""

from __future__ import annotations

import os
from pathlib import Path

from core.paths import secrets_dir

# Historically documented; anyone who still sets this on the factory host gets the admin warning.
LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD = "SandboxDemo!2026"

# Removed from docker-compose.yml — kept for tests that assert legacy detection.
DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD = "AfSc7xK9mR2nL4vP8qW1jH0fT5dB3cZyEu"

DEFAULT_SANDBOX_DEMO_PASSWORD = LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD

_SANDBOX_PW_FILE = Path(
    os.environ.get(
        "AIFACTORY_SANDBOX_DEMO_PASSWORD_FILE",
        str(secrets_dir() / "sandbox_demo_password"),
    )
)


def _password_from_file() -> str:
    try:
        if _SANDBOX_PW_FILE.is_file():
            return _SANDBOX_PW_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def sandbox_demo_password_uses_default() -> bool:
    """True when demo login is missing or still uses a well-known legacy password."""
    raw = (os.environ.get("AIFACTORY_SANDBOX_DEMO_PASSWORD") or "").strip() or _password_from_file()
    if not raw:
        return True
    return raw in (
        LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD,
        DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD,
    )


def effective_sandbox_demo_password_for_compose() -> str:
    """Password injected into generated compose previews; never empty."""
    raw = (os.environ.get("AIFACTORY_SANDBOX_DEMO_PASSWORD") or "").strip() or _password_from_file()
    if raw:
        return raw
    # Last resort for workers started outside entrypoint (should not happen in Docker).
    import secrets

    return secrets.token_urlsafe(24)
