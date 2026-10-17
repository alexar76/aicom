"""Relay products: session and token salts, UUID primary-key lookups, pinned fragments, the SPA
auth shim and the public export.
"""

from __future__ import annotations

import re
from pathlib import Path


_DEMO_SEED_UUID_MARKER = "# aicom-factory-demo-uuid5"
_DEMO_SEED_UUID_SNIPPET = '''
def _aicom_demo_user_id(email: str) -> str:
    """Stable PK across serverless instances (live_ephemeral_identity gate)."""
    import uuid as _uuid
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"aicom-demo:{email.strip().lower()}"))
'''


_RELAY_SPA_AUTH_MARKER = "# aicom-factory-relay-spa-auth"
_RELAY_SPA_AUTH_SHIM = '''"""SPA auth routes injected by the AI factory publish step."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Operator, Workspace

_shim = APIRouter(tags=["auth"])


@_shim.get("/api/auth/csrf")
def spa_csrf(request: Request) -> dict[str, str]:
    """Echo the bearer token — Relay's CSRF guard compares header to bearer sid."""
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return {"csrf_token": token}


@_shim.get("/api/auth/me")
def spa_me(request: Request, db: Session = Depends(get_db)) -> dict:
    import uuid as _uuid

    from ..security import decode_session_token

    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    token = auth[7:].strip()
    payload = decode_session_token(token)
    operator_id = (payload or {}).get("operator_id") or (payload or {}).get("sub")
    if not operator_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        oid = _uuid.UUID(str(operator_id))
    except ValueError:
        oid = operator_id
    operator = db.query(Operator).filter(Operator.id == oid).first()
    if operator is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    workspace = db.get(Workspace, operator.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="workspace missing")
    role = getattr(operator, "role", "owner")
    created = getattr(operator, "created_at", None)
    ws_created = getattr(workspace, "created_at", None)
    return {
        "operator": {
            "id": str(operator.id),
            "email": operator.email,
            "role": role.value if hasattr(role, "value") else str(role),
            "workspace_id": str(operator.workspace_id),
            "created_at": created.isoformat() if created is not None else "",
        },
        "workspace": {
            "id": str(workspace.id),
            "name": workspace.name,
            "logo_url": getattr(workspace, "logo_url", None),
            "accent_color": getattr(workspace, "accent_color", "#8a1c2b"),
            "tier": (
                workspace.tier.value
                if hasattr(getattr(workspace, "tier", None), "value")
                else str(getattr(workspace, "tier", "solo"))
            ),
            "created_at": ws_created.isoformat() if ws_created is not None else "",
        },
    }


@_shim.post("/api/auth/logout")
def spa_logout() -> dict[str, bool]:
    return {"ok": True}
'''


_RELAY_ACCESS_SALT = "relay-access-token"
_RELAY_SESSION_SALT = "relay-session"
_CREATE_ACCESS_TOKEN_RE = re.compile(
    r"def _create_access_token\(operator_id\)[\s\S]*?"
    r"return serializer\.dumps\(\s*\{[\"']sub[\"']:\s*str\(operator_id\)\},\s*"
    r"salt=[\"']relay-access-token[\"']\)",
)
# Token ``sub`` / path ids are str; SQLAlchemy UUID columns need uuid.UUID.
_RELAY_UUID_PK_EQ_RE = re.compile(
    r"\b(?P<model>Operator|Handoff)\.id\s*==\s*(?P<var>operator_id|handoff_id)\b"
)
_RELAY_UUID_PK_EXPECTED = {"Operator": "operator_id", "Handoff": "handoff_id"}


def _iter_product_api_dirs(code_root: Path) -> list[Path]:
    root = Path(code_root)
    found: list[Path] = []
    seen: set[str] = set()
    for rel in ("backend/app", "app", "api", "server", "backend"):
        candidate = root / rel
        if not candidate.is_dir():
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
    return found or ([root] if root.is_dir() else [])


