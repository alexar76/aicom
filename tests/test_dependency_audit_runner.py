"""The local security gate must preserve scanner failures and leave packages alone."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_dependency_audit.sh"


@pytest.mark.parametrize("failed_tool", ["", "bandit", "pip_audit", "frontend", "typescript"])
def test_audit_collects_failures_without_mutating_dependencies(tmp_path, failed_tool):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
    for directory in ("web/frontend", "aimarket-sdks/typescript"):
        folder = tmp_path / directory
        folder.mkdir(parents=True)
        (folder / "package-lock.json").write_text("{}\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    scanner = binary_dir / "scanner"
    scanner.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "tool = args[1] if args[:1] == ['-m'] else pathlib.Path.cwd().name\n"
        "with open(os.environ['AUDIT_CALLS'], 'a') as log:\n"
        "    log.write(json.dumps({'tool': tool, 'args': args}) + '\\n')\n"
        "sys.exit(3 if tool == os.environ.get('AUDIT_FAIL_TOOL') else 0)\n",
        encoding="utf-8",
    )
    scanner.chmod(0o700)
    (binary_dir / "npm").symlink_to(scanner)
    log = tmp_path / "calls.jsonl"
    result = subprocess.run(
        ["bash", str(scripts / SCRIPT.name)],
        env={
            **os.environ,
            "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
            "AIFACTORY_AUDIT_PYTHON": str(scanner),
            "AUDIT_CALLS": str(log),
            "AUDIT_FAIL_TOOL": failed_tool,
        },
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == (1 if failed_tool else 0), result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [call["tool"] for call in calls] == ["bandit", "pip_audit", "frontend", "typescript"]
    for call in calls[2:]:
        assert call["args"] == [
            "audit", "--package-lock-only", "--ignore-scripts", "--include=dev", "--audit-level=high",
        ]
    assert all("install" not in call["args"] and "ci" not in call["args"] for call in calls)
    report = Path(calls[1]["args"][calls[1]["args"].index("-o") + 1])
    assert report == tmp_path / ".internal/audit/pip-audit-report.json"
    assert not (tmp_path / "pip-audit-report.json").exists()


def test_explicit_missing_audit_python_is_an_error(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "AIFACTORY_AUDIT_PYTHON": str(tmp_path / "missing-python")},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "Audit Python is unavailable" in result.stderr
