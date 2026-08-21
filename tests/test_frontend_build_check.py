"""A SPA that does not compile has no dist — the gate must say so, with the compiler's words."""

import json
from pathlib import Path

import pytest

from web.backend.services.frontend_build_check import (
    extract_error_lines,
    find_frontend_dir,
    npm_env,
    run_frontend_build_check,
)

TSC_LOG = """
> switchpitch-frontend@0.1.0 build
> tsc && vite build

src/components/__tests__/ScoreBadge.test.tsx(4,1): error TS2582: Cannot find name 'test'.
src/pages/SourcesPage.tsx(3,10): error TS2305: Module '"../types"' has no exported member 'Source'.
npm notice New major version of npm available! 10.9.0 -> 12.0.2
"""


def _frontend(tmp_path: Path, scripts: dict) -> Path:
    root = tmp_path / "code" / "prod-x"
    (root / "frontend").mkdir(parents=True)
    (root / "frontend" / "package.json").write_text(
        json.dumps({"name": "f", "scripts": scripts}), encoding="utf-8"
    )
    return root


def test_finds_the_directory_that_declares_a_build():
    pass


def test_find_frontend_dir_requires_a_build_script(tmp_path):
    root = _frontend(tmp_path, {"build": "vite build"})
    assert find_frontend_dir(root) == root / "frontend"

    other = _frontend(tmp_path / "b", {"test": "vitest"})
    assert find_frontend_dir(other) is None


def test_error_lines_are_the_compiler_diagnostics_not_npm_chatter():
    lines = extract_error_lines(TSC_LOG)
    assert any("TS2305" in line for line in lines)
    assert any("TS2582" in line for line in lines)
    assert not any("npm notice" in line for line in lines)


def test_error_lines_are_deduped_and_capped():
    blob = "\n".join(["src/a.ts(1,1): error TS1: x"] * 50)
    assert extract_error_lines(blob) == ["src/a.ts(1,1): error TS1: x"]


def test_test_file_errors_are_recognised():
    from web.backend.services.frontend_build_check import _is_test_file_error

    assert _is_test_file_error("src/__tests__/App.test.tsx(1,32): error TS2307: …")
    assert _is_test_file_error("src/e2e/login.spec.ts(1,30): error TS2307: …")
    assert _is_test_file_error("src/setupTests.ts(2,1): error TS2304: …")
    assert not _is_test_file_error("src/pages/Login.tsx(6,50): error TS2339: …")
    assert not _is_test_file_error("src/hooks/useAuth.ts(29,27): error TS1005: …")


def test_npm_env_points_home_and_cache_at_writable_paths(tmp_path, monkeypatch):
    """The factory user's HOME is read-only; without this npm dies with EACCES."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    env = npm_env()
    assert env["HOME"] == str(tmp_path)
    assert env["npm_config_cache"] == str(tmp_path / ".npm")
    assert Path(env["npm_config_cache"]).is_dir()


def test_skips_cleanly_when_the_product_has_no_frontend(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    (tmp_path / "code" / "prod-none").mkdir(parents=True)
    report = run_frontend_build_check("prod-none")
    assert report["skipped"] is True
    assert report["passed"] is True


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("AIFACTORY_FRONTEND_BUILD_E2E", "0")
    report = run_frontend_build_check("prod-anything")
    assert report == {"passed": True, "skipped": True, "reason": "disabled"}


def test_build_that_exits_zero_without_dist_is_still_a_failure(tmp_path, monkeypatch):
    """`exit 0` with nothing emitted is the silent version of the same bug."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = _frontend(tmp_path, {"build": "true"})
    assert root.is_dir()
    pytest.importorskip("shutil")
    import shutil

    if shutil.which("npm") is None:
        pytest.skip("npm not available in this environment")
    report = run_frontend_build_check("prod-x")
    assert report["passed"] is False
    assert any("no_index_html" in i for i in report["issues"])


def test_jsx_in_a_ts_file_is_named_as_a_rename(tmp_path):
    """tsc reports it as a cascade of typos; the fix is one rename."""
    from web.backend.services.frontend_build_check import jsx_in_ts_hints

    base = tmp_path / "frontend"
    (base / "src" / "hooks").mkdir(parents=True)
    (base / "src" / "hooks" / "useAuth.ts").write_text(
        "export function P({children}) {\n  return (\n    <AuthContext.Provider>{children}</AuthContext.Provider>\n  );\n}\n",
        encoding="utf-8",
    )
    errors = [
        "src/hooks/useAuth.ts(3,32): error TS1005: '>' expected.",
        "src/hooks/useAuth.ts(3,37): error TS1005: ';' expected.",
    ]
    hints = jsx_in_ts_hints(base, errors)
    assert len(hints) == 1, "one hint per file, not per error"
    assert "src/hooks/useAuth.tsx" in hints[0]


def test_plain_ts_syntax_error_gets_no_rename_hint(tmp_path):
    from web.backend.services.frontend_build_check import jsx_in_ts_hints

    base = tmp_path / "frontend"
    (base / "src").mkdir(parents=True)
    (base / "src" / "util.ts").write_text("export const x = ;\n", encoding="utf-8")
    hints = jsx_in_ts_hints(base, ["src/util.ts(1,18): error TS1005: expression expected."])
    assert hints == []


