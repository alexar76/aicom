"""Optional AIMarket consumer — buy ecosystem services when Hub is configured."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import EconomyConfig

logger = logging.getLogger("skopos.economy.consumer")


def hub_available(cfg: EconomyConfig) -> bool:
    return bool(cfg.hub_url)


def hub_search(cfg: EconomyConfig, *, intent: str, budget: float = 1.0, limit: int = 5) -> list[dict[str, Any]]:
    """Free read — discover capabilities on the configured Hub (no wallet required)."""
    if not cfg.hub_url:
        return []
    url = cfg.hub_url.rstrip("/") + "/ai-market/v2/search"
    try:
        resp = requests.get(
            url,
            params={"intent": intent, "budget": budget, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        matches = data.get("matches")
        return matches if isinstance(matches, list) else []
    except Exception as exc:
        logger.debug("hub search failed: %s", type(exc).__name__)
        return []


def try_auto_register(cfg: EconomyConfig) -> None:
    """Best-effort Hub supply registration — never blocks SKOPOS startup."""
    if not cfg.enabled or not cfg.auto_register or not cfg.hub_url or not cfg.publish_token:
        return
    from .manifest import build_supply_manifest

    url = cfg.hub_url.rstrip("/") + "/ai-market/v2/supply/register"
    headers = {
        "Authorization": f"Bearer {cfg.publish_token}",
        "Content-Type": "application/json",
    }
    for manifest in build_supply_manifest(cfg):
        try:
            resp = requests.post(url, json=manifest, headers=headers, timeout=20)
            if resp.status_code >= 400:
                logger.warning(
                    "AIMarket register %s: HTTP %s",
                    manifest.get("capability_id"),
                    resp.status_code,
                )
            else:
                logger.info("AIMarket registered %s", manifest.get("capability_id"))
        except Exception as exc:
            logger.warning("AIMarket register failed: %s", type(exc).__name__)
