"""Previews that died with the app process must not hold the concurrency cap."""

from web.backend.services.sandbox_guards import mark_orphaned_uvicorn_previews


def test_uvicorn_preview_is_reaped_after_restart():
    reap = mark_orphaned_uvicorn_previews
    active = {
        "sandbox-a": {"status": "running", "backend_preview_port": 32773},
        "sandbox-b": {"status": "running", "backend_preview_port": 41111},
    }
    assert reap(active) == 2
    assert all(v["status"] == "stopped" for v in active.values())
    assert active["sandbox-a"]["stopped_reason"] == "orphaned_by_restart"


def test_compose_previews_survive_a_restart():
    reap = mark_orphaned_uvicorn_previews
    active = {"sandbox-c": {"status": "running", "compose_proxy_port": 8123}}
    assert reap(active) == 0
    assert active["sandbox-c"]["status"] == "running"


def test_already_stopped_and_portless_ready_entries_are_untouched():
    reap = mark_orphaned_uvicorn_previews
    active = {
        "sandbox-d": {"status": "stopped", "backend_preview_port": 1234},
        "sandbox-e": {"status": "running", "startup_phase": "ready"},
        "sandbox-f": {"status": "running"},
    }
    assert reap(active) == 0
    assert active["sandbox-e"]["status"] == "running"
    assert active["sandbox-f"]["status"] == "running"


def test_interrupted_bootstrap_is_reaped_after_restart():
    """No port + bootstrapping is a dead start, not a static preview."""
    reap = mark_orphaned_uvicorn_previews
    active = {
        "sandbox-boot": {"status": "running", "startup_phase": "bootstrapping"},
        "sandbox-start": {"status": "running", "startup_phase": "starting"},
        "sandbox-static": {"status": "running", "startup_phase": "ready"},
    }
    assert reap(active) == 2
    assert active["sandbox-boot"]["status"] == "stopped"
    assert active["sandbox-boot"]["stopped_reason"] == "orphaned_bootstrap"
    assert active["sandbox-start"]["status"] == "stopped"
    assert active["sandbox-static"]["status"] == "running"
