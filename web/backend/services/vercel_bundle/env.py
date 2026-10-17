"""Environment a deployed product runs with: SQLite path, product wallet, demo login, JWT
secret and the mesh endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path


def _sqlite_env() -> dict[str, str]:
    """Serverless filesystems are read-only outside /tmp."""
    path = "/tmp/product.db"
    url = f"sqlite:///{path}"
    return {
        "DATABASE_URL": url,
        "SQLALCHEMY_DATABASE_URI": url,
        "DB_PATH": path,
        "RELAY_DB_PATH": path,
    }


def wallet_env() -> dict[str, str]:
    """Wallet settings for a deployed product — off unless the operator opts in.

    A published product must work for a visitor with no wallet at all: the mesh
    grants a free trial allowance per caller, which is what a demo actually runs on.
    Binding a wallet is the operator's decision, made by setting
    ``AIFACTORY_PRODUCT_WALLET_ADDRESS`` (plus optionally ``..._CHAIN``) on the
    factory before publishing. Nothing here ever carries a private key: an address
    is configuration, a key would be custody.
    """
    address = os.environ.get("AIFACTORY_PRODUCT_WALLET_ADDRESS", "").strip()
    chain = os.environ.get("AIFACTORY_PRODUCT_WALLET_CHAIN", "base").strip() or "base"
    if not address:
        return {"WALLET_ENABLED": "0"}
    return {
        "WALLET_ENABLED": "1",
        "WALLET_ADDRESS": address,
        "WALLET_CHAIN": chain,
    }


def demo_auth_env() -> dict[str, str]:
    """Same demo login the live gate and sandbox preview use.

    Without these on the Vercel function, products seed ``operator@…`` (or nothing)
    while ``live_deployment_gate`` POSTs ``sandbox.demo@magic-ai-factory.com`` + the
    factory password → permanent 401 on /api/auth/login even when health is green.
    """
    from core.demo_identity import sandbox_demo_email
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    email = sandbox_demo_email()
    password = effective_sandbox_demo_password_for_compose()
    return {
        "SANDBOX_DEMO_EMAIL": email,
        "SANDBOX_DEMO_PASSWORD": password,
        "VITE_SANDBOX_DEMO_EMAIL": email,
        "VITE_SANDBOX_DEMO_PASSWORD": password,
    }


DEFAULT_ATLAS_PUBLIC_URL = "https://atlas.modelmarket.dev"
DEFAULT_HUB_PUBLIC_URL = "https://modelmarket.dev"


def mesh_env(product_id: str | None = None) -> dict[str, str]:
    """Public mesh endpoints a serverless product can actually reach.

    Generated products default ``atlas_base_url`` to ``http://localhost:8001``. That
    works in a compose sandbox next to ATLAS; on Vercel every advisory becomes
    ``Mesh unavailable: All connection attempts failed``. Point the function at the
    public ATLAS origin (override with ``AIFACTORY_ATLAS_PUBLIC_URL``).

    Paying participants: prefer a **runtime** session (``core.aimarket_participant`` +
    ``AIMARKET_WALLET_KEY`` / channel). Per-product overrides live at
    ``data/state/<product_id>/aimarket_participant.env`` so one Sentinel channel does
    not leak into every other deploy. ``ATLAS_AGENT_KEY`` is legacy identity only.
    """
    overrides: dict[str, str] = {}
    if product_id:
        try:
            from core.paths import resolve_data_root

            env_path = Path(resolve_data_root()) / "state" / product_id / "aimarket_participant.env"
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    overrides[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            overrides = {}

    def pick(*names: str, default: str = "") -> str:
        for name in names:
            if name in overrides and overrides[name]:
                return overrides[name]
            val = (os.environ.get(name) or "").strip()
            if val:
                return val
        return default

    atlas = pick(
        "AIFACTORY_ATLAS_PUBLIC_URL", "ATLAS_PUBLIC_URL", "ATLAS_BASE_URL", default=DEFAULT_ATLAS_PUBLIC_URL
    ).rstrip("/")
    hub = pick(
        "AIFACTORY_AIMARKET_HUB_URL", "AIMARKET_HUB_URL", "AIMARKET_BASE_URL", default=DEFAULT_HUB_PUBLIC_URL
    ).rstrip("/")
    agent_key = pick("AIFACTORY_ATLAS_AGENT_KEY", "ATLAS_AGENT_KEY", default="demo-atlas-key")
    visitor = pick(
        "AIFACTORY_AIMARKET_SANDBOX_VISITOR",
        "AIMARKET_SANDBOX_VISITOR",
        default=f"aicom-{product_id}" if product_id else "aicom-vercel-demo",
    )
    channel = pick("AIFACTORY_AIMARKET_PAYMENT_CHANNEL", "AIMARKET_PAYMENT_CHANNEL", "X_PAYMENT_CHANNEL")
    channel_secret = pick(
        "AIFACTORY_AIMARKET_PAYMENT_CHANNEL_SECRET",
        "AIMARKET_PAYMENT_CHANNEL_SECRET",
        "X_PAYMENT_CHANNEL_SECRET",
    )
    wallet_key = pick("AIFACTORY_PRODUCT_WALLET_KEY", "AIMARKET_WALLET_KEY", "SENTINEL_WALLET_KEY")
    wallet_addr = pick("AIFACTORY_PRODUCT_WALLET_ADDRESS", "AIMARKET_WALLET_ADDRESS", "WALLET_ADDRESS")
    out = {
        "ATLAS_BASE_URL": atlas or DEFAULT_ATLAS_PUBLIC_URL,
        "AIMARKET_HUB_URL": hub or DEFAULT_HUB_PUBLIC_URL,
        "AIMARKET_BASE_URL": hub or DEFAULT_HUB_PUBLIC_URL,
        "ATLAS_AGENT_KEY": agent_key or "demo-atlas-key",
        "AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
        "X_AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
    }
    if channel:
        out["AIMARKET_PAYMENT_CHANNEL"] = channel
        out["X_PAYMENT_CHANNEL"] = channel
    if channel_secret:
        out["AIMARKET_PAYMENT_CHANNEL_SECRET"] = channel_secret
        out["X_PAYMENT_CHANNEL_SECRET"] = channel_secret
    if wallet_key:
        out["AIMARKET_WALLET_KEY"] = wallet_key
    if wallet_addr:
        out["AIMARKET_WALLET_ADDRESS"] = wallet_addr
        out["WALLET_ADDRESS"] = wallet_addr
        out["WALLET_ENABLED"] = "1"
        out["WALLET_CHAIN"] = pick("WALLET_CHAIN", "AIMARKET_CHAIN", default="base") or "base"
    # Pass through remaining AIMARKET_* overrides (escrow channel id, hub address, etc.)
    for k, v in overrides.items():
        if not k.startswith("AIMARKET_") or not v or k in out:
            continue
        out[k] = v
    return out


_JWT_DEPS_MARKER = "# aicom-factory-jwt-identity"


def jwt_secret_env(product_id: str | None = None) -> dict[str, str]:
    """Stable JWT secret injected before the app imports Settings.

    Sentinel login signed with ``os.environ.setdefault(SECRET_KEY, sentinel-dev-…)``
    after ``get_settings()`` had already cached ``secret_key=dev-secret-key-change-me``.
    ``get_current_user`` then jose-decoded with Settings and every operator route
    answered ``Invalid token`` after a 200 login.
    """
    override = (os.environ.get("AIFACTORY_PRODUCT_JWT_SECRET") or "").strip()
    secret = override or f"aicom-demo-jwt:{product_id or 'default'}"
    return {
        "SECRET_KEY": secret,
        "JWT_SECRET": secret,
        "JWT_ALGORITHM": "HS256",
        "ALGORITHM": "HS256",
    }
