"""Tests for QA project realism heuristics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agents.qa import QAAgent


def _mk_agent(tmp_path: Path) -> QAAgent:
    agent = QAAgent(llm_router=MagicMock())
    agent.data_root = tmp_path
    return agent


def test_assess_project_realism_flags_thin_backend(tmp_path: Path):
    pid = "prod-thin-backend"
    code_dir = tmp_path / "code" / pid
    code_dir.mkdir(parents=True)
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef h():\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    qa = _mk_agent(tmp_path)
    code_files = [
        {
            "path": str(code_dir / "main.py"),
            "content": (code_dir / "main.py").read_text(encoding="utf-8"),
        }
    ]
    issues = qa._assess_project_realism(pid, code_files)
    titles = {i.get("title") for i in issues}
    assert "Backend realism: missing explicit test files" in titles
    assert "Backend realism: missing README" in titles
    assert "Backend realism: structure too thin" in titles


def test_assess_project_realism_accepts_structured_backend(tmp_path: Path):
    pid = "prod-structured-backend"
    code_dir = tmp_path / "code" / pid
    tests_dir = code_dir / "tests"
    tests_dir.mkdir(parents=True)
    (code_dir / "README.md").write_text("# Product\nRun tests with pytest\n", encoding="utf-8")
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (code_dir / "service.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tests_dir / "test_service.py").write_text(
        "from service import add\n\ndef test_add():\n    assert add(1,2) == 3\n",
        encoding="utf-8",
    )

    qa = _mk_agent(tmp_path)
    code_files = []
    for p in (code_dir / "main.py", code_dir / "service.py", tests_dir / "test_service.py"):
        code_files.append({"path": str(p), "content": p.read_text(encoding="utf-8")})
    issues = qa._assess_project_realism(pid, code_files)
    assert issues == []


def test_assess_project_realism_flags_mocked_api_auth(tmp_path: Path):
    pid = "prod-mock-auth"
    code_dir = tmp_path / "code" / pid
    tests_dir = code_dir / "tests"
    tests_dir.mkdir(parents=True)
    (code_dir / "README.md").write_text("# Product\n", encoding="utf-8")
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/api/auth/login')\n"
        "def login():\n"
        "    return {'token': 'mock-jwt-token'}\n",
        encoding="utf-8",
    )
    (code_dir / "service.py").write_text("def health():\n    return {'ok': True}\n", encoding="utf-8")
    (tests_dir / "test_service.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    qa = _mk_agent(tmp_path)
    code_files = []
    for p in (code_dir / "main.py", code_dir / "service.py", tests_dir / "test_service.py"):
        code_files.append({"path": str(p), "content": p.read_text(encoding="utf-8")})
    issues = qa._assess_project_realism(pid, code_files)
    titles = {i.get("title") for i in issues}
    assert "Backend realism: mocked API auth response" in titles


def test_assess_project_realism_flags_constant_only_api_responses(tmp_path: Path):
    pid = "prod-static-api"
    code_dir = tmp_path / "code" / pid
    tests_dir = code_dir / "tests"
    tests_dir.mkdir(parents=True)
    (code_dir / "README.md").write_text("# Product\n", encoding="utf-8")
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/api/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n"
        "@app.get('/api/profile')\n"
        "def profile():\n"
        "    return {'name': 'demo', 'plan': 'free'}\n",
        encoding="utf-8",
    )
    (code_dir / "service.py").write_text("def noop():\n    return None\n", encoding="utf-8")
    (tests_dir / "test_service.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    qa = _mk_agent(tmp_path)
    code_files = []
    for p in (code_dir / "main.py", code_dir / "service.py", tests_dir / "test_service.py"):
        code_files.append({"path": str(p), "content": p.read_text(encoding="utf-8")})
    issues = qa._assess_project_realism(pid, code_files)
    titles = {i.get("title") for i in issues}
    assert "Backend realism: constant-only API responses" in titles
    assert "Backend realism: no stateful behavior signals" in titles


def test_assess_project_realism_detects_stateful_backend_signals(tmp_path: Path):
    pid = "prod-stateful-api"
    code_dir = tmp_path / "code" / pid
    tests_dir = code_dir / "tests"
    tests_dir.mkdir(parents=True)
    (code_dir / "README.md").write_text("# Product\n", encoding="utf-8")
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from service import create_user\n"
        "app = FastAPI()\n"
        "@app.post('/api/users')\n"
        "def create(payload: dict):\n"
        "    return create_user(payload)\n",
        encoding="utf-8",
    )
    (code_dir / "service.py").write_text(
        "STORE = []\n"
        "def create_user(payload):\n"
        "    STORE.append(payload)\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    (tests_dir / "test_service.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    qa = _mk_agent(tmp_path)
    code_files = []
    for p in (code_dir / "main.py", code_dir / "service.py", tests_dir / "test_service.py"):
        code_files.append({"path": str(p), "content": p.read_text(encoding="utf-8")})
    issues = qa._assess_project_realism(pid, code_files)
    titles = {i.get("title") for i in issues}
    assert "Backend realism: no stateful behavior signals" not in titles


def test_assess_session_token_salt_flags_relay_mismatch(tmp_path: Path):
    pid = "prod-relay-salt"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_session_token_salt(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/routers/auth.py",
                "content": (
                    "return serializer.dumps({'sub': str(operator_id)}, "
                    "salt='relay-access-token')\n"
                    'response.set_cookie(key="session", value=token)\n'
                ),
            },
            {
                "path": f"code/{pid}/backend/app/routers/handoffs.py",
                "content": 'URLSafeTimedSerializer(secret, salt="relay-session")\n',
            },
            {
                "path": f"code/{pid}/backend/app/deps.py",
                "content": 'SESSION_COOKIE_NAME = "relay_session"\n',
            },
        ],
    )
    titles = {i.get("title") for i in issues}
    assert "API contract: login token salt does not match protected routes" in titles
    assert "API contract: login cookie name does not match session reader" in titles


def test_assess_session_token_salt_clean_after_create_session_token(tmp_path: Path):
    pid = "prod-relay-fixed"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_session_token_salt(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/routers/auth.py",
                "content": "from ..security import create_session_token\nreturn create_session_token(str(operator_id))\n",
            },
            {
                "path": f"code/{pid}/backend/app/security.py",
                "content": 'salt="relay-session"\n',
            },
        ],
    )
    assert issues == []


def test_assess_uuid_pk_lookup_flags_raw_operator_id(tmp_path: Path):
    pid = "prod-relay-uuid"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_uuid_pk_lookup(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/routers/handoffs.py",
                "content": (
                    "operator_id = data.get('sub')\n"
                    "return db.query(Operator).filter(Operator.id == operator_id).first()\n"
                ),
            }
        ],
    )
    titles = {i.get("title") for i in issues}
    assert "API contract: string UUID compared to UUID column" in titles


def test_assess_uuid_pk_lookup_clean_after_coerce(tmp_path: Path):
    pid = "prod-relay-uuid-fixed"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_uuid_pk_lookup(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/routers/handoffs.py",
                "content": (
                    "return db.query(Operator).filter("
                    'Operator.id == __import__("uuid").UUID(str(operator_id))'
                    ").first()\n"
                ),
            }
        ],
    )
    assert issues == []


def test_assess_relay_pinned_compat_flags_raw_receipt_uuid(tmp_path: Path):
    pid = "prod-relay-pin"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_relay_pinned_compat(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/services/receipt.py",
                "content": '"handoff_id": handoff.id,\n"approval_state": handoff.status.value,\n',
            }
        ],
    )
    titles = {i.get("title") for i in issues}
    assert "API contract: Relay enum/ORM fragment not coerced" in titles


def test_assess_relay_pinned_compat_clean_after_coerce(tmp_path: Path):
    pid = "prod-relay-pin-fixed"
    qa = _mk_agent(tmp_path)
    issues = qa._assess_relay_pinned_compat(
        pid,
        [
            {
                "path": f"code/{pid}/backend/app/services/receipt.py",
                "content": '"handoff_id": str(handoff.id),\n',
            }
        ],
    )
    assert issues == []
