"""The factory generates npm repairs itself, without trusting generated lockfile text."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.backend.services import npm_dependency_repair as repair


def _project(root: Path, rel: str = "frontend", *, spec: str = "^4.17.0") -> Path:
    directory = root / rel
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "factory-product", "version": "1.0.0", "private": True,
        "dependencies": {"lodash": spec},
        "scripts": {"postinstall": "node never-run.js"},
    }
    (directory / "package.json").write_text(json.dumps(manifest))
    _write_lock(directory, "4.17.20")
    return directory


def _write_lock(directory: Path, version: str = "4.17.21") -> None:
    manifest = json.loads((directory / "package.json").read_text())
    lock = {
        "name": manifest["name"], "version": manifest["version"], "lockfileVersion": 3,
        "packages": {"": manifest, "node_modules/lodash": {
            "version": version,
            "resolved": f"https://registry.npmjs.org/lodash/-/lodash-{version}.tgz",
        }},
    }
    (directory / "package-lock.json").write_text(json.dumps(lock))


def _feedback(rel: str = "frontend", *, code: str | None = None) -> dict:
    check = {
        "directory": rel, "manifest": f"{rel}/package.json", "lockfile": f"{rel}/package-lock.json",
        "passed": False, "issues": ["npm dependency repair required"],
    }
    if code:
        check["code"] = code
    return {
        "passed": False, "checks": [check],
        "dependency_risks": [{
            "code": "npm_vulnerability", "package": "lodash", "severity": "high",
            "file": f"{rel}/package-lock.json", "manifest": f"{rel}/package.json",
            "fix_available": True,
        }] if code is None else [],
    }


def _audit(**findings: str) -> dict:
    severities = ("info", "low", "moderate", "high", "critical")
    return {
        "vulnerabilities": {name: {"severity": level, "range": "<99.0.0", "fixAvailable": True}
                            for name, level in findings.items()},
        "metadata": {"vulnerabilities": {
            **{level: list(findings.values()).count(level) for level in severities}, "total": len(findings),
        }},
    }


def _npm(monkeypatch, *, audit: dict | None = None, tree_error: bool = False,
         mutate_source=None, fail_command: str | None = None):
    calls = []
    monkeypatch.setattr(repair.shutil, "which", lambda _: "/trusted/npm")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        stage = Path(kwargs["cwd"])
        kind = "fix" if command[1:3] == ["audit", "fix"] else command[1]
        if kind == fail_command:
            raise subprocess.TimeoutExpired(command, 30)
        if kind in ("install", "fix"):
            _write_lock(stage)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"added": 0, "audit": _audit()}), stderr="")
        if kind == "ls":
            tree = {"problems": ["missing: lodash@4.17.21"]} if tree_error else {
                "name": "factory-product", "dependencies": {"lodash": {"version": "4.17.21"}},
            }
            return SimpleNamespace(returncode=int(tree_error), stdout=json.dumps(tree), stderr="")
        assert kind == "audit", command
        if mutate_source:
            mutate_source()
        report = audit if audit is not None else _audit()
        counts = report.get("metadata", {}).get("vulnerabilities", {}) if isinstance(report, dict) else {}
        return SimpleNamespace(returncode=int(bool(counts.get("high") or counts.get("critical") or report.get("error"))),
                               stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(repair.subprocess, "run", run)
    return calls


def test_factory_writes_npm_generated_lock_and_requires_qa(tmp_path, monkeypatch):
    source = _project(tmp_path)
    before = (source / "package-lock.json").read_bytes()
    calls = _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["attempted"] is True and result["passed"] is True
    assert result["requires_qa"] is True
    assert result["changed_files"] == ["frontend/package-lock.json"]
    assert (source / "package-lock.json").read_bytes() != before
    locked = json.loads((source / "package-lock.json").read_text())
    assert locked["packages"]["node_modules/lodash"]["version"] == "4.17.21"
    kinds = ["fix" if command[1:3] == ["audit", "fix"] else command[1] for command, _ in calls]
    assert kinds == ["install", "fix", "ls", "audit"]


def test_uses_updated_manifest_from_developer_and_regenerates_lock(tmp_path, monkeypatch):
    source = _project(tmp_path, "backend")
    manifest = json.loads((source / "package.json").read_text())
    manifest["dependencies"]["lodash"] = "^4.17.21"
    (source / "package.json").write_text(json.dumps(manifest))
    _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback("backend", code="npm_lockfile_stale"))
    assert result["passed"] is True
    locked = json.loads((source / "package-lock.json").read_text())
    assert locked["packages"][""]["dependencies"] == manifest["dependencies"]
    assert result["changed_files"] == ["backend/package-lock.json"]


def test_missing_backend_lock_is_generated_without_frontend_build(tmp_path, monkeypatch):
    source = _project(tmp_path, "backend")
    (source / "package-lock.json").unlink()
    _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback("backend", code="npm_lockfile_missing"))
    assert result["passed"] is True
    assert (source / "package-lock.json").is_file()
    assert "backend/package-lock.json" in result["changed_files"]


def test_malformed_target_lock_is_regenerated_from_valid_manifest(tmp_path, monkeypatch):
    source = _project(tmp_path)
    (source / "package-lock.json").write_text("{this lock is not valid JSON")
    _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback(code="npm_manifest_invalid"))
    assert result["passed"] is True
    assert result["changed_files"] == ["frontend/package-lock.json"]
    locked = json.loads((source / "package-lock.json").read_text())
    assert locked["packages"]["node_modules/lodash"]["version"] == "4.17.21"


@pytest.mark.parametrize("unrelated_defect", ["malformed_lock", "git_dependency"])
def test_unrelated_npm_project_does_not_block_requested_repair(tmp_path, monkeypatch, unrelated_defect):
    _project(tmp_path)
    unrelated = _project(tmp_path, "tools")
    if unrelated_defect == "malformed_lock":
        (unrelated / "package-lock.json").write_text("{unrelated broken lock")
    else:
        manifest = json.loads((unrelated / "package.json").read_text())
        manifest["dependencies"]["lodash"] = "git+ssh://git@untrusted.invalid/repository"
        (unrelated / "package.json").write_text(json.dumps(manifest))
    original = {p.name: p.read_bytes() for p in unrelated.iterdir()}
    _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is True
    assert result["changed_files"] == ["frontend/package-lock.json"]
    assert original == {p.name: p.read_bytes() for p in unrelated.iterdir()}


def test_tool_runs_with_dev_dependencies_without_scripts_or_factory_secrets(tmp_path, monkeypatch):
    source = _project(tmp_path)
    (source / ".npmrc").write_text("registry=https://untrusted.invalid\nignore-scripts=false\n")
    (source / "never-run.js").write_text("throw Error('must never execute')")
    monkeypatch.setenv("OPENAI_API_KEY", "factory-secret")
    monkeypatch.setenv("NODE_OPTIONS", "--require=./never-run.js")
    monkeypatch.setenv("npm_config_omit", "dev")
    calls = _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is True
    for command, kwargs in calls:
        assert "--ignore-scripts" in command
        assert "--include=dev" in command
        assert "--force" not in command and "--omit=dev" not in command
        assert Path(kwargs["cwd"]) != source
        assert not {"OPENAI_API_KEY", "NODE_OPTIONS", "npm_config_omit"} & kwargs["env"].keys()
        assert "npm_config_userconfig" in kwargs["env"]
        assert "node_modules" not in {p.name for p in source.iterdir()}


@pytest.mark.parametrize("feedback", [{}, {"passed": True}, _feedback(code="npm_audit_incomplete")])
def test_no_speculative_edits_for_clean_or_unavailable_audit(tmp_path, monkeypatch, feedback):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    calls = _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, feedback)
    assert result["attempted"] is False
    assert result["changed_files"] == [] and not calls
    assert (source / "package-lock.json").read_bytes() == original


def test_missing_npm_does_not_apply_changes(tmp_path, monkeypatch):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    monkeypatch.setattr(repair.shutil, "which", lambda _: None)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert (source / "package-lock.json").read_bytes() == original


@pytest.mark.parametrize("command", ["install", "fix", "ls", "audit"])
def test_tool_timeout_never_applies_a_partial_candidate(tmp_path, monkeypatch, command):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    _npm(monkeypatch, fail_command=command)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert result["issues"]
    assert (source / "package-lock.json").read_bytes() == original


def test_incomplete_resolved_graph_blocks_even_a_clean_registry_result(tmp_path, monkeypatch):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    _npm(monkeypatch, tree_error=True)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert (source / "package-lock.json").read_bytes() == original


def test_registry_failure_does_not_apply_candidate(tmp_path, monkeypatch):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    _npm(monkeypatch, audit={"error": {"code": "ENOTFOUND"}})
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert (source / "package-lock.json").read_bytes() == original


def test_remaining_original_high_finding_does_not_claim_release_ready(tmp_path, monkeypatch):
    _project(tmp_path)
    _npm(monkeypatch, audit=_audit(lodash="high"))
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["attempted"] is True and result["passed"] is False
    assert result["requires_qa"] is True
    assert result["issues"]


def test_candidate_cannot_introduce_a_new_high_or_critical_package(tmp_path, monkeypatch):
    source = _project(tmp_path)
    original = (source / "package-lock.json").read_bytes()
    _npm(monkeypatch, audit=_audit(new_dependency="critical"))
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert (source / "package-lock.json").read_bytes() == original


def test_old_finding_in_another_root_cannot_authorize_new_high_in_target(tmp_path, monkeypatch):
    _project(tmp_path, "frontend")
    target = _project(tmp_path, "backend")
    original = (target / "package-lock.json").read_bytes()
    feedback = _feedback("backend", code="npm_lockfile_stale")
    feedback["dependency_risks"] = [{
        "code": "npm_vulnerability", "package": "vite", "severity": "high",
        "file": "frontend/package-lock.json", "manifest": "frontend/package.json",
    }]
    _npm(monkeypatch, audit=_audit(vite="high"))
    result = repair.repair_npm_dependencies(tmp_path, feedback)
    assert result["passed"] is False
    assert result["changed_files"] == []
    assert (target / "package-lock.json").read_bytes() == original


def test_concurrent_source_change_is_preserved_instead_of_overwritten(tmp_path, monkeypatch):
    source = _project(tmp_path)
    lock = source / "package-lock.json"
    concurrent = '{"concurrent": "developer edit"}'
    _npm(monkeypatch, mutate_source=lambda: lock.write_text(concurrent))
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert lock.read_text() == concurrent


def test_feedback_path_cannot_escape_product(tmp_path, monkeypatch):
    _project(tmp_path / "product")
    outside = _project(tmp_path, "outside")
    original = (outside / "package-lock.json").read_bytes()
    calls = _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path / "product", _feedback("../outside", code="npm_lockfile_missing"))
    assert result["passed"] is False and result["changed_files"] == []
    assert not calls
    assert (outside / "package-lock.json").read_bytes() == original


@pytest.mark.parametrize("spec", ["https://untrusted.invalid/package.tgz", "git+ssh://git@untrusted.invalid/repo", "file:/private/package"])
def test_unsupported_external_sources_are_not_resolved_on_factory_host(tmp_path, monkeypatch, spec):
    _project(tmp_path, spec=spec)
    calls = _npm(monkeypatch)
    result = repair.repair_npm_dependencies(tmp_path, _feedback())
    assert result["passed"] is False and result["changed_files"] == []
    assert not calls
