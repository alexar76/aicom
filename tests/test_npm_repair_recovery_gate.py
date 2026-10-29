"""Auto-recovery cannot COMPLETE a dependency repair without a fresh clean audit."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orchestrator import auto_recovery
from web.backend.services import npm_dependency_check


def _recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_MIN_REPAIR_ROUND", "1")
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_REQUIRE_STOREFRONT", "1")
    root = tmp_path / "code" / "prod-recover-deps"
    root.mkdir(parents=True)
    product = {
        "id": root.name, "state": "BUG_FOUND", "quality_repair_round": 5,
        "security_repair_round": 2,
        "auto_recovery_verification": {"passed": True, "npm_dependency_audit": {"passed": True, "checked_at": 1}},
    }
    monkeypatch.setattr(auto_recovery, "verify_product_automated", lambda *args, **kwargs: {
        "passed": True, "tests": {"passed": True}, "product_id": root.name,
    })
    monkeypatch.setattr(auto_recovery, "refresh_product_storefront_telemetry", lambda *args, **kwargs: {
        "ok": True, "release_score": 90, "demo_score": 100,
    })
    monkeypatch.setattr("web.backend.services.duplicate_module_check.find_capabilities_never_invoked", lambda *args, **kwargs: [])
    complete = MagicMock()
    monkeypatch.setattr(auto_recovery, "apply_product_completed_locked", complete)
    return product, root, complete


@pytest.mark.parametrize("issue", ["high:lodash", "npm audit registry unavailable", "lockfile stale"])
def test_recovery_blocks_remaining_findings_or_incomplete_check_despite_old_clean_report(tmp_path, monkeypatch, issue):
    product, root, complete = _recovery(tmp_path, monkeypatch)
    calls = []
    fresh = {"passed": False, "skipped": False, "checked_at": 123, "issues": [issue]}

    def audit(code_root):
        calls.append(code_root)
        return fresh

    monkeypatch.setattr(npm_dependency_check, "run_npm_dependency_check", audit)
    assert auto_recovery.try_auto_recovery_after_qa_failure(
        product, [], repair_round=5, data_root=str(tmp_path),
    ) is False
    assert calls == [root]
    complete.assert_not_called()
    assert product["state"] == "BUG_FOUND"
    evidence = product["auto_recovery_verification"]
    assert evidence["passed"] is False
    assert evidence["npm_dependency_audit"] == fresh
    assert evidence["tests"]["passed"] is True


def test_successful_recovery_records_fresh_current_file_audit_before_completion(tmp_path, monkeypatch):
    product, root, complete = _recovery(tmp_path, monkeypatch)
    events = []
    fresh = {"passed": True, "skipped": False, "checked_at": 456, "manifest_sha256": {"package-lock.json": "new-hash"}}

    def audit(code_root):
        assert code_root == root
        events.append("audit")
        return fresh

    complete.side_effect = lambda *args, **kwargs: events.append("complete")
    monkeypatch.setattr(npm_dependency_check, "run_npm_dependency_check", audit)
    assert auto_recovery.try_auto_recovery_after_qa_failure(
        product, [], repair_round=5, data_root=str(tmp_path),
    ) is True
    assert events == ["audit", "complete"]
    assert product["auto_recovery_verification"]["passed"] is True
    assert product["auto_recovery_verification"]["npm_dependency_audit"] == fresh


def test_non_npm_product_passes_with_actual_applicable_skip(tmp_path, monkeypatch):
    product, _, complete = _recovery(tmp_path, monkeypatch)
    assert auto_recovery.try_auto_recovery_after_qa_failure(
        product, [], repair_round=5, data_root=str(tmp_path),
    ) is True
    complete.assert_called_once()
    report = product["auto_recovery_verification"]["npm_dependency_audit"]
    assert report["passed"] is True and report["skipped"] is True
    assert report["reason"] == "no_npm_projects"


@pytest.mark.parametrize("kind", ["exception", "malformed", "unproven"])
def test_recovery_refuses_unproven_or_crashed_check(tmp_path, monkeypatch, kind):
    product, _, complete = _recovery(tmp_path, monkeypatch)

    def audit(*args):
        if kind == "exception":
            raise OSError("npm unavailable")
        return [] if kind == "malformed" else {"passed": "true"}

    monkeypatch.setattr(npm_dependency_check, "run_npm_dependency_check", audit)
    assert auto_recovery.try_auto_recovery_after_qa_failure(
        product, [], repair_round=5, data_root=str(tmp_path),
    ) is False
    complete.assert_not_called()
    assert product["auto_recovery_verification"]["passed"] is False


def test_refresh_changes_are_audited_before_recovery_completion(tmp_path, monkeypatch):
    product, root, complete = _recovery(tmp_path, monkeypatch)

    def refresh(*args, **kwargs):
        (root / "package.json").write_text('{"dependencies": {"lodash": "4.17.20"}}')
        return {"ok": True}

    monkeypatch.setattr(auto_recovery, "refresh_product_storefront_telemetry", refresh)
    # Real checker sees the file introduced during refresh, so a previous clean
    # result cannot cover it and the missing matching lock blocks completion.
    assert auto_recovery.try_auto_recovery_after_qa_failure(
        product, [], repair_round=5, data_root=str(tmp_path),
    ) is False
    complete.assert_not_called()
    report = product["auto_recovery_verification"]["npm_dependency_audit"]
    assert report["dependency_risks"][0]["code"] == "npm_lockfile_missing"
