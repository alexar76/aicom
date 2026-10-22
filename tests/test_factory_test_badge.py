"""A product's CI badge says what the factory measured, and only that.

The GitHub-house contract told the developer agent to commit docs/badges/ci.svg, the asset
autofix drew a missing one as "ci: passing", and the catalog publish wrote a "passing" SVG of
its own. None of them had run anything (2026-10-21 audit). The badge is now drawn from the
factory's runtime-test stage — docs/badges/factory-tests.json — and from nothing else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from orchestrator.pipeline_worker_sidecars import PipelineWorkerSidecarMixin
from web.backend.services.github_house_assets import (
    CI_BADGE,
    FACTORY_TESTS_RECORD,
    apply_github_house_asset_autofix,
    product_tree_digest,
    record_factory_test_run,
    refresh_factory_test_badge,
)


def _product(root: Path) -> Path:
    (root / "app").mkdir(parents=True)
    (root / "app" / "core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "README.md").write_text(
        '<!-- aicom-readme-badges -->\n<img src="docs/badges/ci.svg" alt="factory tests" />\n'
        "<!-- /aicom-readme-badges -->\n",
        encoding="utf-8",
    )
    return root


def _badge(root: Path) -> str:
    return (root / CI_BADGE).read_text(encoding="utf-8")


PASSED = {"passed": True, "commands": ["python -m pytest tests -q"], "results": [{"exit_code": 0}]}
FAILED = {"passed": False, "commands": ["python -m pytest tests -q"], "results": [{"exit_code": 1}]}


def test_a_passing_run_draws_passed_with_its_date(tmp_path):
    root = _product(tmp_path)
    record = record_factory_test_run(root, PASSED, now=1_792_540_800)  # 2026-10-21
    assert record["status"] == "passed"
    assert record["tree_sha256"] == product_tree_digest(root)
    saved = json.loads((root / FACTORY_TESTS_RECORD).read_text(encoding="utf-8"))
    assert saved["commands"] == ["python -m pytest tests -q"] and saved["exit_codes"] == [0]
    svg = _badge(root)
    assert "factory tests" in svg and "passed 2026-10-21" in svg and "#4c1" in svg


def test_a_failing_run_draws_failed_in_red(tmp_path):
    root = _product(tmp_path)
    record_factory_test_run(root, FAILED)
    svg = _badge(root)
    assert "failed" in svg and "#e05d44" in svg and "passed" not in svg


def test_no_tests_is_not_run_rather_than_passed(tmp_path):
    root = _product(tmp_path)
    record_factory_test_run(root, {"passed": False, "skipped": True, "commands": [], "results": []})
    assert "not run" in _badge(root)


def test_code_changed_after_the_run_is_not_re_run(tmp_path):
    root = _product(tmp_path)
    record_factory_test_run(root, PASSED)
    (root / "app" / "core.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    assert refresh_factory_test_badge(root) == "not re-run"
    assert "passed" not in _badge(root)


def test_docs_and_readme_edits_after_the_run_keep_the_result(tmp_path):
    """The catalog publish edits README badge markers and adds CONTRIBUTING.md afterwards."""
    root = _product(tmp_path)
    record_factory_test_run(root, PASSED)
    (root / "README.md").write_text("# changed\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text("PRs welcome\n", encoding="utf-8")
    (root / "docs" / "badges" / "license.svg").write_text("<svg/>\n", encoding="utf-8")
    (root / "app" / "__pycache__").mkdir()
    (root / "app" / "__pycache__" / "core.cpython-312.pyc").write_bytes(b"\0\1")
    (root / "runtime_test.db").write_bytes(b"sqlite")
    assert refresh_factory_test_badge(root) == "passed"


def test_without_a_record_the_badge_is_not_run(tmp_path):
    root = _product(tmp_path)
    assert refresh_factory_test_badge(root) == "not run"
    assert "not run" in _badge(root) and "passing" not in _badge(root)


def test_the_autofix_replaces_an_agent_drawn_passing_badge(tmp_path):
    root = _product(tmp_path)
    (root / "docs" / "badges").mkdir(parents=True)
    (root / CI_BADGE).write_text('<svg><text>ci</text><text>passing</text></svg>\n', encoding="utf-8")
    notes = apply_github_house_asset_autofix(root)
    assert "docs/badges/ci.svg:not run" in notes
    assert "passing" not in _badge(root)


def test_unmeasured_coverage_and_tests_badges_say_so(tmp_path):
    root = _product(tmp_path)
    (root / "README.md").write_text(
        '<img src="docs/badges/coverage.svg" alt="coverage" />\n'
        '<img src="docs/badges/tests.svg" alt="tests" />\n',
        encoding="utf-8",
    )
    apply_github_house_asset_autofix(root)
    coverage = (root / "docs" / "badges" / "coverage.svg").read_text(encoding="utf-8")
    tests = (root / "docs" / "badges" / "tests.svg").read_text(encoding="utf-8")
    assert "not measured" in coverage and "not counted" in tests
    assert ">ok<" not in coverage + tests


def test_the_runtime_test_stage_records_its_own_run(tmp_path):
    """The pipeline stage itself writes the record into the product tree it tested."""
    pid = "prod-badge"
    code = _product(tmp_path / "code" / pid)
    (code / "tests").mkdir()
    (code / "tests" / "test_core.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
        "from app.core import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    host = SimpleNamespace(data_root=tmp_path)
    host._infer_default_test_commands = lambda workdir: [f"{sys.executable} -m pytest tests -q -p no:cacheprovider"]
    result = PipelineWorkerSidecarMixin._run_runtime_tests(host, pid, [])
    assert result["passed"], result
    record = json.loads((code / FACTORY_TESTS_RECORD).read_text(encoding="utf-8"))
    assert record["status"] == "passed" and record["exit_codes"] == [0]
    assert refresh_factory_test_badge(code) == "passed"
