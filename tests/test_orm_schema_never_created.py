"""Tables declared and never created: the most expensive single defect of one product's night.

The browser reported `500` on `POST /api/auth/login`. The login handler was correct — it returns a
token, sets a cookie, raises 401 on bad credentials — and four rounds edited it anyway. What was
actually true:

* 16 tables declared on the ORM base across `backend/app/models/`;
* `backend/alembic/versions/0001_initial.py` describing them;
* and NOTHING running `alembic upgrade` — not the Dockerfile, not docker-compose, not an
  entrypoint, and `main.py` had no startup hook at all.

So every request touching the database raised `OperationalError: no such table` and surfaced as a
bare 500. The demo journey passed the whole time, because the login handler answers demo credentials
from the environment *before* it queries anything: the product looked authenticated end to end while
its database had no schema.

Existing migrations are not a schema. That distinction is the whole detector.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_orm_schema_never_created


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


BASE = "from sqlalchemy.orm import declarative_base\nBase = declarative_base()\nengine = 1\n"
MODEL = 'class User(Base):\n    __tablename__ = "users"\n'
APP = "from fastapi import FastAPI\napp = FastAPI()\n"


def test_the_live_shape_is_found(tmp_path):
    """Migrations present, nobody runs them."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": BASE,
            "backend/app/models/user.py": MODEL,
            "backend/app/main.py": APP,
            "backend/alembic/alembic.ini": "[alembic]\n",
            "backend/alembic/versions/0001_initial.py": "def upgrade():\n    pass\n",
            "Dockerfile": "CMD uvicorn app.main:app\n",
        },
    )
    found = find_orm_schema_never_created(code)
    assert len(found) == 1
    finding = found[0]
    assert finding["file"] == "backend/app/main.py", "the fix belongs at the entrypoint"
    assert finding["tables"] == ["users"]
    assert "migrations exist" in finding["detail"]
    assert "Do not edit the route handlers" in finding["detail"]


def test_a_startup_create_all_satisfies_it(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": BASE,
            "backend/app/models/user.py": MODEL,
            "backend/app/main.py": APP + "Base.metadata.create_all(bind=engine)\n",
        },
    )
    assert find_orm_schema_never_created(code) == []


def test_an_entrypoint_that_runs_migrations_satisfies_it(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": BASE,
            "backend/app/models/user.py": MODEL,
            "backend/app/main.py": APP,
            "Dockerfile": "CMD alembic upgrade head && uvicorn app.main:app\n",
        },
    )
    assert find_orm_schema_never_created(code) == []


def test_a_startup_hook_calling_command_upgrade_satisfies_it(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": BASE,
            "backend/app/models/user.py": MODEL,
            "backend/app/main.py": APP + "from alembic import command\ncommand.upgrade(cfg, 'head')\n",
        },
    )
    assert find_orm_schema_never_created(code) == []


def test_alembics_own_env_module_does_not_count_as_running_them(tmp_path):
    """alembic/env.py calls run_migrations_online() — that is the migration machinery describing
    itself, not the app applying it. Accepting it is exactly how this stayed silent."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": BASE,
            "backend/app/models/user.py": MODEL,
            "backend/app/main.py": APP,
            "backend/alembic/env.py": "def run_migrations_online():\n    command.upgrade(cfg, 'head')\n",
            "backend/alembic/versions/0001_initial.py": "def upgrade():\n    pass\n",
        },
    )
    assert len(find_orm_schema_never_created(code)) == 1


def test_a_product_without_an_orm_is_silent(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": APP})
    assert find_orm_schema_never_created(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not schema_never" in passed, "the health gate can pass with no schema at all"
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "find_orm_schema_never_created(code_root, limit=200)" in score
    assert '"orm_schema_never_created": lambda: d.find_orm_schema_never_created' in dev
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"orm_schema_never_created"' in qa[: qa.index("# Deletions next")]
