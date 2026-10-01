"""A framework name that does not exist takes the whole app down at import time."""

from pathlib import Path

from web.backend.services.duplicate_module_check import find_hallucinated_imports


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_the_real_case_is_caught(tmp_path):
    """`from fastapi.responses import JavaScriptResponse` — plausible, nonexistent."""
    _w(tmp_path, "app/api/routes/embed.py", "from fastapi.responses import JavaScriptResponse\n")
    found = find_hallucinated_imports(tmp_path)
    assert len(found) == 1
    assert found[0]["symbol"] == "JavaScriptResponse"
    assert found[0]["module"] == "fastapi.responses"


def test_real_framework_names_are_not_flagged(tmp_path):
    _w(
        tmp_path,
        "app/main.py",
        "from fastapi import FastAPI, APIRouter, Depends\n"
        "from fastapi.responses import JSONResponse, FileResponse, HTMLResponse\n"
        "from starlette.middleware.cors import CORSMiddleware\n",
    )
    assert find_hallucinated_imports(tmp_path) == []


def test_first_party_imports_are_someone_elses_job(tmp_path):
    """Only packages the factory has installed can be judged here."""
    _w(tmp_path, "app/a.py", "from app.core.security import whatever\n")
    assert find_hallucinated_imports(tmp_path) == []


def test_unknown_third_party_packages_are_not_judged(tmp_path):
    """If it is not installed here, absence proves nothing about the product's env."""
    _w(tmp_path, "app/a.py", "from some_exotic_lib import Thing\n")
    assert find_hallucinated_imports(tmp_path) == []


def test_aliased_imports_are_checked_by_their_real_name(tmp_path):
    _w(tmp_path, "app/a.py", "from fastapi.responses import NopeResponse as R\n")
    found = find_hallucinated_imports(tmp_path)
    assert found and found[0]["symbol"] == "NopeResponse"


def test_findings_are_capped(tmp_path):
    body = "\n".join(f"from fastapi.responses import Nope{i}" for i in range(20))
    _w(tmp_path, "app/a.py", body)
    assert len(find_hallucinated_imports(tmp_path, limit=3)) == 3
