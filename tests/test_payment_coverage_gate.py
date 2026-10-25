"""A missing report, absent branch data or rounded percentage must never pass the gate."""
from __future__ import annotations

import json

import pytest

from scripts.check_payment_coverage import TARGETS, main


@pytest.fixture
def coverage_report(tmp_path):
    report = {"meta": {"branch_coverage": True}, "files": {}}
    for filename, function, _, _ in TARGETS:
        file = report["files"].setdefault(filename, {"functions": {}})
        file["functions"][function] = {"summary": {
            "covered_lines": 1000, "num_statements": 1000,
            "covered_branches": 1000, "num_branches": 1000,
        }}
    return tmp_path / "coverage.json", report


def save_and_run(fixture):
    path, report = fixture
    path.write_text(json.dumps(report))
    return main([str(path)])


def test_full_coverage_passes(coverage_report):
    assert save_and_run(coverage_report) == 0


@pytest.mark.parametrize("axis", ["covered_lines", "covered_branches"])
def test_each_function_enforces_both_unrounded_floors(coverage_report, axis):
    _, report = coverage_report
    for filename, function, line_floor, branch_floor in TARGETS:
        summary = report["files"][filename]["functions"][function]["summary"]
        floor = line_floor if axis == "covered_lines" else branch_floor
        summary[axis] = floor * 10 - 1
        assert save_and_run(coverage_report) == 1
        summary[axis] += 1
        assert save_and_run(coverage_report) == 0
        summary[axis] = 1000


@pytest.mark.parametrize("damage", ["no-branches", "missing-file", "missing-function", "zero-lines", "impossible", "nan", "boolean"])
def test_incomplete_or_invalid_report_is_an_error(coverage_report, damage):
    _, report = coverage_report
    filename, function, _, _ = TARGETS[0]
    summary = report["files"][filename]["functions"][function]["summary"]
    if damage == "no-branches":
        report["meta"]["branch_coverage"] = False
    elif damage == "missing-file":
        del report["files"][filename]
    elif damage == "missing-function":
        del report["files"][filename]["functions"][function]
    elif damage == "zero-lines":
        summary.update(covered_lines=0, num_statements=0)
    else:
        summary["covered_lines"] = {"impossible": 1001, "nan": float("nan"), "boolean": True}[damage]
    assert save_and_run(coverage_report) == 2


@pytest.mark.parametrize("body", [None, "[]", "invalid", "{}"])
def test_missing_or_malformed_file_is_an_error(tmp_path, body):
    path = tmp_path / "coverage.json"
    if body is not None:
        path.write_text(body)
    assert main([str(path)]) == 2
