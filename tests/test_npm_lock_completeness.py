"""An audit cannot declare a truncated npm dependency graph clean."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.backend.services import npm_dependency_check as scan


def _write_project(directory: Path, manifest: dict, packages: dict | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text(json.dumps(manifest))
    (directory / "package-lock.json").write_text(json.dumps({
        "name": manifest.get("name"), "version": manifest.get("version"),
        "lockfileVersion": 3, "packages": packages if packages is not None else {"": manifest},
    }))


def _audit_clean() -> dict:
    counts = dict.fromkeys((*scan.SEVERITIES, "total"), 0)
    return {"vulnerabilities": {}, "metadata": {"vulnerabilities": counts}}


@pytest.mark.parametrize("tree,exit_code", [
    ({"problems": ["missing: lodash@4.17.20"], "dependencies": {"lodash": {"missing": True}}}, 1),
    ({"dependencies": {"parent": {"dependencies": {"child": {"missing": True}}}}}, 0),
    ({"dependencies": {"parent": {"invalid": True}}}, 0),
    ({"dependencies": []}, 0),
    ([], 0),
])
def test_invalid_dependency_tree_blocks_before_advisory_audit(tmp_path, monkeypatch, tree, exit_code):
    _write_project(tmp_path, {"name": "product", "dependencies": {"lodash": "4.17.20"}})
    calls = []
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/trusted/npm")

    def run(command, **kwargs):
        calls.append(command)
        assert command[1] == "ls"
        assert {"--package-lock-only", "--all", "--offline", "--ignore-scripts", "--include=dev"} <= set(command)
        assert 0 < kwargs["timeout"] <= 35
        return SimpleNamespace(returncode=exit_code, stdout=json.dumps(tree))

    monkeypatch.setattr(scan.subprocess, "run", run)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is False
    assert result["dependency_risks"][0]["code"] == "npm_lockfile_stale"
    assert len(calls) == 1


def test_valid_locked_tree_is_checked_before_advisories_in_same_scrubbed_stage(tmp_path, monkeypatch):
    _write_project(tmp_path, {"name": "product"})
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/trusted/npm")
    monkeypatch.setenv("NODE_OPTIONS", "--require=./never-run.js")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert "NODE_OPTIONS" not in kwargs["env"]
        assert kwargs["cwd"] != tmp_path
        assert "--ignore-scripts" in command
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {"name": "product"} if command[1] == "ls" else _audit_clean(),
        ))

    monkeypatch.setattr(scan.subprocess, "run", run)
    result = scan.run_npm_dependency_check(tmp_path)
    assert result["passed"] is True
    assert [command[1] for command, _ in calls] == ["ls", "audit"]
    assert calls[0][1]["cwd"] == calls[1][1]["cwd"]
    assert calls[0][1]["env"] == calls[1][1]["env"]


def _real_tree(directory: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("npm is unavailable")
    home = tmp_path / "npm-home"
    home.mkdir(exist_ok=True)
    (home / "user.npmrc").touch()
    (home / "global.npmrc").touch()
    env = {
        "PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "CI": "1",
        "npm_config_cache": str(home / "cache"),
        "npm_config_userconfig": str(home / "user.npmrc"),
        "npm_config_globalconfig": str(home / "global.npmrc"),
        "npm_config_update_notifier": "false",
    }
    return subprocess.run([npm, *scan.LOCK_CHECK_ARGS], cwd=directory, env=env,
                          capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("section", ["dependencies", "devDependencies"])
def test_real_npm_rejects_a_declared_dependency_missing_from_lock(tmp_path, section):
    directory = tmp_path / "project"
    _write_project(directory, {"name": "product", "version": "1.0.0", section: {"lodash": "4.17.20"}})
    tree = _real_tree(directory, tmp_path)
    assert tree.returncode != 0
    with pytest.raises(ValueError, match="incomplete or invalid"):
        scan._validate_locked_tree(tree.stdout, tree.returncode)


def test_real_npm_rejects_a_missing_transitive_dependency(tmp_path):
    directory = tmp_path / "project"
    manifest = {"name": "product", "version": "1.0.0", "dependencies": {"parent": "1.0.0"}}
    _write_project(directory, manifest, {
        "": manifest,
        "node_modules/parent": {"version": "1.0.0", "dependencies": {"child": "1.0.0"}},
    })
    tree = _real_tree(directory, tmp_path)
    assert tree.returncode != 0
    with pytest.raises(ValueError, match="incomplete or invalid"):
        scan._validate_locked_tree(tree.stdout, tree.returncode)


@pytest.mark.parametrize("optional", ["dependency", "peer"])
def test_real_npm_allows_missing_optional_dependencies_and_peers(tmp_path, optional):
    directory = tmp_path / "project"
    manifest = {"name": "product", "version": "1.0.0"}
    if optional == "dependency":
        manifest["optionalDependencies"] = {"optional-package": "1.0.0"}
    else:
        manifest["peerDependencies"] = {"optional-peer": "1.0.0"}
        manifest["peerDependenciesMeta"] = {"optional-peer": {"optional": True}}
    _write_project(directory, manifest)
    tree = _real_tree(directory, tmp_path)
    assert tree.returncode == 0, tree.stderr
    scan._validate_locked_tree(tree.stdout, tree.returncode)


def test_real_npm_allows_a_complete_dependency_tree(tmp_path):
    directory = tmp_path / "project"
    manifest = {"name": "product", "version": "1.0.0", "dependencies": {"parent": "1.0.0"}}
    _write_project(directory, manifest, {
        "": manifest,
        "node_modules/parent": {"version": "1.0.0", "dependencies": {"child": "1.0.0"}},
        "node_modules/child": {"version": "1.0.0"},
    })
    tree = _real_tree(directory, tmp_path)
    assert tree.returncode == 0, tree.stderr
    scan._validate_locked_tree(tree.stdout, tree.returncode)
