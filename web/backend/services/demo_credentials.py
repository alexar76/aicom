"""Shared defaults for sandbox demo login (compose preview env injection)."""

from __future__ import annotations

import os

# Historically documented; anyone who still sets this on the factory host gets the admin warning.
LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD = "SandboxDemo!2026"

# When `AIFACTORY_SANDBOX_DEMO_PASSWORD` is unset, docker-compose substitutes this value.
# MUST stay in sync with `docker-compose.yml` → `app.environment.AIFACTORY_SANDBOX_DEMO_PASSWORD`.
DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD = "AfSc7xK9mR2nL4vP8qW1jH0fT5dB3cZyEu"

# Backward compat for tests / imports (same as legacy public demo password).
DEFAULT_SANDBOX_DEMO_PASSWORD = LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD


def sandbox_demo_password_uses_default() -> bool:
    """True when demo login is missing or still uses the well-known legacy password."""
    raw = (os.environ.get("AIFACTORY_SANDBOX_DEMO_PASSWORD") or "").strip()
    if not raw:
        return True
    return raw == LEGACY_PUBLIC_SANDBOX_DEMO_PASSWORD


def effective_sandbox_demo_password_for_compose() -> str:
    """Password injected into generated compose previews; never empty."""
    raw = (os.environ.get("AIFACTORY_SANDBOX_DEMO_PASSWORD") or "").strip()
    if raw:
        return raw
    return DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD
