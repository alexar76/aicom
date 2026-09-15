"""A finding that names a path nothing can resolve is a dead end, and three gates depended on it.

`tsc` prints paths relative to the frontend directory. Everything downstream treats a path in a finding
as repo-relative: the repair scope, the file attachment, the edit applier. So a real error arrived as

    frontend_build_failed: src/api/advisory.ts(24,36): error TS2339 …

for a file that lives at `frontend/src/api/advisory.ts`. Measured consequences, all in one round:

    область ремонта: []                                   ← no such file, so no scope
    2 edit(s) did not apply: src/api/advisory.ts: no such file — use `files` to create it
                            src/components/Operator/Dashboard.tsx: no such file

No scope means no attachment, no attachment means the round guesses, and the guess names the
unresolvable path again. The frontend build, the demo journey and the browser crawl all wait behind it.
"""

from __future__ import annotations

from web.backend.services.frontend_build_check import _repo_relative


def test_a_tsc_path_becomes_repo_relative():
    line = "src/api/advisory.ts(24,36): error TS2339: Property 'get' does not exist"
    assert _repo_relative(line, "frontend").startswith("frontend/src/api/advisory.ts(24,36)")


def test_a_path_already_repo_relative_is_left_alone():
    """Otherwise a second pass produces frontend/frontend/src/…"""
    line = "frontend/src/already.ts(1,1): error TS1005"
    assert _repo_relative(line, "frontend") == line
    assert _repo_relative(_repo_relative(line, "frontend"), "frontend") == line


def test_a_frontend_at_the_repo_root_changes_nothing():
    line = "src/api/advisory.ts(1,1): error TS1005"
    assert _repo_relative(line, ".") == line
    assert _repo_relative(line, "") == line


def test_a_nested_frontend_directory_is_honoured():
    line = "src/main.tsx(3,3): error TS2304"
    assert _repo_relative(line, "apps/web").startswith("apps/web/src/main.tsx")


def test_lines_without_a_path_survive_untouched():
    for line in ("no path in this line at all", "npm run build exited 1: ELIFECYCLE"):
        assert _repo_relative(line, "frontend") == line


def test_every_directory_the_error_can_start_with_is_covered():
    for head in ("src", "app", "pages", "components", "lib", "tests", "test"):
        line = f"{head}/thing.tsx(1,1): error TS1005"
        assert _repo_relative(line, "frontend") == f"frontend/{line}"


def test_the_gate_applies_it_before_building_the_issue_list():
    """Inert unless the rewrite happens upstream of the text every consumer reads."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "frontend_build_check.py"
    ).read_text(encoding="utf-8")
    rewrite = src.index("errors = [_repo_relative(line, rel) for line in errors]")
    emit = src.index("extra = ts2339_shape_hint(product_code, base, line)")
    assert rewrite < emit
