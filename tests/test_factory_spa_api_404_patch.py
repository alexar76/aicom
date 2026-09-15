"""Factory patches that keep live-gate / sandbox previews honest."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.vercel_fullstack_adapter import (
    ensure_settings_module_export,
    patch_spa_api_not_found_tuple,
)


def test_patch_spa_api_not_found_tuple(tmp_path: Path):
    main = tmp_path / "app" / "main.py"
    main.parent.mkdir(parents=True)
    main.write_text(
        "from fastapi.responses import FileResponse\n"
        "\n"
        "@app.get('/{full_path:path}')\n"
        "async def serve_spa(full_path: str):\n"
        "    if full_path.startswith('api/'):\n"
        "        return {'detail': 'Not Found'}, 404\n"
        "    return FileResponse('x')\n",
        encoding="utf-8",
    )
    notes = patch_spa_api_not_found_tuple(tmp_path)
    assert notes == ["app/main.py"]
    text = main.read_text(encoding="utf-8")
    assert "JSONResponse" in text
    assert "status_code=404" in text
    assert ", 404" not in text.split("serve_spa", 1)[1].split("return FileResponse", 1)[0]
    assert patch_spa_api_not_found_tuple(tmp_path) == []


def test_ensure_settings_module_export(tmp_path: Path):
    cfg = tmp_path / "config.py"
    cfg.write_text(
        "def get_settings():\n    return object()\n",
        encoding="utf-8",
    )
    notes = ensure_settings_module_export(tmp_path)
    assert notes == ["config.py"]
    text = cfg.read_text(encoding="utf-8")
    assert "settings = _AicomSettingsView(get_settings())" in text
    assert 'name in ("ALGORITHM"' in text
    assert ensure_settings_module_export(tmp_path) == []


def test_patch_deterministic_demo_user_seed(tmp_path: Path):
    seed = tmp_path / "seed.py"
    seed.write_text(
        "from .models.user import User\n"
        "\n"
        "def seed_demo_user() -> None:\n"
        "    email = 'a@b.com'\n"
        "    user = User(\n"
        "        email=email,\n"
        "        hashed_password='x',\n"
        "        role='admin',\n"
        "    )\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import patch_deterministic_demo_user_seed

    notes = patch_deterministic_demo_user_seed(tmp_path)
    assert notes == ["seed.py"]
    text = seed.read_text(encoding="utf-8")
    assert "_aicom_demo_user_id" in text
    assert "id=_aicom_demo_user_id(email)" in text
    assert patch_deterministic_demo_user_seed(tmp_path) == []


def test_patch_auth_login_to_use_seed_helper(tmp_path: Path):
    auth = tmp_path / "routers" / "auth.py"
    auth.parent.mkdir(parents=True)
    auth.write_text(
        "from ..db import get_db\n"
        "from ..utils.security import hash_password\n"
        "import os\n"
        "_demo_seeded = False\n"
        "\n"
        "@router.post('/login')\n"
        "async def login(login_data, db):\n"
        "    global _demo_seeded\n"
        "    # Seed demo user exactly once per process (cold start safe)\n"
        "    if not _demo_seeded:\n"
        "        demo_email = os.environ.get('SANDBOX_DEMO_EMAIL')\n"
        "        demo_password = os.environ.get('SANDBOX_DEMO_PASSWORD')\n"
        "        if demo_email and demo_password:\n"
        "            try:\n"
        "                existing = db.query(User).filter(User.email == demo_email).first()\n"
        "                if not existing:\n"
        "                    hashed = hash_password(demo_password)\n"
        "                    db.add(User(email=demo_email, hashed_password=hashed, role='admin'))\n"
        "                    db.commit()\n"
        "            except Exception:\n"
        "                db.rollback()\n"
        "        _demo_seeded = True\n"
        '    token = jwt.encode({"sub": str(user.id), "email": user.email}, secret)\n'
        "    user = db.query(User).filter(User.email == login_data.email).first()\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import patch_auth_login_to_use_seed_helper

    notes = patch_auth_login_to_use_seed_helper(tmp_path)
    assert notes == ["routers/auth.py"]
    text = auth.read_text(encoding="utf-8")
    assert "seed_demo_user(db)" in text
    assert "_demo_seeded" not in text
    assert "from ..services.seeding import seed_demo_user" in text
    assert '"sub": user.email' in text
    assert "str(user.id)" not in text
    assert patch_auth_login_to_use_seed_helper(tmp_path) == []


def test_patch_get_current_user_stable_identity(tmp_path: Path):
    deps = tmp_path / "deps.py"
    deps.write_text(
        "from app.db import get_db\n"
        "from app.models.user import User\n"
        "from app.config import settings\n"
        "from jose import JWTError, jwt\n"
        "\n"
        "async def get_current_user(credentials, db):\n"
        "    token = credentials.credentials\n"
        "    try:\n"
        '        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])\n'
        '        email: str = payload.get("sub")\n'
        "        if email is None:\n"
        "            raise HTTPException(status_code=401, detail='Invalid token')\n"
        "    except JWTError:\n"
        "        raise HTTPException(status_code=401, detail='Invalid token')\n"
        "    user = db.query(User).filter(User.email == email).first()\n"
        "    if user is None:\n"
        "        raise HTTPException(status_code=401, detail='User not found')\n"
        "    return user\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        patch_get_current_user_stable_identity,
    )

    notes = patch_get_current_user_stable_identity(tmp_path)
    assert notes == ["deps.py"]
    text = deps.read_text(encoding="utf-8")
    assert "seed_demo_user(db)" in text
    assert 'payload.get("email") or payload.get("sub")' in text
    assert "User.id == str(email)" in text
    assert patch_get_current_user_stable_identity(tmp_path) == []


def test_apply_live_auth_autofix_writes_the_product_tree(tmp_path: Path):
    """Factory must patch data/code/<id>, not wait for Cursor to SSH the product."""
    app = tmp_path / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (routers / "auth.py").write_text(
        "from ..db import get_db\n"
        "from ..utils.security import hash_password\n"
        "import os\n"
        "_demo_seeded = False\n"
        "\n"
        "@router.post('/login')\n"
        "async def login(login_data, db):\n"
        "    global _demo_seeded\n"
        "    if not _demo_seeded:\n"
        "        demo_email = os.environ.get('SANDBOX_DEMO_EMAIL')\n"
        "        demo_password = os.environ.get('SANDBOX_DEMO_PASSWORD')\n"
        "        if demo_email and demo_password:\n"
        "            try:\n"
        "                existing = db.query(User).filter(User.email == demo_email).first()\n"
        "                if not existing:\n"
        "                    hashed = hash_password(demo_password)\n"
        "                    db.add(User(email=demo_email, hashed_password=hashed, role='admin'))\n"
        "                    db.commit()\n"
        "            except Exception:\n"
        "                db.rollback()\n"
        "        _demo_seeded = True\n"
        '    token = jwt.encode({"sub": str(user.id), "email": user.email}, secret)\n',
        encoding="utf-8",
    )
    (app / "deps.py").write_text(
        "from app.db import get_db\n"
        "from app.models.user import User\n"
        "async def get_current_user(credentials, db):\n"
        '    email: str = payload.get("sub")\n'
        "    user = db.query(User).filter(User.email == email).first()\n",
        encoding="utf-8",
    )
    (tmp_path / "backend" / "requirements.txt").write_text(
        "passlib==1.7.4\nbcrypt==4.2.0\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import apply_live_auth_autofix

    notes = apply_live_auth_autofix(tmp_path)
    assert any(n.startswith("auth_seed:") for n in notes)
    assert any(n.startswith("jwt_identity:") for n in notes)
    assert any(n.startswith("bcrypt_pin:") for n in notes)
    auth = (routers / "auth.py").read_text(encoding="utf-8")
    assert "seed_demo_user(db)" in auth
    assert '"sub": user.email' in auth
    deps = (app / "deps.py").read_text(encoding="utf-8")
    assert 'payload.get("email") or payload.get("sub")' in deps
    reqs = (tmp_path / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "bcrypt==4.0.1" in reqs
    assert apply_live_auth_autofix(tmp_path) == []


def test_apply_live_auth_autofix_aligns_relay_token_salt_without_spa_js(tmp_path: Path):
    """Salt mismatch must be written into data/code even when public JS has no CSRF call."""
    app = tmp_path / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (app / "security.py").write_text(
        'from itsdangerous import URLSafeTimedSerializer\n'
        'serializer = URLSafeTimedSerializer("s", salt="relay-session")\n'
        "def create_session_token(operator_id: str) -> str:\n"
        '    return serializer.dumps({"operator_id": operator_id})\n',
        encoding="utf-8",
    )
    (app / "deps.py").write_text('SESSION_COOKIE_NAME = "relay_session"\n', encoding="utf-8")
    (routers / "auth.py").write_text(
        '''
from fastapi import APIRouter, Response
router = APIRouter()

def _create_access_token(operator_id) -> str:
    """Create a signed token carrying the operator id."""
    from itsdangerous import URLSafeTimedSerializer
    secret = getattr(settings, "SESSION_SECRET", "dev-secret")
    serializer = URLSafeTimedSerializer(secret)
    return serializer.dumps({"sub": str(operator_id)}, salt="relay-access-token")

def _set_session_cookie(response: Response, operator_id) -> str:
    token = _create_access_token(operator_id)
    response.set_cookie(key="session", value=token, httponly=True)
    return token

@router.post("/api/auth/login")
def login_api():
    return {"access_token": "x"}
''',
        encoding="utf-8",
    )
    (routers / "handoffs.py").write_text(
        'secret = getattr(settings, "SESSION_SECRET", None) or getattr('
        'settings, "SECRET_KEY", "insecure-dev-secret")\n'
        's = URLSafeTimedSerializer(secret, salt="relay-session")\n',
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        apply_live_auth_autofix,
        relay_source_session_mismatch,
    )

    assert relay_source_session_mismatch(tmp_path) is True
    notes = apply_live_auth_autofix(tmp_path)
    assert any(n.startswith("relay_token_salt:") for n in notes)
    auth = (routers / "auth.py").read_text(encoding="utf-8")
    assert "create_session_token" in auth
    assert "relay-access-token" not in auth
    assert 'key="relay_session"' in auth
    handoffs = (routers / "handoffs.py").read_text(encoding="utf-8")
    assert "session_secret" in handoffs
    assert relay_source_session_mismatch(tmp_path) is False
    assert apply_live_auth_autofix(tmp_path) == []


def test_apply_live_auth_autofix_does_not_import_missing_seed_on_relay_login(tmp_path: Path):
    """``def login_root`` must not match Sentinel's ``def login`` seed helper."""
    app = tmp_path / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (routers / "auth.py").write_text(
        "from ..db import get_db\n"
        "def _create_access_token(operator_id) -> str:\n"
        "    return str(operator_id)\n"
        "def login_root():\n"
        "    return _authenticate()\n"
        "def login_api():\n"
        "    return _authenticate()\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import apply_live_auth_autofix

    notes = apply_live_auth_autofix(tmp_path)
    assert not any(n.startswith("auth_seed:") for n in notes)
    text = (routers / "auth.py").read_text(encoding="utf-8")
    assert "seed_demo_user" not in text


def test_apply_live_auth_autofix_drops_orphan_seed_import(tmp_path: Path):
    app = tmp_path / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (routers / "auth.py").write_text(
        "# aicom-factory-auth-seed-helper\n"
        "from ..db import get_db\n"
        "from ..services.seeding import seed_demo_user\n"
        "def login_api():\n"
        "    return _authenticate()\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import apply_live_auth_autofix

    notes = apply_live_auth_autofix(tmp_path)
    assert any(n.startswith("orphan_seed_import:") for n in notes)
    text = (routers / "auth.py").read_text(encoding="utf-8")
    assert "seed_demo_user" not in text
    assert "aicom-factory-auth-seed-helper" not in text


def test_apply_live_auth_autofix_coerces_relay_uuid_pk_lookups(tmp_path: Path):
    """String token subject must not hit a SQLAlchemy UUID column raw."""
    app = tmp_path / "backend" / "app"
    routers = app / "routers"
    services = app / "services"
    routers.mkdir(parents=True)
    services.mkdir(parents=True)
    (routers / "handoffs.py").write_text(
        "def verify_access_token(token: str, db):\n"
        "    operator_id = data.get('operator_id') or data.get('sub')\n"
        "    return db.query(Operator).filter(Operator.id == operator_id).first()\n",
        encoding="utf-8",
    )
    (services / "handoff_service.py").write_text(
        "def get_handoff(db, handoff_id, workspace):\n"
        "    return db.query(Handoff).filter(\n"
        "        Handoff.id == handoff_id, Handoff.workspace_id == workspace.id\n"
        "    ).first()\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        apply_live_auth_autofix,
        relay_source_uuid_pk_mismatch,
    )

    assert relay_source_uuid_pk_mismatch(tmp_path) is True
    notes = apply_live_auth_autofix(tmp_path)
    assert any(n.startswith("relay_uuid_pk:") for n in notes)
    handoffs = (routers / "handoffs.py").read_text(encoding="utf-8")
    assert 'Operator.id == __import__("uuid").UUID(str(operator_id))' in handoffs
    assert "Operator.id == operator_id" not in handoffs
    service = (services / "handoff_service.py").read_text(encoding="utf-8")
    assert 'Handoff.id == __import__("uuid").UUID(str(handoff_id))' in service
    assert relay_source_uuid_pk_mismatch(tmp_path) is False
    assert apply_live_auth_autofix(tmp_path) == []


def test_apply_live_auth_autofix_applies_relay_pinned_enum_orm_fragments(tmp_path: Path):
    """Factory must write AEGIS's fail-fast Relay pin into data/code, not Docker sed."""
    app = tmp_path / "backend" / "app"
    services = app / "services"
    schemas = app / "schemas"
    routers = app / "routers"
    services.mkdir(parents=True)
    schemas.mkdir(parents=True)
    routers.mkdir(parents=True)
    (routers / "handoffs.py").write_text("router = APIRouter(tags=[\"handoffs\"])\n", encoding="utf-8")
    (services / "handoff_service.py").write_text(
        "payload_json=json.dumps(\n"
        "    {\n"
        '        "items": [\n'
        '            {"category": it.category.value, "passed": it.passed}\n'
        "            for it in persisted\n"
        "        ],\n"
        '        "source": verification_source.value,\n'
        "    }\n"
        ")\n",
        encoding="utf-8",
    )
    (services / "receipt.py").write_text(
        "return {\n"
        '    "category": vi.category.value,\n'
        '    "handoff_id": handoff.id,\n'
        '    "approval_state": handoff.status.value,\n'
        '    "verification_source": handoff.verification_source.value,\n'
        "}\n",
        encoding="utf-8",
    )
    (services / "audit.py").write_text(
        "out.append({\n"
        '    "id": e.id,\n'
        '    "action": e.action.value,\n'
        "})\n",
        encoding="utf-8",
    )
    (schemas / "__init__.py").write_text(
        "from pydantic import BaseModel, Field\n\nclass HandoffOut(BaseModel):\n    id: str\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        apply_live_auth_autofix,
        relay_source_pinned_mismatch,
        relay_source_pinned_structure_break,
    )

    assert relay_source_pinned_mismatch(tmp_path) is True
    notes = apply_live_auth_autofix(tmp_path)
    assert any(n.startswith("relay_pinned:") for n in notes)
    receipt = (services / "receipt.py").read_text(encoding="utf-8")
    assert "str(handoff.id)" in receipt
    assert "hasattr(handoff.status" in receipt
    audit = (services / "audit.py").read_text(encoding="utf-8")
    assert "str(e.id)" in audit
    assert "hasattr(e.action" in audit
    schemas_text = (schemas / "__init__.py").read_text(encoding="utf-8")
    assert "stringify_uuid" in schemas_text
    svc = (services / "handoff_service.py").read_text(encoding="utf-8")
    assert "hasattr(it.category" in svc
    assert relay_source_pinned_mismatch(tmp_path) is False
    assert relay_source_pinned_structure_break(tmp_path) is False
    assert apply_live_auth_autofix(tmp_path) == []


def test_patch_relay_pinned_compat_does_not_guess_when_fragment_moved(tmp_path: Path):
    app = tmp_path / "backend" / "app"
    services = app / "services"
    routers = app / "routers"
    services.mkdir(parents=True)
    routers.mkdir(parents=True)
    (routers / "handoffs.py").write_text("# relay\n", encoding="utf-8")
    (services / "receipt.py").write_text(
        'return {"handoff_id": str(other.id), "approval_state": "ok"}\n',
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        patch_relay_pinned_compat,
        relay_source_pinned_structure_break,
    )

    assert patch_relay_pinned_compat(app) == []
    assert "str(other.id)" in (services / "receipt.py").read_text(encoding="utf-8")
    assert relay_source_pinned_structure_break(tmp_path) is True


def test_ensure_atlas_client_core_layers(tmp_path: Path):
    client = tmp_path / "atlas_client.py"
    client.write_text(
        'layers = ["flood", "effis", "lightning", "volcano", "alerts", "events", "tsunami"]\n'
        'nearest = ["flood", "effis"]\n',
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import ensure_atlas_client_core_layers

    notes = ensure_atlas_client_core_layers(tmp_path)
    assert notes == ["atlas_client.py"]
    text = client.read_text(encoding="utf-8")
    assert '"weather"' in text and '"fire"' in text
    assert ensure_atlas_client_core_layers(tmp_path) == []


def test_ensure_aimarket_participant_client(tmp_path: Path):
    client = tmp_path / "atlas_client.py"
    client.write_text(
        "\n".join(
            [
                "import httpx",
                "class AtlasClient:",
                "    def __init__(self):",
                '        self.base_url = "http://localhost:8001"',
                '        self.agent_key = "demo-atlas-key"',
                "    async def _invoke(self, capability_id, input_data):",
                "        async with httpx.AsyncClient() as client:",
                "            await client.post(",
                '                f"{self.base_url}/aimarket/invoke",',
                '                json={"capability_id": capability_id, "input": input_data},',
                '                headers={"X-Agent-Key": self.agent_key},',
                "            )",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    from web.backend.services.vercel_fullstack_adapter import (
        ensure_aimarket_participant_client,
        mesh_env,
        rewrite_legacy_mesh_invoke_paths,
    )

    assert rewrite_legacy_mesh_invoke_paths(tmp_path) == ["atlas_client.py"]
    notes = ensure_aimarket_participant_client(tmp_path)
    assert notes == ["atlas_client.py"]
    text = client.read_text(encoding="utf-8")
    assert "aicom-factory-mesh-participant-runtime" in text
    assert "get_participant().invoke(" in text
    assert "/aimarket/invoke" not in text
    assert "localhost:8001" not in text
    env = mesh_env()
    assert env["AIMARKET_HUB_URL"] == "https://modelmarket.dev"
    assert "AIMARKET_SANDBOX_VISITOR" in env
