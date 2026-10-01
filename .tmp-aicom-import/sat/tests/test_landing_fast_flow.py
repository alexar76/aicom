"""Tests for landing fast pipeline (mini-spec → architect → developer → QA)."""

from __future__ import annotations

import json

from orchestrator.landing_fast_flow import (
    agent_flow_for_product,
    is_landing_fast_product,
    landing_fast_agent_flow,
    resolve_style_preset,
    write_landing_mini_spec,
)


def test_landing_fast_flow_has_four_core_stages():
    flow = landing_fast_agent_flow()
    assert flow["IDEA_RECEIVED"] == ("__landing_spec__", "SPEC_WRITTEN")
    assert flow["SPEC_WRITTEN"] == ("landing_architect", "ARCH_DESIGNED")
    assert flow["ARCH_DESIGNED"] == ("landing_developer", "CODE_COMMITTED")
    assert flow["QA_TESTING"] == ("__complete__", "COMPLETED")


def test_agent_flow_switches_on_product_flag():
    full = {"landing_fast_path": False}
    fast = {"landing_fast_path": True}
    assert is_landing_fast_product(fast) is True
    assert is_landing_fast_product(full) is False
    assert agent_flow_for_product(fast)["IDEA_RECEIVED"][0] == "__landing_spec__"
    assert agent_flow_for_product(full)["IDEA_RECEIVED"][0] == "analyst"


def test_resolve_style_preset_by_id():
    preset = resolve_style_preset("neo-brutalist-day", product_id="p1", idea="CRM landing")
    assert preset["id"] == "neo-brutalist-day"
    assert "brutalist" in preset["title"].lower()


def test_write_landing_mini_spec(tmp_path):
    preset = resolve_style_preset(None, product_id="prod-fast-1", idea="Team analytics dashboard")
    spec = write_landing_mini_spec(
        "prod-fast-1",
        idea="Team analytics dashboard for B2B SaaS",
        preset=preset,
        data_root=tmp_path,
    )
    assert spec["delivery_profile"] == "marketing_landing"
    assert spec["style_preset"]["id"] == preset["id"]
    saved = json.loads((tmp_path / "specs" / "prod-fast-1" / "specification.json").read_text())
    assert saved["specification"]["product_name"]