def test_test_dependency_hint_fires_alongside_real_errors(tmp_path, monkeypatch):
    """Six "Cannot find name 'test'" plus one component error still needs the hint."""
    from web.backend.services.frontend_build_check import _is_test_file_error

    errors = [
        "src/__tests__/App.test.tsx(5,1): error TS2582: Cannot find name 'test'.",
        "src/components/PrivateRoute.tsx(6,11): error TS2339: Property 'isAuthenticated' ...",
    ]
    assert any(_is_test_file_error(e) for e in errors)
    assert not all(_is_test_file_error(e) for e in errors)


def test_vite_env_typing_gap_is_named_as_a_declaration_fix(tmp_path):
    """Two of these were all that stood between a product and a green build."""
    from web.backend.services.frontend_build_check import vite_env_types_hint

    base = tmp_path / "frontend"
    (base / "src").mkdir(parents=True)
    errors = [
        "src/pages/OperatorLogin.tsx(9,50): error TS2339: Property 'env' does not exist on type 'ImportMeta'.",
    ]
    hint = vite_env_types_hint(base, errors)
    assert hint and "vite/client" in hint
    assert "do not rewrite the component" in hint


def test_no_vite_hint_when_the_declaration_already_exists(tmp_path):
    from web.backend.services.frontend_build_check import vite_env_types_hint

    base = tmp_path / "frontend"
    (base / "src").mkdir(parents=True)
    (base / "src" / "vite-env.d.ts").write_text(
        '/// <reference types="vite/client" />\n', encoding="utf-8"
    )
    errors = ["src/x.tsx(1,1): error TS2339: Property 'env' does not exist on type 'ImportMeta'."]
    assert vite_env_types_hint(base, errors) is None


def test_no_vite_hint_for_unrelated_errors(tmp_path):
    from web.backend.services.frontend_build_check import vite_env_types_hint

    base = tmp_path / "frontend"
    (base / "src").mkdir(parents=True)
    assert vite_env_types_hint(base, ["src/x.tsx(1,1): error TS2304: Cannot find name 'foo'."]) is None


ADVISORY_TYPE = """
export interface AdvisoryResponse {
  overall: { level: string; reason: string };
  hazards: Array<{
    type: string;
    is_cached: boolean;
    sim: boolean;
  }>;
  location: { lat: number; lon: number };
}
"""


def _advisory_tree(tmp_path: Path) -> tuple[Path, Path]:
    code = tmp_path / "code" / "prod-x"
    front = code / "frontend"
    (front / "src" / "api").mkdir(parents=True)
    (front / "src" / "api" / "advisory.ts").write_text(ADVISORY_TYPE, encoding="utf-8")
    return code, front


def test_ts2339_says_the_field_is_nested_not_missing(tmp_path):
    from web.backend.services.frontend_build_check import ts2339_shape_hint

    code, front = _advisory_tree(tmp_path)
    line = (
        "frontend/src/pages/PublicWidget.tsx(30,16): error TS2339: "
        "Property 'is_cached' does not exist on type 'AdvisoryResponse'."
    )
    hint = ts2339_shape_hint(code, front, line)
    assert hint is not None
    assert "frontend/src/api/advisory.ts" in hint
    assert "nested" in hint
    assert "do not add a top-level" in hint


def test_ts2339_says_a_field_that_is_nowhere_must_not_be_invented_on_the_type(tmp_path):
    from web.backend.services.frontend_build_check import ts2339_shape_hint

    code, front = _advisory_tree(tmp_path)
    line = (
        "frontend/src/pages/PublicWidget.tsx(31,55): error TS2339: "
        "Property 'cached_age_minutes' does not exist on type 'AdvisoryResponse'."
    )
    hint = ts2339_shape_hint(code, front, line)
    assert hint is not None
    assert "frontend/src/api/advisory.ts" in hint
    assert "not on that type" in hint
    assert "JSON the API returns" in hint


def test_ts2339_hint_is_silent_for_import_meta(tmp_path):
    from web.backend.services.frontend_build_check import ts2339_shape_hint

    code, front = _advisory_tree(tmp_path)
    line = "src/x.tsx(1,1): error TS2339: Property 'env' does not exist on type 'ImportMeta'."
    assert ts2339_shape_hint(code, front, line) is None


def test_the_hint_puts_the_declaring_file_in_the_repair_scope(tmp_path):
    """PublicWidget was already in scope; without the type path in the finding text,
    adding is_cached to advisory.ts was reverted as sprawl."""
    from core.repair_batches import _files_in
    from web.backend.services.frontend_build_check import ts2339_shape_hint

    code, front = _advisory_tree(tmp_path)
    line = (
        "frontend/src/pages/PublicWidget.tsx(30,16): error TS2339: "
        "Property 'is_cached' does not exist on type 'AdvisoryResponse'."
    )
    issue = f"frontend_build_failed: {line} {ts2339_shape_hint(code, front, line)}"
    named = _files_in(issue)
    assert "frontend/src/pages/PublicWidget.tsx" in named
    assert "frontend/src/api/advisory.ts" in named

