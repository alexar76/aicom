"""The factory itself writes npm-generated locks, then hands the candidate to QA."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.base_agent import AgentInput
from agents.dev import DeveloperAgent, _DevRound


def _round(root: Path) -> _DevRound:
    return _DevRound(
        code_root=root, saved_relative_paths=[], reclaimed_this_round=set(), saved_files=[],
        previous_content={}, before_score=None, after_score=None, tree_defect_breakdown_before={},
        tree_defect_identities_before={}, edit_problems=[], deleted_snapshots={}, deleted_paths=[],
    )


def _agent_run(tmp_path, monkeypatch, data, repair_tool, *, initial_saved=(), initial_deleted=()):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    agent = DeveloperAgent(MagicMock())
    product_id = "prod-factory-npm-repair"
    root = tmp_path / "code" / product_id
    root.mkdir(parents=True)
    rnd = _round(root)
    rnd.deleted_paths.extend(initial_deleted)
    for rel, content in initial_saved:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        rnd.saved_relative_paths.append(rel)
        rnd.saved_files.append({"path": rel, "content": content})
    task = SimpleNamespace(
        product_id=product_id, patch_mode=False, mode=SimpleNamespace(value="python_cli"),
        admin_instructions="", implementation_plan={},
    )
    code_data = {"files": [], "notes": "Manifest/code repair already accepted"}
    monkeypatch.setattr(agent, "_dev_task", lambda _: task)
    monkeypatch.setattr(agent, "_dev_generate", AsyncMock(return_value=code_data))
    monkeypatch.setattr(agent, "_dev_write_round", lambda *_: rnd)
    for method in ("_dev_postprocess_markup", "_dev_revert_out_of_scope", "_dev_revert_regressions"):
        monkeypatch.setattr(agent, method, lambda *args: None)
    monkeypatch.setattr(agent, "_dev_judge_round", lambda *_: None)
    monkeypatch.setattr(agent, "_dev_validate_round", lambda *_: None)
    monkeypatch.setattr(agent, "_dev_finish_web_tree", lambda *_: None)
    monkeypatch.setitem(sys.modules, "web.backend.services.npm_dependency_repair", SimpleNamespace(
        repair_npm_dependencies=repair_tool,
    ))
    output = asyncio.run(agent.execute(AgentInput("task-npm-repair", product_id, "developer", data)))
    return output, root, rnd


def _failed_audit():
    return {
        "passed": False,
        "checks": [{"directory": "backend", "manifest": "backend/package.json", "lockfile": "backend/package-lock.json"}],
        "dependency_risks": [{"code": "npm_vulnerability", "package": "lodash", "severity": "high"}],
    }


def test_factory_tool_generates_backend_and_tooling_locks_and_tracks_handoff(tmp_path, monkeypatch):
    caller_thread = threading.get_ident()
    audit = _failed_audit()
    calls = []

    def tool(root, feedback):
        calls.append((root, feedback, threading.get_ident()))
        paths = ["backend/package-lock.json", "tools/package-lock.json"]
        for rel in paths:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"generatedBy": "actual npm tool", "path": rel}))
        return {"attempted": True, "passed": True, "changed_files": paths, "issues": [], "checks": [], "requires_qa": False}

    output, root, rnd = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": audit}}, tool,
    )
    assert output.success is True, output.error
    assert calls[0][0] == root and calls[0][1] == audit
    assert calls[0][2] != caller_thread
    assert output.data["file_count"] == 2
    assert set(rnd.saved_relative_paths) == {"backend/package-lock.json", "tools/package-lock.json"}
    assert all(item["generated_by"] == "npm_dependency_repair" for item in output.data["files"])
    manifest = json.loads((root / "code_manifest.json").read_text())
    assert {item["path"] for item in manifest["files"]} == set(rnd.saved_relative_paths)
    repair = output.data["npm_dependency_repair"]
    assert repair["requires_qa"] is True
    assert "QA" in output.data["peer_review"]["notes"]
    assert json.loads((root / "npm_dependency_repair.json").read_text()) == repair
    assert manifest["npm_dependency_repair"] == repair


def test_npm_generated_manifest_refreshes_existing_file_entry_without_duplicates(tmp_path, monkeypatch):
    new_text = '{"dependencies": {"lodash": "^4.17.21"}}'

    def tool(root, feedback):
        (root / "backend/package.json").write_text(new_text)
        return {"attempted": True, "passed": True, "changed_files": ["backend/package.json"], "issues": [], "checks": []}

    output, _, rnd = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": _failed_audit()}}, tool,
        initial_saved=[("backend/package.json", '{"dependencies": {"lodash": "^4.17.20"}}')],
    )
    assert output.success is True
    assert output.data["file_count"] == 1
    assert rnd.saved_relative_paths == ["backend/package.json"]
    assert output.data["files"][0]["content"] == new_text


def test_npm_regenerated_lock_is_saved_without_being_reported_as_deleted(tmp_path, monkeypatch):
    rel = "backend/package-lock.json"

    def tool(root, feedback):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"lockfileVersion": 3, "packages": {}}')
        return {"attempted": True, "passed": True, "changed_files": [rel], "issues": [], "checks": []}

    output, _, rnd = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": _failed_audit()}}, tool,
        initial_deleted=[rel, "backend/obsolete.js"],
    )
    assert output.success is True, output.error
    assert rel in rnd.saved_relative_paths
    assert any(item["path"] == rel for item in output.data["files"])
    assert output.data["deleted_files"] == ["backend/obsolete.js"]


@pytest.mark.parametrize("data", [
    {}, {"security_gate_feedback": {}},
    {"security_gate_feedback": {"npm_dependency_audit": {"passed": True}}},
    {"quality_gates_feedback": {"passed": False}},
])
def test_unrelated_developer_rounds_do_not_run_npm_repair(tmp_path, monkeypatch, data):
    def tool(*args):
        raise AssertionError("An unrelated round must not run npm")

    output, root, _ = _agent_run(tmp_path, monkeypatch, data, tool)
    assert output.success is True, output.error
    assert "npm_dependency_repair" not in output.data
    assert not (root / "npm_dependency_repair.json").exists()


def test_incomplete_repair_remains_visible_and_never_claims_release_readiness(tmp_path, monkeypatch):
    def tool(*args):
        return {"attempted": True, "passed": False, "changed_files": [], "issues": ["registry unavailable"], "checks": []}

    output, root, _ = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": _failed_audit()}}, tool,
    )
    assert output.success is True  # The Developer handoff completed; Security still gates release.
    repair = output.data["npm_dependency_repair"]
    assert repair["passed"] is False and repair["requires_qa"] is True
    assert repair["issues"] == ["registry unavailable"]
    assert json.loads((root / "npm_dependency_repair.json").read_text())["passed"] is False
    assert "quality_gates_all_passed" not in output.data


def test_tool_failure_is_saved_as_incomplete_for_following_qa_security(tmp_path, monkeypatch):
    def tool(*args):
        raise OSError("tool missing")

    output, _, _ = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": _failed_audit()}}, tool,
    )
    assert output.success is True, output.error
    assert output.data["npm_dependency_repair"]["passed"] is False
    assert "tool missing" in output.data["npm_dependency_repair"]["issues"][0]


def test_unsafe_or_missing_changed_paths_are_not_recorded_as_success(tmp_path, monkeypatch):
    def tool(*args):
        return {"attempted": True, "passed": True, "changed_files": ["../outside/package-lock.json"], "issues": [], "checks": []}

    output, _, rnd = _agent_run(
        tmp_path, monkeypatch, {"security_gate_feedback": {"npm_dependency_audit": _failed_audit()}}, tool,
    )
    assert output.success is True
    assert output.data["npm_dependency_repair"]["passed"] is False
    assert output.data["file_count"] == 0 and rnd.saved_relative_paths == []
