"""Unit tests for llm/cost_guard.py — budget tier calculation and model resolution."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from llm.cost_guard import (
    CostGuard,
    cost_guard_enabled,
    get_cost_guard,
    reset_cost_guard_for_tests,
)
from llm.usage_guard import reset_usage_guard_for_tests


def _make_guard_snapshot(day_spend=0.0, month_spend=0.0,
                         daily_cap=10.0, monthly_cap=100.0):
    """Return a MagicMock LLMUsageGuard with controlled snapshot()."""
    guard = MagicMock()
    guard.snapshot.return_value = {
        "day": "2026-01-01",
        "day_spend_usd": day_spend,
        "month": "2026-01",
        "month_spend_usd": month_spend,
        "requests_last_minute": 0,
        "daily_cost_cap_usd": daily_cap,
        "monthly_cost_cap_usd": monthly_cap,
        "max_requests_per_minute": 0,
        "pre_call_reserve_usd": 0.05,
    }
    return guard


def _setup_cost_guard(day_spend=0.0, month_spend=0.0,
                      daily_cap=10.0, monthly_cap=100.0) -> CostGuard:
    guard = _make_guard_snapshot(day_spend=day_spend, month_spend=month_spend,
                                 daily_cap=daily_cap, monthly_cap=monthly_cap)
    reset_usage_guard_for_tests(guard)
    reset_cost_guard_for_tests(None)
    return get_cost_guard()


class TestBudgetTier:
    def test_normal_when_under_threshold(self):
        cg = _setup_cost_guard(day_spend=2.0, daily_cap=10.0)  # 20%
        assert cg.budget_tier() == "normal"
        assert not cg.is_budget_tight()

    def test_tight_when_above_80_percent(self):
        cg = _setup_cost_guard(day_spend=8.5, daily_cap=10.0)  # 85%
        assert cg.budget_tier() == "tight"
        assert cg.is_budget_tight()

    def test_critical_when_above_95_percent(self):
        cg = _setup_cost_guard(day_spend=9.7, daily_cap=10.0)  # 97%
        assert cg.budget_tier() == "critical"
        assert cg.is_budget_tight()

    def test_monthly_cap_drives_tier(self):
        cg = _setup_cost_guard(day_spend=0.0, daily_cap=0.0,
                               month_spend=90.0, monthly_cap=100.0)  # 90% monthly
        assert cg.budget_tier() == "tight"

    def test_worst_cap_wins(self):
        cg = _setup_cost_guard(day_spend=9.0, daily_cap=10.0,   # 90% daily
                               month_spend=10.0, monthly_cap=100.0)  # 10% monthly
        assert cg.budget_tier() == "tight"  # daily drives it

    def test_no_caps_means_normal(self):
        cg = _setup_cost_guard(day_spend=100.0, daily_cap=0.0,
                               month_spend=1000.0, monthly_cap=0.0)
        assert cg.budget_tier() == "normal"

    def test_custom_thresholds_via_env(self, monkeypatch):
        monkeypatch.setenv("AIFACTORY_COST_GUARD_TIGHT_THRESHOLD", "0.50")
        monkeypatch.setenv("AIFACTORY_COST_GUARD_CRITICAL_THRESHOLD", "0.90")
        cg = _setup_cost_guard(day_spend=6.0, daily_cap=10.0)  # 60% — above 0.50
        assert cg.budget_tier() == "tight"


class TestResolveModel:
    AVAILABLE = {"heavy": "deepseek-chat", "light": "deepseek-chat", "budget": "deepseek-v3-lite"}

    def test_normal_returns_requested(self):
        cg = _setup_cost_guard(day_spend=2.0, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "code_generation", "deepseek-chat",
                                  available_models=self.AVAILABLE)
        assert result == "deepseek-chat"

    def test_tight_downgrades_non_critical(self):
        cg = _setup_cost_guard(day_spend=8.5, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "market_research", "deepseek-chat",
                                  available_models=self.AVAILABLE)
        assert result == "deepseek-chat"  # light == heavy for this provider

    def test_tight_preserves_critical_tasks(self):
        cg = _setup_cost_guard(day_spend=8.5, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "security_scan", "deepseek-chat",
                                  available_models=self.AVAILABLE)
        assert result == "deepseek-chat"  # critical tasks keep heavy

    def test_critical_downgrades_everything(self):
        cg = _setup_cost_guard(day_spend=9.8, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "security_scan", "deepseek-chat",
                                  available_models=self.AVAILABLE)
        assert result == "deepseek-v3-lite"  # budget model

    def test_critical_downgrades_qa(self):
        cg = _setup_cost_guard(day_spend=9.8, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "qa_testing", "deepseek-chat",
                                  available_models=self.AVAILABLE)
        assert result == "deepseek-v3-lite"

    def test_returns_requested_when_no_available_models(self):
        cg = _setup_cost_guard(day_spend=9.8, daily_cap=10.0)
        result = cg.resolve_model("deepseek", "code_generation", "deepseek-chat")
        assert result == "deepseek-chat"

    def test_budget_model_falls_back_to_light_then_heavy(self):
        cg = _setup_cost_guard(day_spend=9.8, daily_cap=10.0)
        # no budget key — should fall back to light
        models = {"heavy": "deepseek-chat", "light": "deepseek-flash"}
        result = cg.resolve_model("deepseek", "marketing_content", "deepseek-chat",
                                  available_models=models)
        assert result == "deepseek-flash"


class TestCostGuardEnabled:
    def test_disabled_when_no_caps(self):
        with (
            patch("llm.cost_guard.effective_llm_daily_cost_cap_usd", return_value=0.0),
            patch("llm.cost_guard.effective_llm_monthly_cost_cap_usd", return_value=0.0),
            patch.dict(os.environ, {}, clear=False),
        ):
            if "AIFACTORY_COST_GUARD_ENABLED" in os.environ:
                del os.environ["AIFACTORY_COST_GUARD_ENABLED"]
            assert not cost_guard_enabled()

    def test_enabled_when_daily_cap_set(self):
        with (
            patch("llm.cost_guard.effective_llm_daily_cost_cap_usd", return_value=10.0),
            patch("llm.cost_guard.effective_llm_monthly_cost_cap_usd", return_value=0.0),
            patch.dict(os.environ, {}, clear=False),
        ):
            if "AIFACTORY_COST_GUARD_ENABLED" in os.environ:
                del os.environ["AIFACTORY_COST_GUARD_ENABLED"]
            assert cost_guard_enabled()

    def test_explicitly_disabled_via_env(self):
        with patch.dict(os.environ, {"AIFACTORY_COST_GUARD_ENABLED": "false"}):
            assert not cost_guard_enabled()
