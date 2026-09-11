"""
Storefront / checkout USDT price resolution and admin override persistence.

Admin override lives in ``data/state/<product_id>/sales_config.json`` under
``sales_data.pricing.admin_storefront_usdt`` and wins over agent tiers and marketing hints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from core.paths import pipeline_json_path, resolve_data_root

DEFAULT_STOREFRONT_PRICE_USDT = 4.99
DEFAULT_LANDING_PRICE_USDT = 4.99
DEFAULT_FULL_SOFTWARE_PRICE_USDT = 9.99


def default_price_for_delivery_profile(delivery_profile: str | None) -> float:
    """Two-tier default checkout: landing ~$4.99, full_software ~$9.99."""
    from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile

    if normalize_delivery_profile(delivery_profile) == MARKETING_LANDING:
        return float(DEFAULT_LANDING_PRICE_USDT)
    return float(DEFAULT_FULL_SOFTWARE_PRICE_USDT)


def _coerce_positive_float(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if x > 0 else None
    if isinstance(v, str) and v.strip():
        try:
            x = float(v.strip())
            return x if x > 0 else None
        except ValueError:
            return None
    return None


def _paid_tier_price_usdt(pricing: dict[str, Any]) -> tuple[Optional[float], str]:
    tiers = pricing.get("tiers") or pricing.get("pricing_tiers")
    if not isinstance(tiers, list):
        return None, "professional"
    for t in tiers:
        if not isinstance(t, dict):
            continue
        tp = t.get("price_usdt") or t.get("price", 0)
        p = _coerce_positive_float(tp)
        if p is not None:
            name = str(t.get("name") or "paid").strip().lower() or "professional"
            return p, name
    return None, "professional"


def resolve_storefront_price_usdt(
    *,
    marketing: dict[str, Any],
    sales_config_inner: dict[str, Any],
    default_usdt: float | None = None,
    delivery_profile: str | None = None,
) -> tuple[float, str]:
    """
    Public card / product detail price (USDT) and a short tier label.

    Precedence:
    1. ``sales_data.pricing.admin_storefront_usdt`` (admin)
    2. ``sales_data.pricing.usdt_price`` (sales agent one-shot)
    3. First paid entry in ``pricing.tiers`` / ``pricing_tiers``
    4. Marketing ``monetization_scheme.paid_tiers[0].price_usd_monthly``
    5. ``default_usdt`` or delivery-profile tier default (landing $4.99 / full $9.99)
    """
    if default_usdt is None:
        default_usdt = default_price_for_delivery_profile(delivery_profile)
    pricing = sales_config_inner.get("pricing") if isinstance(sales_config_inner, dict) else None
    if not isinstance(pricing, dict):
        pricing = {}
    if not pricing and isinstance(sales_config_inner, dict):
        alt = sales_config_inner.get("pricing_tiers")
        if isinstance(alt, list):
            pricing = {"tiers": alt}

    admin_p = _coerce_positive_float(pricing.get("admin_storefront_usdt"))
    if admin_p is not None:
        return admin_p, "admin"

    agent_one = _coerce_positive_float(pricing.get("usdt_price"))
    if agent_one is not None:
        return agent_one, "crypto"

    tier_p, tier_name = _paid_tier_price_usdt(pricing)
    if tier_p is not None:
        return tier_p, tier_name

    monetization_scheme = marketing.get("monetization_scheme") if isinstance(marketing, dict) else None
    if isinstance(monetization_scheme, dict):
        paid_tiers = monetization_scheme.get("paid_tiers")
        if isinstance(paid_tiers, list) and paid_tiers:
            t0 = paid_tiers[0]
            if isinstance(t0, dict):
                m = _coerce_positive_float(t0.get("price_usd_monthly"))
                if m is not None:
                    name = str(t0.get("name") or "professional").strip().lower() or "professional"
                    return m, name

    return float(default_usdt), "professional"


def checkout_usdt_from_sales_file(
    product_id: str,
    *,
    data_root: Path | None = None,
    default_usdt: float | None = None,
    delivery_profile: str | None = None,
) -> float:
    """Checkout amount from ``sales_config.json`` only (no marketing file read)."""
    if default_usdt is None:
        if delivery_profile is None:
            p = _read_pipeline_product(product_id)
            if isinstance(p, dict):
                spec = p.get("specification") if isinstance(p.get("specification"), dict) else {}
                delivery_profile = str(
                    p.get("delivery_profile") or spec.get("delivery_profile") or ""
                )
        default_usdt = default_price_for_delivery_profile(delivery_profile)
    root = resolve_data_root(data_root)
    path = root / "state" / product_id / "sales_config.json"
    if not path.is_file():
        return float(default_usdt)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return float(default_usdt)
    inner = raw.get("sales_data") if isinstance(raw, dict) else None
    if not isinstance(inner, dict):
        inner = {}
    pricing = inner.get("pricing") if isinstance(inner.get("pricing"), dict) else {}
    admin_p = _coerce_positive_float(pricing.get("admin_storefront_usdt"))
    if admin_p is not None:
        return admin_p
    agent_one = _coerce_positive_float(pricing.get("usdt_price"))
    if agent_one is not None:
        return agent_one
    tier_p, _ = _paid_tier_price_usdt(pricing)
    if tier_p is not None:
        return tier_p
    return float(default_usdt)


def _read_pipeline_product(product_id: str) -> dict[str, Any] | None:
    path = pipeline_json_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    products = raw.get("products") if isinstance(raw, dict) else None
    if not isinstance(products, dict):
        return None
    p = products.get(product_id)
    return p if isinstance(p, dict) else None


def pilot_settlement_price_usdt(
    product_id: str,
    *,
    data_root: Path | None = None,
    default_usdt: float = DEFAULT_STOREFRONT_PRICE_USDT,
) -> float:
    """
    Authoritative checkout USDT for AI Market pilot on-chain settlement.
    Caller must not accept a client-supplied amount.
    """
    p = _read_pipeline_product(product_id)
    if not p:
        raise ValueError("product not found")
    state = str(p.get("state") or "").upper()
    if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
        raise ValueError("product not available for purchase")
    price = checkout_usdt_from_sales_file(
        product_id, data_root=data_root, default_usdt=default_usdt
    )
    if price <= 0:
        raise ValueError("product not purchasable")
    return float(price)


def read_sales_inner_and_pricing(product_id: str, *, data_root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(sales_data dict, pricing dict)`` from disk; empty dicts if missing."""
    root = resolve_data_root(data_root)
    path = root / "state" / product_id / "sales_config.json"
    if not path.is_file():
        return {}, {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}, {}
    inner = raw.get("sales_data") if isinstance(raw, dict) else None
    if not isinstance(inner, dict):
        inner = {}
    pricing = inner.get("pricing") if isinstance(inner.get("pricing"), dict) else {}
    return inner, pricing