def relay_source_session_mismatch(code_root: Path) -> bool:
    """True when login signs a token the protected routes will not accept.

    Measured on Factory Relay (prod-e1a3b0abf16a): ``auth.py`` dumps with
    ``salt=relay-access-token`` (and ``SESSION_SECRET`` / cookie ``session``) while
    ``handoffs.py`` / ``security.py`` verify ``relay-session`` and read cookie
    ``relay_session``. The Vercel bundle used to hide this; the product tree must not.
    """
    for api_dir in _iter_product_api_dirs(code_root):
        auth_path = next((p for p in api_dir.rglob("routers/auth.py") if p.is_file()), None)
        if auth_path is None:
            continue
        try:
            auth = auth_path.read_text(encoding="utf-8")
        except OSError:
            continue
        salt_wrong = _RELAY_ACCESS_SALT in auth
        cookie_wrong = False
        deps = auth_path.parent.parent / "deps.py"
        if deps.is_file() and ('key="session"' in auth or "key='session'" in auth):
            try:
                deps_text = deps.read_text(encoding="utf-8")
            except OSError:
                deps_text = ""
            if 'SESSION_COOKIE_NAME' in deps_text and "relay_session" in deps_text:
                cookie_wrong = True
        if not salt_wrong and not cookie_wrong:
            continue
        protected = False
        for sibling in (auth_path.parent / "handoffs.py", auth_path.parent.parent / "security.py"):
            if not sibling.is_file():
                continue
            try:
                blob = sibling.read_text(encoding="utf-8")
            except OSError:
                continue
            if _RELAY_SESSION_SALT in blob:
                protected = True
                break
        if protected or cookie_wrong:
            return True
    return False


def _skip_uuid_heal_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & {"tests", "test", "__pycache__"}:
        return True
    name = path.name.lower()
    return name.startswith("test_") or name.endswith("_test.py")


def _relay_uuid_pk_coerce_repl(match: re.Match) -> str:
    model = match.group("model")
    var = match.group("var")
    if _RELAY_UUID_PK_EXPECTED.get(model) != var:
        return match.group(0)
    return f'{model}.id == __import__("uuid").UUID(str({var}))'


def relay_text_has_raw_uuid_pk_eq(text: str) -> bool:
    return bool(_RELAY_UUID_PK_EQ_RE.search(text or ""))


