"""The demo identity the factory hands to every generated product.

Generated backends validate emails with pydantic ``EmailStr`` (email-validator),
which **rejects reserved/special-use domains** — ``.local``, ``.test``,
``.invalid``, ``.localhost``. The factory used to seed demo users at
``sandbox.demo@aicom.local``, so the very first thing a reviewer did in the
sandbox — log in — returned HTTP 500 from the product's own serializer:

    value is not a valid email address: The part after the @-sign is a
    special-use or reserved name that cannot be used with email.

Every product that models users with ``EmailStr`` inherited that failure. The
address the factory injects must therefore be a syntactically ordinary one, and
any operator-configured address on a reserved TLD is repaired here rather than
propagated into a hundred generated apps.
"""

from __future__ import annotations

import os

# RFC 2606 / RFC 6761 reserved names that email-validator refuses.
SPECIAL_USE_TLDS = frozenset({"local", "localhost", "test", "invalid", "onion", "arpa"})

DEFAULT_DEMO_DOMAIN = "magic-ai-factory.com"
DEFAULT_DEMO_EMAIL = f"sandbox.demo@{DEFAULT_DEMO_DOMAIN}"


def is_special_use_email(email: str) -> bool:
    """True when the address sits on a reserved TLD an email validator rejects."""
    _, _, domain = (email or "").partition("@")
    if not domain:
        return False
    return domain.rsplit(".", 1)[-1].strip().lower() in SPECIAL_USE_TLDS


def sane_demo_email(email: str | None, *, default: str = DEFAULT_DEMO_EMAIL) -> str:
    """Return a demo address that ``EmailStr`` will accept.

    Keeps the operator's local-part when only the domain is unusable, so
    ``sandbox.demo@aicom.local`` becomes ``sandbox.demo@magic-ai-factory.com``.
    """
    raw = (email or "").strip()
    if not raw:
        return default
    if "@" not in raw:
        return default
    if not is_special_use_email(raw):
        return raw
    local = raw.split("@", 1)[0].strip() or default.split("@", 1)[0]
    return f"{local}@{DEFAULT_DEMO_DOMAIN}"


def sandbox_demo_email() -> str:
    """The demo login address injected into sandbox previews."""
    return sane_demo_email(os.environ.get("AIFACTORY_SANDBOX_DEMO_EMAIL"))
