"""Regression tests for security audit fixes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from security.audit_logger import AuditLogger, GENESIS_HASH
from security.bootstrap_admin import bootstrap_admin_if_needed
from security.firewall import FirewallManager


def test_audit_chain_tip_matches_disk_before_next_append(tmp_path: Path) -> None:
    log_dir = tmp_path / "audit"
    audit = AuditLogger(str(log_dir))
    audit.log("evt_a", "actor", "resource", {})
    first_file = sorted(log_dir.glob("audit-*.jsonl"))[0]
    line_a = json.loads(first_file.read_text(encoding="utf-8").strip().split("\n")[0])
    assert audit._last_hash == line_a["hash"]
    audit.log("evt_b", "actor", "resource", {})
    lines = first_file.read_text(encoding="utf-8").strip().split("\n")
    if len(lines) < 2:
        lines = sorted(log_dir.glob("audit-*.jsonl"))[-1].read_text(encoding="utf-8").strip().split("\n")
    line_b = json.loads(lines[-1])
    assert line_b["previous_hash"] == line_a["hash"]


def test_firewall_http_permissive_without_enforce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFACTORY_FIREWALL_ENFORCE", raising=False)
    fw = FirewallManager(str(tmp_path / "fw.json"))
    fw.clear_rules()
    allowed, reason = fw.http_request_allowed("203.0.113.50", 8081)
    assert allowed is True
    assert reason == "ok"


def test_firewall_http_enforce_default_deny(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_FIREWALL_ENFORCE", "1")
    fw = FirewallManager(str(tmp_path / "fw2.json"))
    fw.clear_rules()
    allowed, _ = fw.http_request_allowed("203.0.113.50", 8081)
    assert allowed is False


def test_bootstrap_interactive_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    cfg = tmp_path / "config"
    secrets = tmp_path / "secrets"
    cfg.mkdir(parents=True)
    secrets.mkdir(parents=True)
    monkeypatch.setenv("ADMIN_USERS_PATH", str(cfg / "admin_users.json"))
    monkeypatch.setenv("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.chdir(tmp_path)
    with patch("security.bootstrap_admin.getpass.getpass", side_effect=["MySecret12!", "MySecret12!"]), patch(
        "security.bootstrap_admin.ADMIN_JSON", cfg / "admin.json"
    ), patch("security.bootstrap_admin.USERS_JSON", cfg / "admin_users.json"), patch(
        "security.bootstrap_admin.BOOTSTRAP_SECRET", secrets / "bootstrap_admin.txt"
    ):
        rc = bootstrap_admin_if_needed()
    assert rc == 0
    assert not (secrets / "bootstrap_admin.txt").exists()
    users = json.loads((cfg / "admin_users.json").read_text(encoding="utf-8"))
    assert users["users"][0]["username"] == "admin"


def test_bootstrap_random_password_not_admin123(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    cfg = tmp_path / "config"
    secrets = tmp_path / "secrets"
    cfg.mkdir(parents=True)
    secrets.mkdir(parents=True)
    monkeypatch.setenv("ADMIN_USERS_PATH", str(cfg / "admin_users.json"))
    monkeypatch.setenv("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.chdir(tmp_path)
    with patch("security.bootstrap_admin.ADMIN_JSON", cfg / "admin.json"), patch(
        "security.bootstrap_admin.USERS_JSON", cfg / "admin_users.json"
    ), patch("security.bootstrap_admin.BOOTSTRAP_SECRET", secrets / "bootstrap_admin.txt"):
        rc = bootstrap_admin_if_needed()
    assert rc == 0
    secret_text = (secrets / "bootstrap_admin.txt").read_text(encoding="utf-8")
    assert "admin123" not in secret_text
    users = json.loads((cfg / "admin_users.json").read_text(encoding="utf-8"))
    assert users["users"][0]["username"] == "admin"
