"""First-party API references curated by the ModelMarket operator.

CoinMarketCap was listed here until 2026-11-22. CMC support (ticket 1474981) declined any ModelMarket route for
its quotes on 2026-11-19 and on 2026-11-22 asked that ModelMarket not present CMC data or API access among its
offerings; the operator removed the reference."""

from __future__ import annotations

from aimarket_hub.semantic_search import normalize_text


_SERVICES = (
    ({
        "id": "tavily",
        "name": "Tavily",
        "description": "Advanced web search with ranked sources and snippets.",
        "documentation_url": "https://docs.tavily.com/documentation/machine-payments/x402",
        "endpoint": "https://x402.tavily.com/search",
        "method": "POST",
        "payment_networks": ("base",),
        "published_price_usd": 0.01,
        "price_basis": "per_request",
    }, ("web search", "поиск в интернете", "веб поиск", "busqueda web", "recherche web", "网页搜索")),
    ({
        "id": "laso",
        "name": "Laso",
        "description": "Non-reloadable U.S. prepaid card. Check merchant acceptance before loading the card.",
        "documentation_url": "https://docs.laso.finance/guides/usa-prepaid-card",
        "endpoint": "https://laso.finance/get-card",
        "method": "GET",
        "payment_networks": ("base", "solana"),
        "published_price_usd": 5,
        "price_basis": "minimum_load",
    }, ("prepaid card", "virtual card", "предоплачен", "виртуальн", "tarjeta prepago", "carte prepayee", "预付卡")),
)


def is_modelmarket_apex(hub_url: str) -> bool:
    return hub_url.rstrip("/") == "https://modelmarket.dev"


def external_references(intent: str = "", *, budget: float | None = None) -> list[dict]:
    """References for direct provider use, with prices taken from provider documentation."""
    query = normalize_text(intent[:500])
    return [
        {**service, "payment_protocol": "x402", "asset": "USDC",
         "payment_recipient": "provider", "hub_invoke": False}
        for service, aliases in _SERVICES
        if (budget is None or service["published_price_usd"] <= budget)
        and (not query or any(phrase in query for phrase in (service["id"], *aliases)))
    ]