def patch_admin_storefront_usdt(
    product_id: str,
    *,
    admin_storefront_usdt: float | None,
    clear_admin_storefront_usdt: bool,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """
    Merge or clear ``admin_storefront_usdt`` in ``sales_config.json``.

    Raises:
        ValueError: invalid amount
    """
    root = resolve_data_root(data_root)
    path = root / "state" / product_id / "sales_config.json"
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            raw = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            raw = {}

    sales_data = raw.get("sales_data")
    if not isinstance(sales_data, dict):
        sales_data = {}
    pricing = sales_data.get("pricing")
    if not isinstance(pricing, dict):
        pricing = {}

    if clear_admin_storefront_usdt:
        pricing.pop("admin_storefront_usdt", None)
    elif admin_storefront_usdt is not None:
        v = float(admin_storefront_usdt)
        if v <= 0 or v > 1_000_000:
            raise ValueError("admin_storefront_usdt must be between 0 exclusive and 1000000")
        pricing["admin_storefront_usdt"] = round(v, 2)

    sales_data["pricing"] = pricing
    raw["sales_data"] = sales_data
    raw.setdefault("product_id", product_id)
    if "created_at" not in raw:
        import time

        raw["created_at"] = time.time()
    raw.setdefault("agent", raw.get("agent") or "admin")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    effective = checkout_usdt_from_sales_file(product_id, data_root=root)
    return {
        "admin_storefront_usdt": pricing.get("admin_storefront_usdt"),
        "storefront_checkout_usdt": effective,
    }
