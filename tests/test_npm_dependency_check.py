"""Factory dependency checks cover actual locked trees and fail closed offline."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.backend.services import npm_dependency_check as scan


def _project(root: Path, rel="frontend", *, dependencies=None, dev_dependencies=None):
    directory = root / rel
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"name": "example", "version": "1.0.0", "dependencies": dependencies or {"react": "^18.3.1"}}
    if dev_dependencies:
        manifest["devDependencies"] = dev_dependencies
    packages = {"": manifest}
    for section in ("dependencies", "devDependencies"):
        for name, version in manifest.get(section, {}).items():
            packages["node_modules/" + name] = {"version": version.lstrip("^~")}
    lock = {"lockfileVersion": 3, "packages": packages}
    (directory / "package.json").write_text(json.dumps(manifest))
    (directory / "package-lock.json").write_text(json.dumps(lock))
    return directory


def _report(**severities):
    findings = {name: {"severity": severity, "range": "<2.0.0", "fixAvailable": True}
                for name, severity in severities.items()}
    counts = {severity: list(severities.values()).count(severity) for severity in scan.SEVERITIES}
    return {"vulnerabilities": findings, "metadata": {"vulnerabilities": {**counts, "total": len(findings)}}}


def _mock_npm(monkeypatch, report=None, returncode=0):
    calls = []
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/trusted/bin/npm")

    def run(command, **kwargs):
        if command[1] == "ls":
            return SimpleNamespace(returncode=0, stdout="{}")
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=json.dumps(report if report is not None else _report()))

    monkeypatch.setattr(scan.subprocess, "run", run)
    return calls


def test_no_npm_sources_skips_but_missing_source_blocks(tmp_path):
    assert scan.run_npm_dependency_check(tmp_path)["skipped"] is True
    result = scan.run_npm_dependency_check(tmp_path / "absent")
    assert result["passed"] is False
    assert result["dependency_risks"][0]["code"] == "npm_product_missing"


def test_audits_all_roots_including_dev_and_skips_vendor(tmp_path, monkeypatch):
    _project(tmp_path, "frontend", dev_dependencies={"vitest": "^4.0.0"})
    _project(tmp_path, "backend")
    _project(tmp_path, "frontend/node_modules/dep")
    _project(tmp_path, ".aicom_sandbox/fixture")
    calls = _mock_npm(monkeypatch)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is True and result["skipped"] is False
    assert len(result["checks"]) == len(calls) == 2
    assert len(result["manifest_sha256"]) == 4
    for command, kwargs in calls:
        assert command[0] == "/trusted/bin/npm"
        assert {"--include=dev", "--package-lock-only", "--ignore-scripts", "--audit-level=high", "--json"} <= set(command)
        assert 0 < kwargs["timeout"] <= 35


def test_audit_copies_only_manifests_scrubs_env_and_does_not_install(tmp_path, monkeypatch):
    directory = _project(tmp_path)
    (directory / ".npmrc").write_text("registry=https://untrusted.invalid\nignore-scripts=false\n")
    (directory / "exploit.js").write_text("throw Error('must not execute')")
    monkeypatch.setenv("OPENAI_API_KEY", "factory-secret")
    monkeypatch.setenv("NODE_OPTIONS", "--require=./exploit.js")
    monkeypatch.setenv("npm_config_omit", "dev")
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/trusted/bin/npm")
    before = {p.name: p.read_bytes() for p in directory.iterdir()}

    def run(command, **kwargs):
        stage = kwargs["cwd"]
        assert stage != directory
        assert {p.name for p in stage.iterdir()} == {"package.json", "package-lock.json"}
        assert kwargs["env"].keys().isdisjoint({"OPENAI_API_KEY", "NODE_OPTIONS", "npm_config_omit"})
        assert Path(kwargs["env"]["npm_config_userconfig"]).read_text() == ""
        assert "install" not in command and "fix" not in command
        return SimpleNamespace(returncode=0, stdout=json.dumps(_report()))

    monkeypatch.setattr(scan.subprocess, "run", run)
    assert scan.run_npm_dependency_check(tmp_path)["passed"] is True
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_high_and_critical_findings_return_actionable_repair_data(tmp_path, monkeypatch):
    _project(tmp_path)
    _mock_npm(monkeypatch, _report(vite="high", vitest="critical", esbuild="moderate"), 1)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert len(result["dependency_risks"]) == 2
    risk = result["dependency_risks"][0]
    assert risk["file"] == "frontend/package-lock.json"
    assert risk["manifest"] == "frontend/package.json"
    assert risk["fix_available"] is True
    assert "build and tests" in risk["recommendation"]
    assert result["checks"][0]["report"]["metadata"]["vulnerabilities"]["moderate"] == 1


def test_moderate_findings_are_recorded_without_blocking_high_threshold(tmp_path, monkeypatch):
    _project(tmp_path)
    _mock_npm(monkeypatch, _report(esbuild="moderate"))
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is True
    assert result["dependency_risks"] == []


@pytest.mark.parametrize("report,returncode", [
    ({"error": {"code": "ENOTFOUND"}}, 1), ({}, 0), ([], 0),
    (_report(), 1), (_report(), 2),
    ({"metadata": {"vulnerabilities": {"high": 0, "critical": 0}}, "vulnerabilities": {}}, 0),
    ({"metadata": [], "vulnerabilities": {}}, 0),
])
def test_registry_and_malformed_or_unsuccessful_reports_block(tmp_path, monkeypatch, report, returncode):
    _project(tmp_path)
    _mock_npm(monkeypatch, report, returncode)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert result["dependency_risks"][0]["code"] == "npm_audit_incomplete"


def test_inconsistent_audit_counts_are_not_clean(tmp_path, monkeypatch):
    _project(tmp_path)
    report = _report(vite="high")
    report["metadata"]["vulnerabilities"]["high"] = 0
    _mock_npm(monkeypatch, report)
    assert scan.run_npm_dependency_check(tmp_path)["passed"] is False


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("npm", 35)])
def test_audit_tool_failure_blocks(tmp_path, monkeypatch, error):
    _project(tmp_path)
    _mock_npm(monkeypatch)

    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(scan.subprocess, "run", run)
    assert scan.run_npm_dependency_check(tmp_path)["passed"] is False


def test_missing_npm_is_not_a_skip(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr(scan.shutil, "which", lambda _: None)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False and result["skipped"] is False


def test_no_lockfile_and_outdated_lockfile_block_before_registry(tmp_path, monkeypatch):
    first = _project(tmp_path, "frontend")
    (first / "package-lock.json").unlink()
    second = _project(tmp_path, "backend")
    (second / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
    calls = _mock_npm(monkeypatch)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert {r["code"] for r in result["dependency_risks"]} == {"npm_lockfile_missing", "npm_lockfile_stale"}
    assert not calls


def test_workspace_members_share_root_lock_but_unrelated_package_needs_own(tmp_path, monkeypatch):
    root = _project(tmp_path, ".")
    member = root / "packages/ui"
    member.mkdir(parents=True)
    manifest = {"name": "ui", "dependencies": {"react": "^18.3.1"}}
    (member / "package.json").write_text(json.dumps(manifest))
    lock = json.loads((root / "package-lock.json").read_text())
    lock["packages"]["packages/ui"] = manifest
    (root / "package-lock.json").write_text(json.dumps(lock))
    calls = _mock_npm(monkeypatch)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is True and len(calls) == 1
    assert "packages/ui/package.json" in result["checks"][0]["sha256"]
    unrelated = root / "tools"
    unrelated.mkdir()
    (unrelated / "package.json").write_text(json.dumps(manifest))
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert result["dependency_risks"][0]["code"] == "npm_lockfile_missing"


@pytest.mark.parametrize("contents", ["[]", "{bad", '{"lockfileVersion": 1}', '{"lockfileVersion": 3, "packages": {}}'])
def test_bad_or_unverifiable_lockfile_blocks(tmp_path, monkeypatch, contents):
    directory = _project(tmp_path)
    (directory / "package-lock.json").write_text(contents)
    calls = _mock_npm(monkeypatch)
    assert scan.run_npm_dependency_check(tmp_path)["passed"] is False
    assert not calls


def test_product_edit_during_audit_invalidates_clean_result(tmp_path, monkeypatch):
    directory = _project(tmp_path)
    _mock_npm(monkeypatch)

    def run(*args, **kwargs):
        (directory / "package.json").write_text('{"dependencies": {"vite": "*"}}')
        return SimpleNamespace(returncode=0, stdout=json.dumps(_report()))

    monkeypatch.setattr(scan.subprocess, "run", run)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert "changed during the audit" in result["issues"][0]


def test_symlinked_input_outside_product_is_blocked(tmp_path, monkeypatch):
    directory = _project(tmp_path / "product")
    outside = tmp_path / "outside.json"
    outside.write_text((directory / "package-lock.json").read_text())
    (directory / "package-lock.json").unlink()
    (directory / "package-lock.json").symlink_to(outside)
    calls = _mock_npm(monkeypatch)
    assert scan.run_npm_dependency_check(tmp_path / "product")["passed"] is False
    assert not calls


def test_shrinkwrap_cannot_override_the_audited_lockfile(tmp_path, monkeypatch):
    directory = _project(tmp_path)
    (directory / "npm-shrinkwrap.json").write_text((directory / "package-lock.json").read_text())
    calls = _mock_npm(monkeypatch)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert "npm_shrinkwrap_unsupported" in {r["code"] for r in result["dependency_risks"]}
    assert not calls
