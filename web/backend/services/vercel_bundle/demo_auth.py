"""Demo login that works on a live deploy: a deterministic demo user, a login that uses the
seed helper, a stable current-user identity, and login pages prefilled with the live
password.
"""

from __future__ import annotations

import re
from pathlib import Path

from .discovery import find_frontend_dist
from .env import _JWT_DEPS_MARKER
from .relay import (
    _DEMO_SEED_UUID_MARKER,
    _DEMO_SEED_UUID_SNIPPET,
    _iter_product_api_dirs,
    patch_relay_pinned_compat,
    patch_relay_public_export_compat,
    patch_relay_token_salt_mismatch,
    patch_relay_uuid_pk_lookup,
)
from .requirements import pin_bcrypt_in_requirement_files


def patch_deterministic_demo_user_seed(api_dir: Path) -> list[str]:
    """Make demo user primary keys deterministic from email (uuid5).

    Without this, each Vercel instance seeds ``uuid4()`` for the same demo email,
    so a Bearer token from instance A fails on instance B (``User not found``).
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    seed_names = {"seed.py", "demo_seed.py", "seeding.py"}
    for path in root.rglob("*.py"):
        if path.name not in seed_names and "seed" not in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "seed_demo_user" not in text or "User(" not in text:
            continue
        if _DEMO_SEED_UUID_MARKER in text:
            continue
        if "User(" not in text:
            continue
        new = text
        if "_aicom_demo_user_id" not in new:
            # Insert helper before first seed_demo_user def.
            new = new.replace(
                "def seed_demo_user",
                _DEMO_SEED_UUID_SNIPPET + "\n" + _DEMO_SEED_UUID_MARKER + "\ndef seed_demo_user",
                1,
            )
        # Prefer explicit id= on User(...) construction.
        if re.search(r"User\s*\(\s*\n?\s*email\s*=", new) and "id=_aicom_demo_user_id" not in new:
            new = re.sub(
                r"User\s*\(\s*",
                "User(\n            id=_aicom_demo_user_id(email),\n            ",
                new,
                count=1,
            )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_AUTH_LOGIN_SEED_MARKER = "# aicom-factory-auth-seed-helper"
_AUTH_LOGIN_DEF_RE = re.compile(r"\b(?:async )?def login\s*\(")
_AUTH_ONE_SHOT_SEED_RE = re.compile(
    r"[ \t]*global _demo_seeded\n"
    r"(?:[ \t]*#.*\n)*"
    r"[ \t]*if not _demo_seeded:[\s\S]*?"
    r"[ \t]*_demo_seeded = True\n",
)
_ORPHAN_SEED_IMPORT_RE = re.compile(
    r"^(?:from \.\.services\.seeding import seed_demo_user|"
    r"from app\.services\.seeding import seed_demo_user)\n",
    re.M,
)


def _seeding_py_exists(api_dir: Path) -> bool:
    return any(p.is_file() and p.name == "seeding.py" for p in Path(api_dir).rglob("seeding.py"))


def patch_drop_orphan_seed_demo_import(api_dir: Path) -> list[str]:
    """Relay-style apps have login_root/login_api, not Sentinel's seed helper.

    ``def login`` used to match ``def login_root``, so auth_seed imported
    ``seed_demo_user`` from a module that does not exist — ImportError on every
    request. Strip the dangling import when seeding.py is absent and unused.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir() or _seeding_py_exists(root):
        return notes
    for path in root.rglob("auth.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "seed_demo_user(db)" in text:
            continue
        new = _ORPHAN_SEED_IMPORT_RE.sub("", text)
        if new.startswith(_AUTH_LOGIN_SEED_MARKER + "\n") and "seed_demo_user" not in new:
            new = new[len(_AUTH_LOGIN_SEED_MARKER) + 1 :]
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        try:
            notes.append(path.relative_to(root).as_posix())
        except ValueError:
            notes.append(path.name)
    return notes


def patch_auth_login_to_use_seed_helper(api_dir: Path) -> list[str]:
    """Login must upsert the demo operator on every request, not once per process.

    Sentinel's ``auth.py`` seeded only if the email was missing, then set
    ``_demo_seeded = True`` even after a failed hash. On Vercel that is a
    permanent 401: /tmp SQLite is empty on a new instance, or an old row keeps a
    stale password. ``seeding.seed_demo_user`` already upserts; login must call it.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("auth.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _AUTH_LOGIN_DEF_RE.search(text):
            continue
        new = text
        already = _AUTH_LOGIN_SEED_MARKER in new and "seed_demo_user(db)" in new
        needs_sub = '"sub": str(user.id)' in new or "'sub': str(user.id)" in new
        if already and not needs_sub:
            continue
        if "seed_demo_user" not in new:
            if "from ..db import get_db" in new:
                new = new.replace(
                    "from ..db import get_db",
                    "from ..db import get_db\nfrom ..services.seeding import seed_demo_user",
                    1,
                )
            elif "from app.db import" in new:
                new = "from app.services.seeding import seed_demo_user\n" + new
            else:
                new = "from app.services.seeding import seed_demo_user\n" + new
        if _AUTH_ONE_SHOT_SEED_RE.search(new):
            new = _AUTH_ONE_SHOT_SEED_RE.sub("    seed_demo_user(db)\n", new, count=1)
        elif "seed_demo_user(db)" not in new:
            new = re.sub(
                r"(async def login\s*\([^)]*\)\s*:\s*\n)",
                r"\1    seed_demo_user(db)\n",
                new,
                count=1,
            )
        new = new.replace("_demo_seeded = False\n", "")
        new = new.replace("_demo_seeded = False", "")
        # deps.py treats JWT ``sub`` as an email; a random uuid there is
        # live_ephemeral_identity + 401 User not found on every other instance.
        new = new.replace('"sub": str(user.id)', '"sub": user.email')
        new = new.replace("'sub': str(user.id)", "'sub': user.email")
        if _AUTH_LOGIN_SEED_MARKER not in new:
            new = _AUTH_LOGIN_SEED_MARKER + "\n" + new
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def patch_get_current_user_stable_identity(api_dir: Path) -> list[str]:
    """Resolve JWT ``sub`` as email or id, and re-seed the demo user on the instance."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("deps.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "def get_current_user" not in text:
            continue
        if _JWT_DEPS_MARKER in text:
            continue
        new = text
        if "seed_demo_user" not in new:
            if "from app.db import get_db" in new:
                new = new.replace(
                    "from app.db import get_db",
                    "from app.db import get_db\nfrom app.services.seeding import seed_demo_user",
                    1,
                )
            elif "from ..db import get_db" in new:
                new = new.replace(
                    "from ..db import get_db",
                    "from ..db import get_db\nfrom ..services.seeding import seed_demo_user",
                    1,
                )
            else:
                new = "from app.services.seeding import seed_demo_user\n" + new
        new = new.replace(
            'email: str = payload.get("sub")',
            'email = payload.get("email") or payload.get("sub")',
        )
        new = new.replace(
            'email = payload.get("sub")',
            'email = payload.get("email") or payload.get("sub")',
        )
        if "seed_demo_user(db)" not in new and "user = db.query(User)" in new:
            new = new.replace(
                "user = db.query(User)",
                "seed_demo_user(db)\n    user = db.query(User)",
                1,
            )
        new = re.sub(
            r"user = db\.query\(User\)\.filter\(User\.email == email\)\.first\(\)",
            "user = db.query(User).filter(User.email == email).first()\n"
            "    if user is None:\n"
            "        user = db.query(User).filter(User.id == str(email)).first()",
            new,
            count=1,
        )
        if _JWT_DEPS_MARKER not in new:
            new = _JWT_DEPS_MARKER + "\n" + new
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def apply_live_auth_autofix(code_root: Path) -> list[str]:
    """Patch the product tree for known live-auth defects (401 salt, UUID PK 500,
    enum/ORM/audit serialization).

    The Vercel bundle already applies these to a copy. The factory must also write
    them into ``data/code/<id>`` so the next publish (and GitHub) is the factory's
    fix — not a Cursor SSH into the product, and not an AEGIS Docker sed on a pin.
    """
    root = Path(code_root)
    if not root.is_dir():
        return []
    actions: list[str] = []
    for api_dir in _iter_product_api_dirs(root):
        for label, fn in (
            ("auth_seed", patch_auth_login_to_use_seed_helper),
            ("orphan_seed_import", patch_drop_orphan_seed_demo_import),
            ("jwt_identity", patch_get_current_user_stable_identity),
            ("demo_uuid", patch_deterministic_demo_user_seed),
            ("relay_token_salt", patch_relay_token_salt_mismatch),
            ("relay_uuid_pk", patch_relay_uuid_pk_lookup),
            ("relay_pinned", patch_relay_pinned_compat),
            ("relay_public_export", patch_relay_public_export_compat),
        ):
            for rel in fn(api_dir):
                actions.append(f"{label}:{rel}")
    for rel in pin_bcrypt_in_requirement_files(root):
        actions.append(f"bcrypt_pin:{rel}")
    return actions


def patch_widget_demo_defaults(public_dir: Path) -> list[str]:
    """Keep Berlin as the demo city, but the API bbox (above) must be wide enough to hit LIVE pins."""
    # No city swap — Berlin works once atlas_client uses ±5°. Hook retained for future JS fixes.
    return []


# Passwords products bake into Vite bundles while the API seeds from factory env — UI login 401.
_STALE_DEMO_PASSWORD_MARKERS = (
    "SentinelDemo123!",
    "SandboxDemo!2026",
)


def _frontend_demo_auth_stale(code_dir: Path, demo: dict[str, str]) -> bool:
    """True when the built SPA does not carry the same demo password the API will seed."""
    dist = find_frontend_dist(code_dir)
    if dist is None:
        return True
    password = (demo.get("VITE_SANDBOX_DEMO_PASSWORD") or demo.get("SANDBOX_DEMO_PASSWORD") or "").strip()
    if not password:
        return False
    blob_parts: list[str] = []
    for path in list(dist.rglob("*.js"))[:24] + list(dist.rglob("*.mjs"))[:8]:
        try:
            blob_parts.append(path.read_text(encoding="utf-8", errors="replace")[:80_000])
        except OSError:
            continue
    blob = "".join(blob_parts)
    if password in blob:
        return False
    return any(marker in blob for marker in _STALE_DEMO_PASSWORD_MARKERS)


def patch_operator_login_prefill(
    public_dir: Path,
    *,
    demo_email: str,
    demo_password: str = "",
) -> list[str]:
    """Replace reserved demo auth baked into frontend bundles.

    EmailStr rejects ``.local`` (422). Operator Login must prefill the same
    ``SANDBOX_DEMO_*`` the API seeds — typically ``sandbox.demo@magic-ai-factory.com`` plus the
    factory ``AIFACTORY_SANDBOX_DEMO_PASSWORD``. Vite bakes ``VITE_SANDBOX_DEMO_PASSWORD`` at build
    time; when that diverges from ``vercel.json`` runtime env the UI gets permanent 401.
    """
    notes: list[str] = []
    root = Path(public_dir)
    if not root.is_dir():
        return notes
    email = (demo_email or "").strip()
    password = (demo_password or "").strip()
    if not email and not password:
        return notes
    email_needles = (
        "operator@sentinel.local",
        "admin@localhost",
        "demo@localhost",
        "operator@localhost",
    )
    password_needles = list(_STALE_DEMO_PASSWORD_MARKERS)
    from web.backend.services.demo_credentials import DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD

    password_needles.append(DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD)
    for path in list(root.rglob("*.js")) + list(root.rglob("*.html")) + list(root.rglob("*.mjs")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        new = text
        if email:
            for needle in email_needles:
                if needle in new:
                    new = new.replace(needle, email)
        if password:
            for needle in password_needles:
                if needle and needle != password and needle in new:
                    new = new.replace(needle, password)
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and re.search(r"get_participant\(\)\._invoke\s*\(", new)
        ):
            new = re.sub(
                r"return\s+await\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            new = re.sub(
                r"return\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            if "aicom-factory-mesh-participant-runtime" not in new:
                new = new.replace(
                    "async def _invoke",
                    "# aicom-factory-mesh-participant-runtime\n    async def _invoke",
                    1,
                )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes
