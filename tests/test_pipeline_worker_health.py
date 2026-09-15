from pipeline_worker import PipelineWorker


def test_worker_priorities_include_design_and_hardening():
    worker = PipelineWorker()
    assert worker._get_priority("design_critic") == 6
    assert worker._get_priority("hardening") == 6


def test_worker_health_and_readiness_snapshots():
    worker = PipelineWorker()
    health = worker.health_snapshot()
    ready = worker.readiness_snapshot()
    assert health["ok"] is True
    assert "uptime_sec" in health
    assert "ready" in ready
    assert "sqlite_ready" in ready
