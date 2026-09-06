"""
Public demo instance guard.

When ``AIFACTORY_DEMO_READONLY=1`` (e.g. magic-ai-factory.com), block operations
that would let visitors corrupt shared demo state or exfiltrate secrets. Admin
login is passwordless for the shared ``admin`` account (readonly guard still applies).
"""

from __future__ import annotations

import os

from fastapi import HTTPException


def is_public_demo() -> bool:
    return os.environ.get("AIFACTORY_DEMO_READONLY", "").strip() == "1"


def allows_passwordless_admin_login() -> bool:
    """Shared demo hosts: admin enters without a password (readonly guard still applies)."""
    return is_public_demo()


def require_not_public_demo(action: str) -> None:
    if is_public_demo():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Public demo mode: {action} is disabled. "
                "Self-host your own instance for full owner controls."
            ),
        )


def public_demo_status() -> dict:
    on = is_public_demo()
    return {
        "public_demo": on,
        "public_demo_readonly": on,
        "allows_passwordless_admin_login": allows_passwordless_admin_login(),
        "blocks_factory_backup": on,
        "blocks_factory_restore": on,
        "blocks_admin_password_change": on,
        "blocks_admin_user_management": on,
        "blocks_platform_settings_save": on,
        "blocks_published_site_head_html_save": on,
        "allows_factory_on_hold_toggle": True,
    }
