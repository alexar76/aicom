"""
Hand-crafted OpenAPI metadata (tags, descriptions) for FastAPI auto-generated schema.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_DESCRIPTION = """
## AI-Factory v2.1 — HTTP API

Autonomous product pipeline, admin console, storefront commerce, and sandbox previews.

### Auth
- **Admin:** `POST /api/admin/auth/login` → JWT in `access_token` cookie (+ `X-CSRF-Token` for mutating routes).
- **Customer:** Bearer token from `POST /api/customer/register` or login flows.

### Pipeline
Products advance through agent stages (analyst → pm → architect → developer → qa → …).
State is persisted under `data/state/` (SQLite or JSON). The **pipeline worker** processes the task queue.

### Docs
- This page: Swagger UI
- Operator guide: `docs/admin-guide.md`, `docs/security.md`
"""


OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "admin-auth", "description": "Admin login, 2FA (TOTP / WebAuthn passkeys), session cookies."},
    {"name": "admin", "description": "Dashboard, pipeline control, LLM providers, audit logs, agent handoffs."},
    {"name": "products", "description": "Public and authenticated product catalog endpoints."},
    {"name": "payment", "description": "Stripe and on-chain payment intents, webhooks."},
    {"name": "customer", "description": "Storefront customer accounts and entitlements."},
    {"name": "sandbox", "description": "Isolated preview of generated apps (Docker-hardened when configured)."},
    {"name": "marketing", "description": "Site analytics snippets and public marketing helpers."},
    {"name": "telemetry", "description": "Usage events and operational metrics ingestion."},
    {"name": "health", "description": "Liveness and version probes."},
]


def apply_openapi_metadata(app: FastAPI) -> None:
    """Attach richer tag list and description to the generated OpenAPI schema."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=API_DESCRIPTION,
            routes=app.routes,
        )
        schema["tags"] = OPENAPI_TAGS
        schema.setdefault("info", {})["contact"] = {
            "name": "AI-Factory",
            "url": "https://github.com/alexar76/aicom",
        }
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
