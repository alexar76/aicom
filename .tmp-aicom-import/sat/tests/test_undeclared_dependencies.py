"""An import no dependency file declares works in the sandbox and dies in every clean install.

Found in production, which is the only place this class of defect can be found by the gates that
existed. The factory published a full-stack product to Vercel: the page served 200, and every API
route answered FUNCTION_INVOCATION_FAILED. The function log:

    File "/var/task/api/app/utils/security.py", line 7, in <module>
        import jwt
    ModuleNotFoundError: No module named 'jwt'

requirements.txt declared `python-jose[cryptography]` — a different package, providing `jose`, not
`jwt`. Nine green gates, a passing browser E2E, a passing demo journey, and a deploy that could not
serve a single API call. Every gate ran against a sandbox venv that happened to have PyJWT
installed: an environment more generous than production is a test that cannot fail for the reason
that matters.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_undeclared_dependencies


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


LIVE_REQS = (
    "fastapi==0.110.0\nsqlalchemy==2.0.29\npasslib[bcrypt]==1.7.4\n"
    "python-jose[cryptography]==3.3.0\n"
)


def test_the_live_shape_is_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/requirements.txt": LIVE_REQS,
            "backend/app/utils/security.py": "import jwt\nfrom passlib.context import CryptContext\n",
        },
    )
    found = find_undeclared_dependencies(code)
    assert [f["import_root"] for f in found] == ["jwt"]
    assert found[0]["package"] == "pyjwt", "the import name and the package name differ"
    assert found[0]["file"].endswith("requirements.txt"), "the fix belongs where deps are declared"
    assert "ModuleNotFoundError" in found[0]["detail"]


def test_declared_dependencies_are_not_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/requirements.txt": "fastapi==0.110.0\npyjwt==2.8.0\n",
            "backend/app/main.py": "import jwt\nfrom fastapi import FastAPI\n",
        },
    )
    assert find_undeclared_dependencies(code) == []


def test_stdlib_and_local_modules_are_not_dependencies(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/requirements.txt": "fastapi==0.110.0\n",
            "backend/app/main.py": (
                "import os\nimport json\nimport asyncio\n"
                "from app.routers import auth\nfrom fastapi import FastAPI\n"
            ),
            "backend/app/routers/auth.py": "x = 1\n",
        },
    )
    assert find_undeclared_dependencies(code) == []


def test_an_extra_covers_its_own_import(tmp_path):
    """passlib[bcrypt] brings bcrypt; demanding a separate line for it would be noise."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/requirements.txt": "passlib[bcrypt]==1.7.4\n",
            "backend/app/security.py": "import bcrypt\nimport passlib\n",
        },
    )
    assert find_undeclared_dependencies(code) == []


def test_test_only_imports_are_not_demanded_of_production(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/requirements.txt": "fastapi==0.110.0\n",
            "backend/tests/test_auth.py": "import pytest\nimport responses\n",
        },
    )
    assert find_undeclared_dependencies(code) == []


def test_pyproject_declarations_count(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "pyproject.toml": '[project]\ndependencies = ["fastapi>=0.110", "PyJWT>=2.8"]\n',
            "app/main.py": "import jwt\nfrom fastapi import FastAPI\n",
        },
    )
    assert find_undeclared_dependencies(code) == []


def test_a_product_that_declares_nothing_is_left_alone(tmp_path):
    """No requirements file at all is a different defect; this detector has no opinion."""
    code = _tree(tmp_path / "code", {"app/main.py": "import jwt\n"})
    assert find_undeclared_dependencies(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not undeclared_deps" in passed
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "find_undeclared_dependencies(code_root, limit=200)" in score
    assert '"undeclared_dependency": lambda: d.find_undeclared_dependencies' in dev
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"undeclared_dependency"' in qa[: qa.index("# Deletions next")]
