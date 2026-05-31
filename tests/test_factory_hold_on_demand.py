"""Factory hold: env hard-stop vs config soft-hold, and on-demand classification.

Under a *soft* hold (config `general.factory_on_hold`) the pipeline worker keeps
advancing explicitly-requested on-demand products (admin "New product", guest
fast-path landings) while pausing autonomous + post-ship work. The env
`AIFACTORY_FACTORY_ON_HOLD=1` is a hard kill switch that pauses everything.
"""

from __future__ import annotations

import pytest

from core.factory_hold import is_factory_hard_stopped, is_factory_on_hold
from core.product_origin import is_on_demand_product


def test_on_demand_explicit_marker():
    assert is_on_demand_product({"on_demand": True}) is True
    assert is_on_demand_product({"on_demand": False}) is False
    assert is_on_demand_product({}) is False


def test_on_demand_landing_fast_path():
    # Guest/admin fast-path landings are always human-requested.
    assert is_on_demand_product({"landing_fast_path": True}) is True


def test_on_demand_guest_tag_fallback():
    assert is_on_demand_product({"tags": ["guest-landing", "marketing-landing"]}) is True
    assert is_on_demand_product({"tags": ["autonomous", "saas"]}) is False


def test_on_demand_rejects_non_dict():
    assert is_on_demand_product(None) is False
    assert is_on_demand_product("prod-1") is False


def test_autonomous_product_is_not_on_demand():
    # A Director/Discovery product carries none of the on-demand signals.
    autonomous = {"id": "p", "idea": "x", "state": "IDEA_RECEIVED", "tags": ["autonomous"]}
    assert is_on_demand_product(autonomous) is False


def test_env_hard_stop(monkeypatch):
    monkeypatch.setenv("AIFACTORY_FACTORY_ON_HOLD", "1")
    assert is_factory_hard_stopped() is True
    # Hard stop also reads as "on hold" (superset).
    assert is_factory_on_hold() is True


def test_env_hard_stop_off(monkeypatch):
    monkeypatch.delenv("AIFACTORY_FACTORY_ON_HOLD", raising=False)
    assert is_factory_hard_stopped() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On"])
def test_env_hard_stop_truthy_values(monkeypatch, val):
    monkeypatch.setenv("AIFACTORY_FACTORY_ON_HOLD", val)
    assert is_factory_hard_stopped() is True


def test_config_soft_hold_is_not_hard_stop(monkeypatch):
    # Config hold via explicit config dict; env unset → soft hold, not a hard stop.
    monkeypatch.delenv("AIFACTORY_FACTORY_ON_HOLD", raising=False)
    cfg = {"general": {"factory_on_hold": True}}
    assert is_factory_on_hold(config=cfg) is True
    assert is_factory_hard_stopped() is False
