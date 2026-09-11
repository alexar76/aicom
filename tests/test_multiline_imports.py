"""Parenthesised imports were invisible to every gate that read imports.

The regex used `[^\n(]+` for the name list, so it stopped at the parenthesis and
never crossed a newline — the single most common Python import style went unchecked.
A product reached a live Vercel deployment with DashboardResponse missing from
app.schemas.operator while the gates reported one unrelated defect.
"""

from pathlib import Path

from web.backend.services.duplicate_module_check import (
    find_hallucinated_imports,
    find_missing_symbols,
    from_imports,
)


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_parenthesised_import_is_parsed():
    src = "from app.schemas.operator import (\n    DashboardResponse,\n    SpendResponse,\n)\n"
    assert from_imports(src) == [("app.schemas.operator", ["DashboardResponse", "SpendResponse"])]


def test_single_line_and_aliases_still_work():
    assert from_imports("from a.b import C\n") == [("a.b", ["C"])]
    assert from_imports("from a.b import C as D\n") == [("a.b", ["C"])]


def test_relative_imports_keep_their_dots():
    assert from_imports("from ..models import X\n") == [("..models", ["X"])]


def test_star_import_is_reported():
    assert from_imports("from a import *\n") == [("a", ["*"])]


def test_the_production_defect_is_now_caught(tmp_path):
    """Exactly what shipped: a multi-line import of a name that does not exist."""
    root = tmp_path / "code" / "prod-x"
    _w(root, "backend/app/schemas/operator.py", "class SpendResponse:\n    pass\n")
    _w(
        root,
        "backend/app/api/routes/operator.py",
        "from app.schemas.operator import (\n    DashboardResponse,\n    SpendResponse,\n)\n",
    )
    missing = {m["symbol"] for m in find_missing_symbols(root)}
    assert "DashboardResponse" in missing
    assert "SpendResponse" not in missing


def test_a_multiline_reexport_counts_as_a_definition(tmp_path):
    root = tmp_path / "code" / "prod-y"
    _w(root, "backend/app/inner.py", "class Thing:\n    pass\n")
    _w(root, "backend/app/facade.py", "from app.inner import (\n    Thing,\n)\n")
    _w(root, "backend/app/user.py", "from app.facade import Thing\n")
    assert find_missing_symbols(root) == []


def test_hallucinated_framework_names_are_caught_in_multiline_form(tmp_path):
    _w(
        tmp_path,
        "app/x.py",
        "from fastapi.responses import (\n    JSONResponse,\n    JavaScriptResponse,\n)\n",
    )
    found = find_hallucinated_imports(tmp_path)
    assert [f["symbol"] for f in found] == ["JavaScriptResponse"]


def test_syntax_error_yields_no_imports_rather_than_raising():
    assert from_imports("from a import (\n") == []
