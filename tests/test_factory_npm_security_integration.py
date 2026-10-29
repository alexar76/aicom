"""Product dependency evidence reaches the Security → Developer repair loop."""

from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.base_agent import AgentInput
from agents.security import SecurityAgent
from web.backend.services.security_pipeline_gate import (
    build_security_gate_feedback,
    security_scan_passes_pipeline_gate,
)


def _scan(report: object) -> dict:
    return {
        "security_score": 100,
        "grade": "A",
        "vulnerabilities": [],
        "dependency_risks": [],
        "npm_dependency_audit": report,
    }


@pytest.mark.parametrize("code", ["npm_vulnerability", "npm_audit_incomplete", "npm_lockfile_stale"])
def test_a_failed_npm_audit_blocks_even_with_heuristic_risks_disabled(monkeypatch, code):
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "1")
    monkeypatch.setenv("AIFACTORY_SECURITY_BLOCK_DEP_RISKS", "0")
    report = {"passed": False, "issues": [code]}
    passed, reasons = security_scan_passes_pipeline_gate(_scan(report))
    assert not passed
    assert "npm_dependency_audit_failed" in reasons


@pytest.mark.parametrize("report", [None, [], "clean", {}, {"passed": "true"}])
def test_malformed_npm_evidence_does_not_count_as_a_clean_audit(monkeypatch, report):
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "1")
    passed, reasons = security_scan_passes_pipeline_gate(_scan(report))
    assert not passed
    assert any(reason.startswith("npm_dependency_audit_") for reason in reasons)


@pytest.mark.parametrize("skipped", [False, True])
def test_clean_or_non_npm_product_passes(monkeypatch, skipped):
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "1")
    assert security_scan_passes_pipeline_gate(_scan({"passed": True, "skipped": skipped})) == (True, [])


def test_existing_explicit_strict_gate_override_is_preserved(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "0")
    assert security_scan_passes_pipeline_gate(_scan({"passed": False})) == (True, [])


def test_legacy_reports_without_npm_evidence_keep_the_existing_gate_behavior(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "1")
    scan = _scan({"passed": True})
    del scan["npm_dependency_audit"]
    assert security_scan_passes_pipeline_gate(scan) == (True, [])


def test_repair_feedback_keeps_paths_fixes_and_hashes_and_bounds_raw_evidence():
    risk = {
        "file": "frontend/package-lock.json",
        "package": "vite",
        "severity": "high",
        "issue": "Installed version is vulnerable",
        "recommendation": "Upgrade vite and regenerate frontend/package-lock.json",
        "fixed_version": "6.4.5",
        "raw_registry_response": "x" * 100_000,
    }
    check = {
        "directory": "frontend",
        "manifest": "frontend/package.json",
        "lockfile": "frontend/package-lock.json",
        "passed": False,
        "issues": ["npm_vulnerability: " + "v" * 4000],
        "sha256": {"frontend/package-lock.json": "abc123"},
        "report": {"unbounded_npm_json": "x" * 100_000},
    }
    report = {
        "passed": False,
        "skipped": False,
        "checked_at": 123.0,
        "manifest_sha256": {"frontend/package.json": "manifest-hash"},
        "issues": ["upgrade vite"],
        "checks": [check] * 100,
        "dependency_risks": [risk] * 100,
    }
    feedback = build_security_gate_feedback(_scan(report), ["npm_dependency_audit_failed"])
    npm = feedback["npm_dependency_audit"]
    assert npm["checks"][0]["lockfile"] == "frontend/package-lock.json"
    assert npm["checks"][0]["sha256"] == {"frontend/package-lock.json": "abc123"}
    assert npm["dependency_risks"][0]["fixed_version"] == "6.4.5"
    assert "regenerate" in npm["dependency_risks"][0]["recommendation"]
    assert npm["manifest_sha256"] == {"frontend/package.json": "manifest-hash"}
    assert len(npm["checks"]) == 20
    assert len(npm["dependency_risks"]) == 30
    assert "report" not in npm["checks"][0]
    assert "raw_registry_response" not in npm["dependency_risks"][0]
    assert len(npm["checks"][0]["issues"][0]) == 1200
    assert "Re-run QA/build/tests" in npm["repair_instruction"]


@pytest.mark.parametrize("passed", [True, False])
def test_security_agent_audits_the_actual_product_and_persists_the_report(tmp_path, monkeypatch, passed):
    import web.backend.services.npm_dependency_check as npm_service

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_SECURITY_GATE_STRICT", "1")
    agent = SecurityAgent(MagicMock())
    product_id = "prod-npm-integration"
    code_dir = tmp_path / "code" / product_id
    frontend = code_dir / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    # The manifest-based source review omits the lockfile. It must not limit the
    # deterministic dependency check's coverage.
    monkeypatch.setattr(agent, "_discover_code_files", lambda _product_id: [])
    monkeypatch.setattr(agent, "_generate_llm_security_review", AsyncMock(return_value={}))
    heuristic_risk = {"package": "old-python-package", "severity": "low", "issue": "existing heuristic"}
    monkeypatch.setattr(agent, "_check_dependency_risks", lambda _files: [heuristic_risk])
    risk = {
        "file": "frontend/package-lock.json",
        "package": "vite",
        "severity": "high",
        "issue": "Known vulnerable locked version",
        "recommendation": "Upgrade vite and regenerate lockfile",
    }
    report = {
        "passed": passed,
        "skipped": False,
        "checks": [{"directory": "frontend", "passed": passed}],
        "dependency_risks": [] if passed else [risk],
        "issues": [] if passed else ["npm_vulnerability"],
        "checked_at": 123.0,
        "manifest_sha256": {"frontend/package-lock.json": "lock-hash"},
    }
    calls = []
    caller_thread = threading.get_ident()

    def audit(path):
        calls.append((path, threading.get_ident()))
        assert (path / "frontend/package-lock.json").is_file()
        return report

    monkeypatch.setattr(npm_service, "run_npm_dependency_check", audit)
    output = asyncio.run(agent.execute(AgentInput("task-audit", product_id, "security")))
    assert output.success, output.error
    assert calls[0][0] == code_dir
    assert calls[0][1] != caller_thread
    assert output.data["npm_dependency_audit"] == report
    assert output.data["dependency_risks"] == [heuristic_risk] + ([] if passed else [risk])
    assert output.metrics["npm_dependency_audit_passed"] is passed
    assert "npm Dependency Security" in output.data["passed_checks" if passed else "failed_checks"]
    artifact = json.loads((tmp_path / "security" / product_id / "security_report.json").read_text())
    assert artifact["report"]["npm_dependency_audit"] == report
    assert security_scan_passes_pipeline_gate(output.data)[0] is passed
