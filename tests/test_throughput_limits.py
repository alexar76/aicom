"""Tests for pipeline throughput preset (general.local_high_throughput_enabled)."""

from pathlib import Path

import yaml

from core import throughput_limits as tl


def test_env_overrides_turbo(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"general": {"local_high_throughput_enabled": True}}), encoding="utf-8")
    monkeypatch.setattr(tl, "_CONFIG_PATH", cfg)
    tl._cache_mtime = None
    tl._cache_turbo = None

    monkeypatch.setenv("AIFACTORY_MAX_RUNNING_TASKS", "3")
    assert tl.effective_max_running_tasks() == 3
    monkeypatch.delenv("AIFACTORY_MAX_RUNNING_TASKS", raising=False)

    assert tl.effective_max_running_tasks() == 48
    assert tl.effective_task_executor_concurrency() == 24
    assert tl.effective_batch_pipeline_max_start_per_cycle() == 8
    assert tl.effective_batch_pipeline_active_limit() == 96
    assert tl.effective_llm_max_parallel_requests() == 32
    assert tl.effective_llm_min_interval_sec() == 0.0


def test_balanced_defaults(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"general": {"local_high_throughput_enabled": False}}), encoding="utf-8")
    monkeypatch.setattr(tl, "_CONFIG_PATH", cfg)
    tl._cache_mtime = None
    tl._cache_turbo = None

    for k in (
        "AIFACTORY_MAX_RUNNING_TASKS",
        "AIFACTORY_TASK_EXECUTOR_CONCURRENCY",
        "AIFACTORY_BATCH_PIPELINE_MAX_START_PER_CYCLE",
        "AIFACTORY_BATCH_PIPELINE_ACTIVE_LIMIT",
        "AIFACTORY_LLM_MAX_PARALLEL_REQUESTS",
        "AIFACTORY_LLM_MIN_INTERVAL_SEC",
    ):
        monkeypatch.delenv(k, raising=False)

    assert tl.effective_max_running_tasks() == 16
    assert tl.effective_task_executor_concurrency() == 6
    assert tl.effective_batch_pipeline_max_start_per_cycle() == 2
    assert tl.effective_batch_pipeline_active_limit() == 30
    assert tl.effective_llm_max_parallel_requests() == 8
    assert tl.effective_llm_min_interval_sec() == 0.05
