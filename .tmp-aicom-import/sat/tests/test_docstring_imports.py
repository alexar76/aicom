"""Guard: imports must not live inside module docstrings."""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECK_SCRIPT = _REPO_ROOT / "scripts" / "check_docstring_imports.py"

# Files that must bind log_suppressed at module level (runtime NameError otherwise).
_LOG_SUPPRESSED_FILES = (
    "agents/base_agent.py",
    "agents/dev.py",
    "llm/router.py",
    "director/worker.py",
    "director/scheduler.py",
)


def _module_has_log_suppressed_import(rel_path: str) -> bool:
    path = _REPO_ROOT / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "core.logging_utils":
            if any(alias.name == "log_suppressed" for alias in node.names):
                return True
    return False


def test_no_imports_inside_module_docstrings():
    proc = subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.parametrize("rel_path", _LOG_SUPPRESSED_FILES)
def test_log_suppressed_import_at_module_level(rel_path: str):
    assert _module_has_log_suppressed_import(rel_path), (
        f"{rel_path} must import log_suppressed from core.logging_utils at module level"
    )


def test_base_agent_log_suppressed_runtime():
    mod = importlib.import_module("agents.base_agent")
    assert callable(vars(mod).get("log_suppressed")), "agents.base_agent.log_suppressed must be callable"

def test_the_gate_separates_a_trapped_import_from_a_usage_example(tmp_path):
    """A moved triple-quote leaves the import at column 0; an example is indented.

    Without that distinction the gate failed CI on nine files, all of them correct —
    rst `::` blocks, quoted tracebacks and "how to call this" snippets in
    `aimarket-bridges`, `awr`, `oracle-core` and two tests. A gate that is red on
    correct code is a gate everyone learns to ignore, so this pins both directions.
    """
    (tmp_path / "trapped.py").write_text(
        '"""A refactor moved these under the quote.\n\nimport logging\n"""\n',
        encoding="utf-8",
    )
    (tmp_path / "example.py").write_text(
        '"""Usage::\n\n    import logging\n"""\n',
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT), str(tmp_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 1, out
    assert "trapped.py" in out
    assert "example.py" not in out


def test_a_virtualenv_under_the_repo_is_not_first_party_source(tmp_path):
    """`signal-hunt/.venv-test/` matched none of the four hard-coded venv spellings,
    so vendored `_pytest` and `urllib3` docstrings were reported as our defects. A
    `pyvenv.cfg` marks the tree regardless of what it is called."""
    venv = tmp_path / ".venv-whatever"
    (venv / "lib").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (venv / "lib" / "vendored.py").write_text(
        '"""Third party.\n\nimport logging\n"""\n', encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT), str(tmp_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
