"""A preview that expires (or whose process dies) must release what it holds.

Found 2026-09-11 on the factory host: 70 ``.aicom_sandbox/sandbox-*`` trees (9.4 GB, the
oldest three weeks old) and two ``running`` registry rows with no live process behind them.
TTL expiry only edited the registry dict; nothing stopped uvicorn, removed the ephemeral
Postgres or deleted the venv. These tests pin the release paths.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from web.backend.api import sandbox as sandbox_api
from web.backend.services import sandbox_guards as guards
from web.backend.services import sandbox_preview_api as preview_api


def _sid() -> str:
    return f"sandbox-{uuid.uuid4().hex}"


def _fresh_registry(monkeypatch, tmp_path: Path) -> dict:
    reg: dict = {}
    monkeypatch.setattr(sandbox_api, "_active_sandboxes", reg)
    monkeypatch.setattr(sandbox_api, "_SANDBOX_REGISTRY_PATH", tmp_path / "state" / "sandboxes.json")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    return reg


def _record_stops(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sandbox_api, "stop_preview_for_sandbox", lambda sid: calls.append(("preview", sid)))
    monkeypatch.setattr(sandbox_api, "stop_compose_for_sandbox", lambda sid: calls.append(("compose", sid)))
    return calls


def _workdir(tmp_path: Path, product_id: str, sid: str, *, age_s: float = 0.0) -> Path:
    tree = tmp_path / "code" / product_id / ".aicom_sandbox" / sid
    (tree / "preview-venv" / "bin").mkdir(parents=True)
    (tree / "preview-venv" / "bin" / "python").write_bytes(b"\x7fELF" * 64)
    if age_s:
        old = time.time() - age_s
        os.utime(tree, (old, old))
    return tree


def test_expired_running_row_is_torn_down_and_dropped(monkeypatch, tmp_path: Path):
    reg = _fresh_registry(monkeypatch, tmp_path)
    calls = _record_stops(monkeypatch)
    sid = _sid()
    tree = _workdir(tmp_path, "prod-x", sid)
    reg[sid] = {"status": "running", "product_id": "prod-x", "expires_at": time.time() - 5,
                "backend_preview_port": 40001}

    assert sandbox_api._prune_expired_and_teardown() == 1

    assert reg == {}
    assert ("preview", sid) in calls and ("compose", sid) in calls
    assert not tree.exists(), "the venv tree must go with the row"
    assert json.loads((tmp_path / "state" / "sandboxes.json").read_text()) == {}


def test_live_rows_are_untouched(monkeypatch, tmp_path: Path):
    reg = _fresh_registry(monkeypatch, tmp_path)
    calls = _record_stops(monkeypatch)
    sid = _sid()
    tree = _workdir(tmp_path, "prod-x", sid)
    reg[sid] = {"status": "running", "product_id": "prod-x", "expires_at": time.time() + 3000}

    assert sandbox_api._prune_expired_and_teardown() == 0
    assert sid in reg and calls == [] and tree.exists()


def test_guard_prune_tears_down_only_expired_running_rows():
    torn: list[str] = []
    active = {
        "sandbox-expired": {"status": "running", "expires_at": time.time() - 1},
        "sandbox-stopped": {"status": "stopped", "expires_at": time.time() - 1},
        "sandbox-live": {"status": "running", "expires_at": time.time() + 999},
        "sandbox-junk": "not-a-row",
    }
    removed = guards.prune_expired_sandboxes(active, teardown=lambda sid, row: torn.append(sid))
    assert removed == 3
    assert torn == ["sandbox-expired"], "stopped rows were released when stopped; junk holds nothing"
    assert list(active) == ["sandbox-live"]


def test_guard_prune_survives_a_failing_teardown():
    def boom(sid, row):
        raise RuntimeError("docker down")

    active = {
        "sandbox-a": {"status": "running", "expires_at": 1.0},
        "sandbox-b": {"status": "running", "expires_at": 1.0},
    }
    assert guards.prune_expired_sandboxes(active, teardown=boom) == 2
    assert active == {}


def test_exited_preview_processes_are_detected(monkeypatch):
    class Proc:
        def __init__(self, rc):
            self._rc = rc

        def poll(self):
            return self._rc

    monkeypatch.setattr(preview_api, "_preview_procs", {"sandbox-dead": Proc(137), "sandbox-alive": Proc(None)})
    assert preview_api.exited_preview_sandboxes() == ["sandbox-dead"]


def test_dead_preview_closes_its_row_and_releases_resources(monkeypatch, tmp_path: Path):
    reg = _fresh_registry(monkeypatch, tmp_path)
    calls = _record_stops(monkeypatch)
    sid = _sid()
    tree = _workdir(tmp_path, "prod-x", sid)
    reg[sid] = {"status": "running", "product_id": "prod-x", "expires_at": time.time() + 3000,
                "backend_preview_port": 40002}
    monkeypatch.setattr(sandbox_api, "exited_preview_sandboxes", lambda: [sid])

    assert sandbox_api._reap_dead_previews() == 1

    assert reg[sid]["status"] == "stopped"
    assert reg[sid]["stopped_reason"] == "preview_exited"
    assert ("preview", sid) in calls
    assert not tree.exists()


def test_stale_workdir_sweep_removes_only_unowned_id_shaped_old_trees(monkeypatch, tmp_path: Path):
    reg = _fresh_registry(monkeypatch, tmp_path)
    orphan_old = _sid()
    owned_old = _sid()
    orphan_fresh = _sid()
    t_orphan_old = _workdir(tmp_path, "prod-a", orphan_old, age_s=7200)
    t_owned_old = _workdir(tmp_path, "prod-a", owned_old, age_s=7200)
    t_gate = _workdir(tmp_path, "prod-b", "sandbox-gatecheck", age_s=7200)
    t_fresh = _workdir(tmp_path, "prod-b", orphan_fresh)
    reg[owned_old] = {"status": "running", "product_id": "prod-a", "expires_at": time.time() + 3000}

    removed, freed = sandbox_api._sweep_stale_workdirs()

    assert removed == 1 and freed > 0
    assert not t_orphan_old.exists()
    assert t_owned_old.exists(), "a running row owns its tree"
    assert t_gate.exists(), "fixed-name gate trees are reused by the gates"
    assert t_fresh.exists(), "inside the grace window nothing is touched"


def test_eviction_goes_through_the_shared_teardown(monkeypatch, tmp_path: Path):
    reg = _fresh_registry(monkeypatch, tmp_path)
    torn: list[str] = []
    monkeypatch.setattr(sandbox_api, "_teardown_sandbox_resources", lambda sid, entry=None: torn.append(sid))
    old, new = _sid(), _sid()
    reg[old] = {"status": "running", "started_at": 100.0, "expires_at": time.time() + 3000}
    reg[new] = {"status": "running", "started_at": 200.0, "expires_at": time.time() + 3000}

    assert sandbox_api._evict_oldest_running_sandbox() == old
    assert torn == [old]
    assert reg[old]["status"] == "stopped" and reg[new]["status"] == "running"


def test_sweep_once_releases_stopped_rows_too(monkeypatch, tmp_path: Path):
    """Boot orphans are marked stopped without a teardown; the first sweep must finish the job."""
    reg = _fresh_registry(monkeypatch, tmp_path)
    torn: list[str] = []
    monkeypatch.setattr(sandbox_api, "_teardown_sandbox_resources", lambda sid, entry=None: torn.append(sid))
    monkeypatch.setattr(sandbox_api, "exited_preview_sandboxes", lambda: [])
    monkeypatch.setattr(sandbox_api, "_maybe_gc_preview_resources", lambda: None)
    orphan = _sid()
    reg[orphan] = {"status": "stopped", "stopped_reason": "orphaned_by_restart", "product_id": "prod-a"}

    result = sandbox_api.sweep_once()

    assert torn == [orphan]
    assert orphan not in reg
    assert result == {"expired": 0, "exited": 0, "workdirs": 0}


def test_sweeper_is_opt_out_and_starts_once(monkeypatch):
    monkeypatch.setattr(sandbox_api, "_sweeper_thread", None)
    monkeypatch.setenv("AIFACTORY_SANDBOX_SWEEP_INTERVAL_S", "0")
    assert sandbox_api.start_expiry_sweeper() is False

    monkeypatch.setattr(sandbox_api, "sweep_once", lambda: {})
    monkeypatch.setenv("AIFACTORY_SANDBOX_SWEEP_INTERVAL_S", "3600")
    assert sandbox_api.start_expiry_sweeper() is True
    assert sandbox_api.start_expiry_sweeper() is False, "one sweeper per process"
    assert sandbox_api._sweeper_thread is not None and sandbox_api._sweeper_thread.daemon


def test_lifespan_starts_the_sweeper():
    src = (Path(__file__).resolve().parents[1] / "web" / "backend" / "main.py").read_text(encoding="utf-8")
    assert "sandbox.start_expiry_sweeper()" in src


def test_sweeper_events_are_visible_without_a_logging_config():
    """Nothing configures the root logger, so uvicorn's lastResort handler drops INFO.

    The two sweeper events an operator needs after the fact — previews released on expiry and
    gigabytes of preview trees deleted — must therefore not be logged at INFO.
    """
    src = (Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "sandbox.py").read_text(
        encoding="utf-8"
    )
    for marker in ("preview(s) expired, resources released", "removed %d stale preview tree(s)"):
        i = src.index(marker)
        call = src.rindex("logger.", 0, i)
        assert src[call:i].startswith("logger.warning"), f"{marker!r} must log above INFO"
