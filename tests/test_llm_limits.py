"""Tests for admin LLM limits YAML slice."""

from pathlib import Path

import yaml

from core import llm_limits as ll


def test_normalize_llm_limits_payload(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"llm": {"limits": {"daily_cost_cap_usd": 10}}}), encoding="utf-8")
    monkeypatch.setattr(ll, "_CONFIG_PATH", cfg)
    ll._CACHE_MTIME = None
    ll._CACHE_SLICE = None

    out = ll.normalize_llm_limits_payload({"daily_cost_cap_usd": 25, "max_requests_per_minute": 60})
    assert out is not None
    assert out["daily_cost_cap_usd"] == 25.0
    assert out["max_requests_per_minute"] == 60
