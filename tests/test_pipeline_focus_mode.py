"""Tests for pipeline focus mode and per-product pipeline pause."""

from __future__ import annotations

import pytest

from core.pipeline_product_pause import (
    get_factory_focus_product_id,
    is_product_pipeline_work_paused,
)
from web.backend.services.product_followup import (
    delete_followup,
    set_product_pipeline_on_hold,
)


@pytest.fixture(autouse=True)
def _clean_followup(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    yield


def test_focus_mode_pauses_non_focus_products():
    cfg = {"general": {"factory_focus_product_id": "prod-a"}}
    set_product_pipeline_on_hold("prod-b", False)
    assert is_product_pipeline_work_paused("prod-b", config=cfg) is True
    assert is_product_pipeline_work_paused("prod-a", config=cfg) is False


def test_manual_pipeline_hold_pauses_without_focus():
    set_product_pipeline_on_hold("prod-x", True)
    assert is_product_pipeline_work_paused("prod-x") is True
    delete_followup("prod-x")


def test_get_factory_focus_product_id_from_config():
    cfg = {"general": {"factory_focus_product_id": "prod-focus"}}
    assert get_factory_focus_product_id(config=cfg) == "prod-focus"


def test_focus_accepts_several_products():
    """An operator reworking two products should not have to pick one."""
    from core.pipeline_product_pause import get_factory_focus_product_ids

    cfg = {"general": {"factory_focus_product_id": "prod-a, prod-b"}}
    assert get_factory_focus_product_ids(config=cfg) == ["prod-a", "prod-b"]
    assert is_product_pipeline_work_paused("prod-a", config=cfg) is False
    assert is_product_pipeline_work_paused("prod-b", config=cfg) is False
    assert is_product_pipeline_work_paused("prod-c", config=cfg) is True


def test_focus_accepts_a_yaml_list():
    from core.pipeline_product_pause import get_factory_focus_product_ids

    cfg = {"general": {"factory_focus_product_id": ["prod-a", "prod-b"]}}
    assert get_factory_focus_product_ids(config=cfg) == ["prod-a", "prod-b"]


def test_no_focus_configured_pauses_nothing_by_focus():
    from core.pipeline_product_pause import (
        get_factory_focus_product_ids,
        is_factory_focus_mode_active,
    )

    cfg = {"general": {}}
    assert get_factory_focus_product_ids(config=cfg) == []
    assert is_factory_focus_mode_active(config=cfg) is False
    assert is_product_pipeline_work_paused("prod-any", config=cfg) is False


def test_suggest_focus_product_prefers_full_software():
    from web.backend.services.pipeline_focus import suggest_focus_product

    products = {
        "prod-landing": {
            "state": "DEV_FIXING",
            "delivery_profile": "marketing_landing",
            "quality_repair_round": 0,
        },
        "prod-full": {
            "state": "DEV_FIXING",
            "spec": {"delivery_profile": "full_software"},
            "quality_repair_round": 1,
        },
    }
    assert suggest_focus_product(products) == "prod-full"
