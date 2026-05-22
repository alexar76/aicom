"""Root discovery manifest."""

from __future__ import annotations

from typing import Any

from web.backend.services.ai_market_protocol.catalog import list_capabilities, list_shipped_products
from web.backend.services.ai_market_protocol.config import base_public_url, pilot_tuple, protocol_versions
from web.backend.services.ai_market_protocol.signing import public_key_b64


def build_well_known() -> dict[str, Any]:
    cfg = pilot_tuple()
    base = base_public_url()
    return {
        "name": "Magic AI-Factory AI Market",
        "mcp_endpoint": f"{base}/ai-market/mcp",
        "manifest_url": f"{base}/ai-market/manifest",
        "products_count": len(list_shipped_products()),
        "capabilities_count": len(list_capabilities()),
        "supported_chains": [cfg["chain"]],
        "supported_tokens": [cfg["token"]],
        "protocol_versions": protocol_versions(),
        "signer_public_key": public_key_b64(),
    }
