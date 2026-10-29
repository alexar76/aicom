"""No deployment is performed: remote helpers run only against temporary files."""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from scripts import llm_failover_openrouter as failover

CANARY = "disposable-failover-credential-for-test"


def test_failover_env_and_backup_private_from_first_write(tmp_path):
    target = tmp_path / ".env"
    previous = os.umask(0)
    try:
        failover._upsert_env_lines(target, {"OPENROUTER_API_KEY": CANARY})
        backup = failover._backup(target)
        failover._upsert_env_lines(target, {"OPENROUTER_API_KEY": "disposable-replacement"})
    finally:
        os.umask(previous)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert CANARY in backup.read_text() and CANARY not in target.read_text()


def test_profile_switch_env_and_backup_private(tmp_path):
    from scripts import llm_routing

    target = tmp_path / ".env"
    previous = os.umask(0)
    try:
        llm_routing._upsert_env(target, {"OPENROUTER_API_KEY": CANARY}, marker="# test-profile")
        backup = llm_routing._backup(target)
    finally:
        os.umask(previous)
    assert target.read_text() == backup.read_text()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_remote_failover_key_only_on_stdin_and_private_writes(tmp_path, monkeypatch):
    captured = {}
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, kwargs=kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True}), stderr="")

    monkeypatch.setattr(failover.subprocess, "run", fake_run)
    assert failover.apply_metis_remote("unused.invalid", "/unused/prod.yaml", CANARY, restart=False)["ok"]
    assert CANARY not in json.dumps(captured["cmd"])
    assert json.loads(captured["kwargs"]["input"])["api_key"] == CANARY
    argv = shlex.split(captured["cmd"][-1])
    assert argv[:2] == ["python3", "-c"]
    # Exercise exactly the shipped remote program with a temporary env path.
    env = tmp_path / ".env"
    program = argv[2].replace('Path("/opt/metis/.env")', f"Path({str(env)!r})")
    prod = tmp_path / "prod.yaml"
    prod.write_text(yaml.safe_dump({"api_key_env": "DEEPSEEK_API_KEY", "modules": {}}))
    previous = os.umask(0)
    try:
        result = real_run(
            [sys.executable, "-c", program, str(prod)],
            input=captured["kwargs"]["input"], capture_output=True, text=True,
        )
    finally:
        os.umask(previous)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert CANARY not in result.stdout
    for path in (prod, env, prod.with_name(report["backup"].split("/")[-1])):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert CANARY in env.read_text()
    assert CANARY not in prod.read_text()


def test_remote_failover_errors_redact_provider_echo(monkeypatch):
    monkeypatch.setattr(failover.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="", stderr="provider rejected " + CANARY,
    ))
    with pytest.raises(RuntimeError) as exc:
        failover.apply_metis_remote("unused.invalid", "/unused/prod.yaml", CANARY, restart=False)
    assert CANARY not in str(exc.value)


@pytest.fixture
def vapid_data(tmp_path, monkeypatch):
    from web.backend.services import web_push_service as push

    monkeypatch.setattr(push, "factory_data_root", lambda: tmp_path)

    class FakeVapid:
        public_key = SimpleNamespace(public_bytes=lambda *args: b"\x04" + b"\x01" * 64)

        def generate_keys(self):
            pass

        def private_pem(self):
            return b"disposable-private-material-for-vapid-test"

    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(Vapid=FakeVapid))
    return push, tmp_path / "secrets" / "web_push_vapid.json"


def test_vapid_private_creation_and_existing_mode_upgrade(vapid_data):
    push, path = vapid_data
    previous = os.umask(0)
    try:
        material = push.get_or_create_vapid_material()
    finally:
        os.umask(previous)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o644)
    assert push.get_or_create_vapid_material() == material
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_vapid_refuses_symlink_or_silent_rotation(vapid_data, tmp_path):
    push, path = vapid_data
    path.parent.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("not-vapid")
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        push.get_or_create_vapid_material()
    assert outside.read_text() == "not-vapid"
    path.unlink()
    path.write_text("{broken-json")
    with pytest.raises(ValueError):
        push.get_or_create_vapid_material()
    assert path.read_text() == "{broken-json"