def relay_source_uuid_pk_mismatch(code_root: Path) -> bool:
    """True when a string token subject is compared to a UUID PK column.

    Measured on Factory Relay (prod-e1a3b0abf16a): after salt/cookie heal,
    ``verify_access_token`` succeeds then ``Operator.id == operator_id`` raises
    because JWT/itsdangerous payloads carry ``str`` and SQLAlchemy UUID columns
    (Postgres) require ``uuid.UUID``. Same class: ``Handoff.id == handoff_id``.
    """
    for api_dir in _iter_product_api_dirs(code_root):
        for path in api_dir.rglob("*.py"):
            if not path.is_file() or _skip_uuid_heal_path(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if relay_text_has_raw_uuid_pk_eq(text):
                return True
    return False


def patch_relay_uuid_pk_lookup(api_dir: Path) -> list[str]:
    """Coerce string operator/handoff ids before SQLAlchemy UUID filters.

    Idempotent. Writes into the product tree (and the Vercel copy). Cursor must
    not SSH-edit the product; the factory owns this write.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("*.py"):
        if not path.is_file() or _skip_uuid_heal_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new = _RELAY_UUID_PK_EQ_RE.sub(_relay_uuid_pk_coerce_repl, text)
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        try:
            notes.append(path.relative_to(root).as_posix())
        except ValueError:
            notes.append(path.name)
    return notes


# Exact fragments measured on Factory Relay (prod-e1a3b0abf16a). Same contract as
# AEGIS ``docker/patch-relay.py``: replace the pinned bytes or stop — never guess.
# (relpath under backend/app, old, new)
_RELAY_PINNED_FRAGMENTS: tuple[tuple[str, str, str], ...] = (
    (
        "services/handoff_service.py",
        '{"category": it.category.value, "passed": it.passed}',
        '{"category": (it.category.value if hasattr(it.category, "value") else str(it.category)), '
        '"passed": it.passed}',
    ),
    (
        "services/handoff_service.py",
        '"source": verification_source.value,',
        '"source": (verification_source.value if hasattr(verification_source, "value") '
        'else str(verification_source)),',
    ),
    (
        "services/receipt.py",
        '"category": vi.category.value',
        '"category": (vi.category.value if hasattr(vi.category, "value") else str(vi.category))',
    ),
    (
        "services/receipt.py",
        '"handoff_id": handoff.id',
        '"handoff_id": str(handoff.id)',
    ),
    (
        "services/receipt.py",
        '"approval_state": handoff.status.value',
        '"approval_state": (handoff.status.value if hasattr(handoff.status, "value") else str(handoff.status))',
    ),
    (
        "services/receipt.py",
        '"verification_source": handoff.verification_source.value',
        '"verification_source": (handoff.verification_source.value if hasattr('
        'handoff.verification_source, "value") else str(handoff.verification_source))',
    ),
    (
        "services/audit.py",
        '"id": e.id',
        '"id": str(e.id)',
    ),
    (
        "services/audit.py",
        '"action": e.action.value',
        '"action": (e.action.value if hasattr(e.action, "value") else str(e.action))',
    ),
    (
        "schemas/__init__.py",
        "from pydantic import BaseModel, Field",
        "from uuid import UUID\n\n"
        "from pydantic import BaseModel as PydanticBaseModel, Field, field_validator\n\n\n"
        "class BaseModel(PydanticBaseModel):\n"
        '    model_config = {"from_attributes": True}\n\n'
        "    @field_validator(\"*\", mode=\"before\")\n"
        "    @classmethod\n"
        "    def stringify_uuid(cls, value):\n"
        "        return str(value) if isinstance(value, UUID) else value",
    ),
)


def _resolve_pinned_path(api_dir: Path, rel: str) -> Path | None:
    direct = Path(api_dir) / rel
    if direct.is_file():
        return direct
    matches = [p for p in Path(api_dir).rglob(rel) if p.is_file()]
    if len(matches) == 1:
        return matches[0]
    return None


def _relay_looks_like_pinned_tree(api_dir: Path) -> bool:
    root = Path(api_dir)
    return bool(_resolve_pinned_path(root, "routers/handoffs.py")) and bool(
        _resolve_pinned_path(root, "services/receipt.py")
    )


def relay_source_pinned_mismatch(code_root: Path) -> bool:
    """True when a pinned Relay enum/ORM/audit fragment is still raw."""
    for api_dir in _iter_product_api_dirs(code_root):
        for rel, old, new in _RELAY_PINNED_FRAGMENTS:
            path = _resolve_pinned_path(api_dir, rel)
            if path is None:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if old in text and new not in text:
                return True
    return False


def relay_source_pinned_structure_break(code_root: Path) -> bool:
    """True when Relay-shaped files exist but a pinned fragment moved — do not guess."""
    for api_dir in _iter_product_api_dirs(code_root):
        if not _relay_looks_like_pinned_tree(api_dir):
            continue
        for rel, old, new in _RELAY_PINNED_FRAGMENTS:
            path = _resolve_pinned_path(api_dir, rel)
            if path is None:
                return True
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                return True
            if old not in text and new not in text:
                return True
    return False


def patch_relay_pinned_compat(api_dir: Path) -> list[str]:
    """Fail-fast exact replaces for Relay enum/ORM/audit 500s. Factory owns the write.

    Mirrors AEGIS ``docker/patch-relay.py``: if the bytes are not where the pin
    says, skip that fragment rather than patching a neighbour. Cursor must not
    SSH-edit the product.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    written: set[str] = set()
    for rel, old, new in _RELAY_PINNED_FRAGMENTS:
        path = _resolve_pinned_path(root, rel)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if old not in text:
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        try:
            note = path.relative_to(root).as_posix()
        except ValueError:
            note = rel
        if note not in written:
            written.add(note)
            notes.append(note)
    return notes


def patch_relay_token_salt_mismatch(api_dir: Path) -> list[str]:
    """Write the Relay login/session alignment into the product tree, not only the Vercel copy.

    Login must emit ``create_session_token`` (salt ``relay-session``, ``session_secret``).
    Cookie name must match ``SESSION_COOKIE_NAME``. Handoffs must read ``session_secret``.
    Idempotent. Cursor must not SSH-edit the product; the factory owns this write.
    """
    notes: list[str] = []
    root = Path(api_dir)
    auth_path = next((p for p in root.rglob("routers/auth.py") if p.is_file()), None)
    if auth_path is None:
        return notes
    try:
        auth = auth_path.read_text(encoding="utf-8")
    except OSError:
        return notes
    new_auth = auth
    if _RELAY_ACCESS_SALT in new_auth and "create_session_token" not in new_auth:
        rewritten = _CREATE_ACCESS_TOKEN_RE.sub(
            "def _create_access_token(operator_id) -> str:\n"
            '    """Create a signed token carrying the operator id."""\n'
            "    from ..security import create_session_token\n"
            "    return create_session_token(str(operator_id))  "
            + _RELAY_SPA_AUTH_MARKER,
            new_auth,
            count=1,
        )
        if rewritten == new_auth:
            rewritten = new_auth.replace(
                f'salt="{_RELAY_ACCESS_SALT}"',
                f'salt="{_RELAY_SESSION_SALT}"',
            ).replace(
                f"salt='{_RELAY_ACCESS_SALT}'",
                f"salt='{_RELAY_SESSION_SALT}'",
            )
            rewritten = rewritten.replace(
                'getattr(settings, "SESSION_SECRET", "dev-secret")',
                'getattr(settings, "session_secret", None) or getattr('
                'settings, "SESSION_SECRET", "dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
            )
        new_auth = rewritten
    cookie_name = ""
    deps_path = auth_path.parent.parent / "deps.py"
    if deps_path.is_file():
        try:
            deps_text = deps_path.read_text(encoding="utf-8")
        except OSError:
            deps_text = ""
        m = re.search(r'SESSION_COOKIE_NAME\s*=\s*["\']([^"\']+)["\']', deps_text)
        if m:
            cookie_name = m.group(1)
    if cookie_name and cookie_name != "session":
        if 'key="session"' in new_auth:
            new_auth = new_auth.replace('key="session"', f'key="{cookie_name}"', 1)
        elif "key='session'" in new_auth:
            new_auth = new_auth.replace("key='session'", f"key='{cookie_name}'", 1)
    if new_auth != auth:
        auth_path.write_text(new_auth, encoding="utf-8")
        notes.append(auth_path.relative_to(root).as_posix())

    handoffs_path = auth_path.parent / "handoffs.py"
    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and 'getattr(settings, "SESSION_SECRET"' in ht:
            patched = ht.replace(
                'secret = getattr(settings, "SESSION_SECRET", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")',
                'secret = getattr(settings, "session_secret", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
                1,
            )
            if patched == ht:
                patched = ht.replace(
                    'getattr(settings, "SESSION_SECRET", None)',
                    'getattr(settings, "session_secret", None) or getattr('
                    'settings, "SESSION_SECRET", None)',
                    1,
                )
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                notes.append(handoffs_path.relative_to(root).as_posix())
    return notes


def patch_relay_spa_auth_compat(api_dir: Path, public_dir: Path) -> list[str]:
    """Relay SPA login calls /api/auth/csrf after /api/auth/login; ship those routes.

    Token salt / cookie alignment is applied first via ``patch_relay_token_salt_mismatch``
    and does not require the built SPA to mention CSRF — that used to skip the source heal.
    """
    notes: list[str] = []
    root = Path(api_dir)
    notes.extend(patch_relay_token_salt_mismatch(root))
    notes.extend(patch_relay_uuid_pk_lookup(root))
    auth_path = next((p for p in root.rglob("routers/auth.py") if p.is_file()), None)
    if auth_path is None:
        return notes
    try:
        auth_text = auth_path.read_text(encoding="utf-8")
    except OSError:
        return notes
    if "/api/auth/login" not in auth_text:
        return notes
    shim_path = auth_path.parent / "_aicom_spa_auth_shim.py"
    if shim_path.is_file():
        try:
            if _RELAY_SPA_AUTH_MARKER in shim_path.read_text(encoding="utf-8"):
                # CSRF shim already shipped; salt notes (if any) still return.
                return notes
        except OSError:
            pass
    needs_csrf = False
    pub = Path(public_dir)
    if pub.is_dir():
        for js in pub.rglob("*.js"):
            try:
                if "/auth/csrf" in js.read_text(encoding="utf-8", errors="ignore"):
                    needs_csrf = True
                    break
            except OSError:
                continue
    if not needs_csrf:
        return notes

    shim_path = auth_path.parent / "_aicom_spa_auth_shim.py"
    shim_path.write_text(_RELAY_SPA_AUTH_SHIM + "\n" + _RELAY_SPA_AUTH_MARKER + "\n", encoding="utf-8")
    notes.append(shim_path.relative_to(root).as_posix())

    new_auth = auth_text
    if "relay-access-token" in new_auth and "create_session_token" not in new_auth:
        new_auth = re.sub(
            r"def _create_access_token\(operator_id\)[\s\S]*?return serializer\.dumps\("
            r'\{"sub": str\(operator_id\)\}, salt="relay-access-token"\)',
            'def _create_access_token(operator_id) -> str:\n'
            '    """Create a signed token carrying the operator id."""\n'
            "    from ..security import create_session_token\n"
            "    return create_session_token(str(operator_id))  "
            + _RELAY_SPA_AUTH_MARKER,
            new_auth,
            count=1,
        )
    if new_auth != auth_text:
        auth_path.write_text(new_auth, encoding="utf-8")
        notes.append(auth_path.relative_to(root).as_posix())

    handoffs_path = auth_path.parent / "handoffs.py"
    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and _RELAY_SPA_AUTH_MARKER not in ht:
            patched = ht.replace(
                'secret = getattr(settings, "SECRET_KEY", "insecure-dev-secret")',
                'secret = getattr(settings, "session_secret", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
                1,
            )
            if "def _aicom_operator_by_id" not in patched and "def verify_access_token" in patched:
                patched = patched.replace(
                    "def verify_access_token(token: str, db: Session) -> Optional[Operator]:",
                    "def _aicom_operator_by_id(db: Session, operator_id) -> Optional[Operator]:\n"
                    "    import uuid as _uuid\n"
                    "    try:\n"
                    "        oid = _uuid.UUID(str(operator_id))\n"
                    "    except ValueError:\n"
                    "        oid = operator_id\n"
                    "    return db.query(Operator).filter(Operator.id == oid).first()  "
                    + _RELAY_SPA_AUTH_MARKER
                    + "\n\n"
                    "def verify_access_token(token: str, db: Session) -> Optional[Operator]:",
                    1,
                )
            patched = patched.replace(
                "db.query(Operator).filter(Operator.id == operator_id).first()",
                "_aicom_operator_by_id(db, operator_id)",
            )
            if "relay-access-token" not in patched and "BadSignature:" in patched:
                patched = patched.replace(
                    "    except BadSignature:\n        pass",
                    "    except BadSignature:\n        pass\n\n"
                    "    try:\n"
                    '        s2 = URLSafeTimedSerializer(secret, salt="relay-access-token")\n'
                    "        data = s2.loads(token, max_age=7 * 24 * 3600)\n"
                    '        operator_id = data.get("operator_id") or data.get("sub")\n'
                    "        if operator_id:\n"
                    "            op = db.query(Operator).filter(Operator.id == operator_id).first()\n"
                    "            if op is not None:\n"
                    "                return op\n"
                    "    except BadSignature:\n"
                    "        pass  "
                    + _RELAY_SPA_AUTH_MARKER,
                    1,
                )
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                notes.append(handoffs_path.relative_to(root).as_posix())

    for schema_path in root.rglob("schemas/__init__.py"):
        try:
            st = schema_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "class HandoffOut" not in st or "from_attributes" in st:
            continue
        new_st = st
        if "ConfigDict" not in new_st:
            new_st = new_st.replace(
                "from pydantic import BaseModel",
                "from pydantic import BaseModel, ConfigDict",
                1,
            )
        new_st = new_st.replace(
            "class HandoffOut(BaseModel):",
            "class HandoffOut(BaseModel):\n"
            "    model_config = ConfigDict(from_attributes=True)  "
            + _RELAY_SPA_AUTH_MARKER,
            1,
        )
        if new_st != st:
            schema_path.write_text(new_st, encoding="utf-8")
            notes.append(schema_path.relative_to(root).as_posix())

    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and "def _aicom_handoff_out" not in ht and "HandoffOut.model_validate(h)" in ht:
            helper = (
                "\n\n"
                "def _aicom_handoff_out(h: Handoff) -> HandoffOut:\n"
                '    """ORM → schema with UUID/enum coercion (Vercel serverless)."""\n'
                "    return HandoffOut(\n"
                "        id=str(h.id),\n"
                "        workspace_id=str(h.workspace_id),\n"
                "        client_name=h.client_name,\n"
                "        project_name=h.project_name,\n"
                "        source_ai_tool=h.source_ai_tool,\n"
                "        draft_text=h.draft_text,\n"
                "        approved_text=h.approved_text,\n"
                "        status=h.status.value if hasattr(h.status, 'value') else str(h.status),\n"
                "        share_token=h.share_token,\n"
                "        content_sha256=h.content_sha256,\n"
                "        verification_source=(\n"
                "            h.verification_source.value\n"
                "            if hasattr(h.verification_source, 'value')\n"
                "            else str(h.verification_source)\n"
                "        ),\n"
                "        created_by=str(h.created_by),\n"
                "        approved_by=str(h.approved_by) if h.approved_by else None,\n"
                "        approved_at=h.approved_at,\n"
                "        rejected_reason=h.rejected_reason,\n"
                "        created_at=h.created_at,\n"
                "    )  "
                + _RELAY_SPA_AUTH_MARKER
                + "\n"
            )
            anchor = "router = APIRouter(tags=[\"handoffs\"])"
            if anchor in ht:
                ht = ht.replace(anchor, helper + anchor, 1)
            ht = ht.replace(
                "HandoffOut.model_validate(h)",
                "_aicom_handoff_out(h)",
            )
            ht = ht.replace(
                "HandoffOut.model_validate(handoff)",
                "_aicom_handoff_out(handoff)",
            )
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)

    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        counts_old = "        counts[s.value] = c"
        counts_new = (
            "        _sk = s.value if hasattr(s, \"value\") else str(s)\n"
            "        if _sk in counts:\n"
            "            counts[_sk] = c  "
            + _RELAY_SPA_AUTH_MARKER
        )
        if ht and counts_old in ht and counts_new not in ht:
            ht = ht.replace(counts_old, counts_new, 1)
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)

    main_path = auth_path.parent.parent / "main.py"
    if main_path.is_file():
        try:
            mt = main_path.read_text(encoding="utf-8")
        except OSError:
            mt = ""
        if mt and _RELAY_SPA_AUTH_MARKER not in mt:
            if "_aicom_spa_auth_shim" not in mt:
                mt = re.sub(
                    r"from \.routers import (?P<rest>[^\n]+)",
                    lambda m: (
                        "from .routers import _aicom_spa_auth_shim, "
                        + m.group("rest").lstrip()
                        + "  "
                        + _RELAY_SPA_AUTH_MARKER
                    ),
                    mt,
                    count=1,
                )
            if "_aicom_spa_auth_shim._shim" not in mt:
                anchor = "app.include_router(auth.router"
                if anchor in mt:
                    mt = mt.replace(
                        anchor,
                        "app.include_router(_aicom_spa_auth_shim._shim)  "
                        + _RELAY_SPA_AUTH_MARKER
                        + "\n    "
                        + anchor,
                        1,
                    )
            if _RELAY_SPA_AUTH_MARKER in mt:
                main_path.write_text(mt, encoding="utf-8")
                notes.append(main_path.relative_to(root).as_posix())

    # CSRF fallback may re-insert ``Operator.id == operator_id``; coerce last.
    for rel in patch_relay_uuid_pk_lookup(root):
        if rel not in notes:
            notes.append(rel)
    return notes


