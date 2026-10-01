"""AI Market pilot settlement — server-side price (no client amount)."""

from __future__ import annotations

import json

import pytest


def test_pilot_settlement_price_from_sales_config(tmp_path, monkeypatch):
    data = tmp_path / "data"
    pid = "prod-abc123def456"
    (data / "state" / pid).mkdir(parents=True)
    (data / "state" / pid / "sales_config.json").write_text(
        json.dumps({"sales_data": {"pricing": {"admin_storefront_usdt": 99.5}}}),
        encoding="utf-8",
    )
    pipeline = data / "state" / "pipeline.json"
    pipeline.write_text(
        json.dumps(
            {
                "products": {
                    pid: {"state": "COMPLETED", "name": "Test SKU"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))

    from web.backend.services.storefront_pricing import pilot_settlement_price_usdt

    price = pilot_settlement_price_usdt(pid, data_root=data)
    assert price == 99.5


def test_pilot_settlement_rejects_unavailable_product(tmp_path, monkeypatch):
    data = tmp_path / "data"
    pid = "prod-abc123def456"
    pipeline = data / "state" / "pipeline.json"
    pipeline.parent.mkdir(parents=True)
    pipeline.write_text(
        json.dumps({"products": {pid: {"state": "DRAFT", "name": "Draft"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))

    from web.backend.services.storefront_pricing import pilot_settlement_price_usdt

    with pytest.raises(ValueError, match="not available"):
        pilot_settlement_price_usdt(pid, data_root=data)
