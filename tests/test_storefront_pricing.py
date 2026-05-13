"""Storefront USDT resolution (admin override vs sales vs marketing)."""

from __future__ import annotations

from web.backend.services.storefront_pricing import (
    DEFAULT_STOREFRONT_PRICE_USDT,
    checkout_usdt_from_sales_file,
    patch_admin_storefront_usdt,
    resolve_storefront_price_usdt,
)


def test_admin_override_wins_over_tiers_and_marketing():
    marketing = {"monetization_scheme": {"paid_tiers": [{"name": "Pro", "price_usd_monthly": 29.0}]}}
    sales = {
        "pricing": {
            "admin_storefront_usdt": 12.34,
            "usdt_price": 5.0,
            "tiers": [{"name": "Paid", "price_usdt": 7.0}],
        }
    }
    p, tier = resolve_storefront_price_usdt(marketing=marketing, sales_config_inner=sales)
    assert abs(p - 12.34) < 1e-6
    assert tier == "admin"


def test_sales_usdt_before_marketing_when_no_admin():
    marketing = {"monetization_scheme": {"paid_tiers": [{"name": "Pro", "price_usd_monthly": 29.0}]}}
    sales = {"pricing": {"usdt_price": 6.5}}
    p, tier = resolve_storefront_price_usdt(marketing=marketing, sales_config_inner=sales)
    assert abs(p - 6.5) < 1e-6
    assert tier == "crypto"


def test_checkout_file_reads_admin(tmp_path):
    pid = "prod-test-pricing"
    state_dir = tmp_path / "state" / pid
    state_dir.mkdir(parents=True)
    cfg = {
        "product_id": pid,
        "sales_data": {"pricing": {"admin_storefront_usdt": 8.0, "usdt_price": 3.0}},
    }
    import json

    (state_dir / "sales_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    got = checkout_usdt_from_sales_file(pid, data_root=tmp_path)
    assert abs(got - 8.0) < 1e-6


def test_patch_clear_admin(tmp_path):
    pid = "prod-patch-price"
    patch_admin_storefront_usdt(pid, admin_storefront_usdt=15.0, clear_admin_storefront_usdt=False, data_root=tmp_path)
    assert abs(checkout_usdt_from_sales_file(pid, data_root=tmp_path) - 15.0) < 1e-6
    patch_admin_storefront_usdt(pid, admin_storefront_usdt=None, clear_admin_storefront_usdt=True, data_root=tmp_path)
    assert checkout_usdt_from_sales_file(pid, data_root=tmp_path) == float(DEFAULT_STOREFRONT_PRICE_USDT)
