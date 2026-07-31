"""AI Market Protocol v1 — discovery, schema, HTTP 402 payments, composition."""

from web.backend.services.ai_market_protocol.catalog import (
    build_manifest,
    get_capability,
    list_capabilities,
    list_shipped_products,
    parse_capability_ref,
)
from web.backend.services.ai_market_protocol.discovery import discover_capabilities
from web.backend.services.ai_market_protocol.pricing import quote_capability_price
from web.backend.services.ai_market_protocol.channels import close_channel, open_channel
from web.backend.services.ai_market_protocol.invoke import invoke_capability_v1
from web.backend.services.ai_market_protocol.pipelines import execute_pipeline
from web.backend.services.ai_market_protocol.receipts import get_receipt
from web.backend.services.ai_market_protocol.stats import append_stat, list_recent_stats
from web.backend.services.ai_market_protocol.wellknown import build_well_known

__all__ = [
    "build_well_known",
    "build_manifest",
    "list_shipped_products",
    "list_capabilities",
    "get_capability",
    "parse_capability_ref",
    "discover_capabilities",
    "quote_capability_price",
    "open_channel",
    "close_channel",
    "invoke_capability_v1",
    "execute_pipeline",
    "get_receipt",
    "append_stat",
    "list_recent_stats",
]
