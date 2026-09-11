"""Pipeline cost optimized mode — spend caps, repair limits, post-ship refresh."""

from core.quality_settings import (
    LEGACY_QUALITY_PRESETS,
    OPTIMIZED_QUALITY_PRESETS,
    apply_pipeline_cost_preset,
    bump_quality_cache_after_config_write,
    monitoring_dev_refresh_enabled,
    pipeline_cost_optimized,
)


def test_apply_pipeline_cost_preset_optimized():
    q = apply_pipeline_cost_preset(optimized=True)
    for k, v in OPTIMIZED_QUALITY_PRESETS.items():
        assert q[k] == v


def test_apply_pipeline_cost_preset_legacy():
    q = apply_pipeline_cost_preset(optimized=False)
    for k, v in LEGACY_QUALITY_PRESETS.items():
        assert q[k] == v


def test_monitoring_dev_refresh_default_off(monkeypatch):
    monkeypatch.delenv("AIFACTORY_MONITORING_DEV_REFRESH_ENABLED", raising=False)
    bump_quality_cache_after_config_write()
    assert monitoring_dev_refresh_enabled() is False


def test_monitoring_dev_refresh_env_override(monkeypatch):
    monkeypatch.setenv("AIFACTORY_MONITORING_DEV_REFRESH_ENABLED", "1")
    assert monitoring_dev_refresh_enabled() is True


def test_landing_repair_cap_from_yaml(monkeypatch):
    monkeypatch.delenv("AIFACTORY_LANDING_MAX_QUALITY_LOOPS", raising=False)
    monkeypatch.delenv("AIFACTORY_MAX_QUALITY_LOOPS", raising=False)
    from core.quality_settings import max_pipeline_repair_rounds_for_delivery_profile

    cap = max_pipeline_repair_rounds_for_delivery_profile("marketing_landing")
    assert cap == OPTIMIZED_QUALITY_PRESETS["max_pipeline_repair_rounds_landing"]


def test_pipeline_cost_optimized_defaults_true():
    assert pipeline_cost_optimized() is True