_RELAY_PUBLIC_EXPORT_MARKER = "# aicom-factory-relay-public-export"


def patch_relay_public_export_compat(api_dir: Path) -> list[str]:
    """Fix Relay public share, receipt JSON, and embed-snippet on Vercel serverless.

    Measured on prod-e1a3b0abf16a: ``PublicReadOut = PublicHandoffOut`` alias breaks the
    nested public router response (500); ``build_receipt`` emits non-JSON-serializable UUIDs
    (500 on receipt.json); enum/UUID coercion gaps break list/detail paths without
    ``_aicom_handoff_out``.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes

    for schema_path in root.rglob("schemas/__init__.py"):
        try:
            st = schema_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_st = st
        # PublicWorkspaceOut is assigned after this class in Relay; using it here
        # NameError's the whole serverless import (FUNCTION_INVOCATION_FAILED).
        if "class PublicReadOut(BaseModel):" in new_st:
            new_st = new_st.replace(
                "    workspace: PublicWorkspaceOut\n",
                "    workspace: WorkspaceOut\n",
            )
        if _RELAY_PUBLIC_EXPORT_MARKER in new_st:
            if new_st != st:
                schema_path.write_text(new_st, encoding="utf-8")
                notes.append(schema_path.relative_to(root).as_posix())
            continue
        if "class HandoffOut" not in new_st:
            if new_st != st:
                schema_path.write_text(new_st, encoding="utf-8")
                notes.append(schema_path.relative_to(root).as_posix())
            continue
        alias_block = "PublicReadOut = PublicHandoffOut"
        if alias_block in new_st and "class PublicReadOut(BaseModel):" not in new_st:
            nested = (
                "\n\n"
                "class PublicHandoffShareOut(BaseModel):\n"
                '    """Approved handoff slice for the public share page."""\n'
                "    id: str\n"
                "    client_name: str\n"
                "    project_name: str\n"
                "    source_ai_tool: str\n"
                "    approved_text: str\n"
                "    approved_at: Optional[datetime] = None\n"
                "    content_sha256: str\n\n\n"
                "class PublicReadOut(BaseModel):\n"
                "    handoff: PublicHandoffShareOut\n"
                "    workspace: WorkspaceOut\n"
                "    verification_source: str  "
                + _RELAY_PUBLIC_EXPORT_MARKER
                + "\n"
            )
            new_st = new_st.replace(alias_block, nested, 1)
        if "stringify_uuid" in new_st or "class BaseModel(PydanticBaseModel)" in new_st:
            # Pinned ORM wrap already stringifies UUIDs; do not rewrite the import.
            pass
        elif "model_config = ConfigDict(from_attributes=True)" not in new_st and "class HandoffOut" in new_st:
            if "ConfigDict" not in new_st:
                new_st = new_st.replace(
                    "from pydantic import BaseModel",
                    "from pydantic import BaseModel, ConfigDict",
                    1,
                )
            if "class HandoffOut(BaseModel):" in new_st and "from_attributes=True" not in new_st:
                new_st = new_st.replace(
                    "class HandoffOut(BaseModel):",
                    "class HandoffOut(BaseModel):\n"
                    "    model_config = ConfigDict(from_attributes=True)  "
                    + _RELAY_PUBLIC_EXPORT_MARKER,
                    1,
                )
        if new_st != st:
            schema_path.write_text(new_st, encoding="utf-8")
            notes.append(schema_path.relative_to(root).as_posix())

    public_path = next((p for p in root.rglob("routers/public.py") if p.is_file()), None)
    if public_path is not None:
        try:
            pt = public_path.read_text(encoding="utf-8")
        except OSError:
            pt = ""
        if pt and _RELAY_PUBLIC_EXPORT_MARKER not in pt and "PublicHandoffShareOut" not in pt:
            new_pt = pt.replace(
                "from ..schemas import PublicHandoffOut, PublicReadOut, PublicWorkspaceOut",
                "from ..schemas import PublicHandoffShareOut, PublicReadOut, PublicWorkspaceOut  "
                + _RELAY_PUBLIC_EXPORT_MARKER,
                1,
            )
            new_pt = new_pt.replace(
                "handoff=PublicHandoffOut(",
                "handoff=PublicHandoffShareOut(",
            )
            new_pt = new_pt.replace("id=h.id,", "id=str(h.id),  " + _RELAY_PUBLIC_EXPORT_MARKER, 1)
            new_pt = new_pt.replace(
                "tier=workspace.tier.value,",
                "tier=(workspace.tier.value if hasattr(workspace.tier, 'value') else str(workspace.tier)),  "
                + _RELAY_PUBLIC_EXPORT_MARKER,
                1,
            )
            if new_pt != pt:
                public_path.write_text(new_pt, encoding="utf-8")
                notes.append(public_path.relative_to(root).as_posix())

    for receipt_path in root.rglob("services/receipt.py"):
        try:
            rt = receipt_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _RELAY_PUBLIC_EXPORT_MARKER in rt or '"handoff_id": handoff.id' not in rt:
            continue
        new_rt = rt.replace(
            '"handoff_id": handoff.id,',
            '"handoff_id": str(handoff.id),  ' + _RELAY_PUBLIC_EXPORT_MARKER,
            1,
        )
        if new_rt != rt:
            receipt_path.write_text(new_rt, encoding="utf-8")
            notes.append(receipt_path.relative_to(root).as_posix())

    handoffs_path = next((p for p in root.rglob("routers/handoffs.py") if p.is_file()), None)
    if handoffs_path is not None:
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and "def _aicom_handoff_out" not in ht and "HandoffOut.model_validate" in ht:
            helper = (
                "\n\n"
                "def _aicom_handoff_out(h: Handoff) -> HandoffOut:\n"
                '    """ORM → schema with UUID/enum coercion (Vercel serverless)."""\n'
                "    return HandoffOut(\n"
                "        id=str(h.id),\n"
                "        workspace_id=str(h.workspace_id),\n"
                "        client_name=h.client_name,\n"
                "        project_name=h.project_name,\n"
                "        source_ai_tool=h.source_ai_tool,\n"
                "        draft_text=h.draft_text,\n"
                "        approved_text=h.approved_text,\n"
                "        status=h.status.value if hasattr(h.status, 'value') else str(h.status),\n"
                "        share_token=h.share_token,\n"
                "        content_sha256=h.content_sha256,\n"
                "        verification_source=(\n"
                "            h.verification_source.value\n"
                "            if hasattr(h.verification_source, 'value')\n"
                "            else str(h.verification_source)\n"
                "        ),\n"
                "        created_by=str(h.created_by),\n"
                "        approved_by=str(h.approved_by) if h.approved_by else None,\n"
                "        approved_at=h.approved_at,\n"
                "        rejected_reason=h.rejected_reason,\n"
                "        created_at=h.created_at,\n"
                "    )  "
                + _RELAY_PUBLIC_EXPORT_MARKER
                + "\n"
            )
            anchor = "router = APIRouter(tags=[\"handoffs\"])"
            if anchor in ht:
                ht = ht.replace(anchor, helper + anchor, 1)
            ht = ht.replace("HandoffOut.model_validate(handoff)", "_aicom_handoff_out(handoff)")
            ht = ht.replace("HandoffOut.model_validate(h)", "_aicom_handoff_out(h)")
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)
        elif ht and "HandoffOut.model_validate" in ht and _RELAY_PUBLIC_EXPORT_MARKER not in ht:
            patched = ht.replace("HandoffOut.model_validate(handoff)", "_aicom_handoff_out(handoff)")
            patched = patched.replace("HandoffOut.model_validate(h)", "_aicom_handoff_out(h)")
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                rel = handoffs_path.relative_to(root).as_posix()
                if rel not in notes:
                    notes.append(rel)

    return notes
