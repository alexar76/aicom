"""What an unpaid caller is told at the AIMarket invoke door.

A caller with no credential used to get `401 unauthorized`, which says the wrong thing: it
is not that we do not know them, it is that this capability is sold. `402` is the
protocol's answer (aimarket-protocol §7), and it is also what a federation hub reads as
evidence that the door is real — SKOPOS sells everything it has, so its admission assay had
nothing to run and nothing to read, and it sat in the operator queue while its own
catalogue said it was for sale.

A wrong credential still gets 401. Telling "pay me" from "that key is not valid" is the
whole point: one is an invitation, the other is a rejection.
"""

from __future__ import annotations

from typing import Any

from skopos.economy.capabilities import CAPABILITIES
from skopos.economy.config import EconomyConfig


def price_for(capability_id: str) -> float | None:
    for spec in CAPABILITIES:
        if spec.capability_id == (capability_id or "").strip():
            return float(spec.price_per_call_usd)
    return None


def payment_required_body(capability_id: str, cfg: EconomyConfig) -> dict[str, Any]:
    """A 402 that names the price and the ways to settle it.

    No x402 `accepts` block: SKOPOS does not verify on-chain payments itself, and quoting a
    settlement it cannot check would invite a buyer to pay into silence. The rails named
    here are the two that actually work — a hub channel, and an operator-issued key.
    """
    price = price_for(capability_id)
    ways: list[dict[str, Any]] = []
    if cfg.hub_url:
        hub = cfg.hub_url.rstrip("/")
        ways.append({
            "rail": "hub-channel",
            "hub": hub,
            "open": f"{hub}/ai-market/v2/channel/open",
            "invoke": f"{hub}/ai-market/v2/invoke",
        })
    ways.append({
        "rail": "api-key",
        "header": "X-API-Key",
        "detail": "operator-issued key for direct, non-federated access",
    })
    body: dict[str, Any] = {
        "success": False,
        "error": "payment_required",
        "detail": "this capability is sold; pay through a hub channel or present a key",
        "protocol_version": "v2",
        "product_id": cfg.product_id,
        "capability_id": (capability_id or "").strip(),
        "payment_ways": ways,
    }
    if price is not None:
        body["needed"] = price
        body["currency"] = "USD"
    return body
