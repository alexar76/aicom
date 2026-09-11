"""Why a repair loop stalls: symbols nothing defines, and modules that keep multiplying."""

from pathlib import Path

from web.backend.services.duplicate_module_check import (
    find_duplicate_roles,
    find_missing_symbols,
    run_duplicate_module_check,
)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_missing_symbol_is_reported_with_its_importers(tmp_path):
    """The exact production failure: five modules import a hasher nobody wrote."""
    root = tmp_path / "code" / "prod-x"
    _write(root, "backend/app/core/security.py", "from passlib.context import CryptContext\n")
    for rel in ("backend/app/seed.py", "backend/app/services/seed.py", "backend/app/services/demo.py"):
        _write(root, rel, "from app.core.security import get_password_hash\n")

    missing = find_missing_symbols(root)
    hit = next(m for m in missing if m["symbol"] == "get_password_hash")
    assert hit["file"] == "backend/app/core/security.py"
    assert len(hit["importers"]) == 3

    report = run_duplicate_module_check.__wrapped__ if hasattr(run_duplicate_module_check, "__wrapped__") else None
    assert report is None  # plain function, no decorator surprises


def test_defined_symbols_are_not_reported(tmp_path):
    root = tmp_path / "code" / "prod-y"
    _write(
        root,
        "backend/app/core/security.py",
        "def get_password_hash(p):\n    return p\n\nclass Hasher:\n    pass\n\nsettings = 1\n",
    )
    _write(
        root,
        "backend/app/seed.py",
        "from app.core.security import get_password_hash, Hasher, settings\n",
    )
    assert find_missing_symbols(root) == []


def test_reexports_count_as_definitions(tmp_path):
    root = tmp_path / "code" / "prod-z"
    _write(root, "backend/app/core/hashing.py", "def hash_it(x):\n    return x\n")
    _write(root, "backend/app/core/security.py", "from app.core.hashing import hash_it\n")
    _write(root, "backend/app/seed.py", "from app.core.security import hash_it\n")
    assert find_missing_symbols(root) == []


def test_star_import_module_is_not_accused(tmp_path):
    """A module that re-exports with * cannot be judged statically."""
    root = tmp_path / "code" / "prod-s"
    _write(root, "backend/app/core/security.py", "from app.core.impl import *\n")
    _write(root, "backend/app/seed.py", "from app.core.security import anything\n")
    assert find_missing_symbols(root) == []


def test_getattr_module_is_not_accused(tmp_path):
    root = tmp_path / "code" / "prod-g"
    _write(root, "backend/app/core/security.py", "def __getattr__(name):\n    return None\n")
    _write(root, "backend/app/seed.py", "from app.core.security import whatever\n")
    assert find_missing_symbols(root) == []


def test_third_party_imports_are_ignored(tmp_path):
    root = tmp_path / "code" / "prod-t"
    _write(root, "backend/app/seed.py", "from sqlalchemy.orm import Session\nfrom fastapi import FastAPI\n")
    assert find_missing_symbols(root) == []


def test_duplicate_roles_are_grouped(tmp_path):
    root = tmp_path / "code" / "prod-d"
    for rel in (
        "backend/app/seed.py",
        "backend/app/services/demo_seed.py",
        "backend/app/services/demo_data.py",
    ):
        _write(root, rel, "x = 1\n")
    _write(root, "frontend/src/pages/Accounts.tsx", "export default function A(){}\n")
    _write(root, "frontend/src/pages/AccountsPage.tsx", "export default function A(){}\n")

    roles = {r["role"]: r["files"] for r in find_duplicate_roles(root)}
    assert len(roles["demo seeding"]) == 3
    assert len(roles["Accounts screen"]) == 2


def test_gate_fails_on_missing_symbol_but_not_on_duplicates_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-gate"
    _write(root, "backend/app/seed.py", "x = 1\n")
    _write(root, "backend/app/services/demo_seed.py", "y = 2\n")
    report = run_duplicate_module_check("prod-gate")
    assert report["passed"] is True
    assert {i["code"] for i in report["issues"]} == {"duplicate_modules"}

    _write(root, "backend/app/core/security.py", "import os\n")
    _write(root, "backend/app/uses.py", "from app.core.security import hash_password\n")
    report = run_duplicate_module_check("prod-gate")
    assert report["passed"] is False
    assert "missing_symbol" in {i["code"] for i in report["issues"]}


def test_no_code_dir_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    report = run_duplicate_module_check("prod-absent")
    assert report["skipped"] is True
    assert report["passed"] is True


def test_orphan_module_with_dangling_imports_is_named_for_deletion(tmp_path):
    """The leftover from an earlier round breaks the package for everything else."""
    from web.backend.services.duplicate_module_check import (
        find_orphan_modules_with_broken_imports,
    )

    root = tmp_path / "code" / "prod-o"
    _write(root, "backend/app/schemas/common.py", "class Kept:\n    pass\n")
    # Superseded endpoint nobody imports any more, still importing a removed name.
    _write(root, "backend/app/api/endpoints/datasets.py", "from app.schemas.common import Gone\n")
    # Its replacement under v1 — same stem — is the one actually wired up.
    _write(
        root,
        "backend/app/api/v1/endpoints/datasets.py",
        "from app.schemas.common import Kept\n",
    )
    _write(root, "backend/app/api/v1/router.py", "from app.api.v1.endpoints.datasets import *\n")

    missing = find_missing_symbols(root)
    orphans = find_orphan_modules_with_broken_imports(root, missing)
    assert [o["file"] for o in orphans] == ["backend/app/api/endpoints/datasets.py"]
    assert orphans[0]["superseded_by"] == ["backend/app/api/v1/endpoints/datasets.py"]


def test_tests_are_never_called_orphans(tmp_path):
    """pytest collects tests; "nothing imports it" is normal and not a defect."""
    from web.backend.services.duplicate_module_check import (
        find_orphan_modules_with_broken_imports,
    )

    root = tmp_path / "code" / "prod-tests"
    _write(root, "backend/app/db.py", "engine = 1\n")
    _write(root, "backend/tests/integration/test_api.py", "from app.db import get_db\n")

    missing = find_missing_symbols(root)
    assert missing, "the dangling import should still be reported as a missing symbol"
    assert find_orphan_modules_with_broken_imports(root, missing) == []


def test_entrypoints_are_never_orphans(tmp_path):
    from web.backend.services.duplicate_module_check import (
        find_orphan_modules_with_broken_imports,
    )

    root = tmp_path / "code" / "prod-entry"
    _write(root, "backend/app/db.py", "engine = 1\n")
    _write(root, "backend/app/main.py", "from app.db import get_db\n")

    missing = find_missing_symbols(root)
    assert find_orphan_modules_with_broken_imports(root, missing) == []


def test_symbols_wanted_only_by_orphans_are_not_also_reported(tmp_path, monkeypatch):
    """5 deletions must not read as 30 "write this schema" instructions."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-both"
    _write(root, "backend/app/schemas/common.py", "class Kept:\n    pass\n")
    _write(
        root,
        "backend/app/api/endpoints/old.py",
        "from app.schemas.common import DatasetCreate, DatasetOut, MetricOut\n",
    )
    # The module that superseded it — an orphan is only safe to name when a twin exists.
    _write(root, "backend/app/api/v1/endpoints/old.py", "from app.schemas.common import Kept\n")
    _write(root, "backend/app/api/v1/router.py", "from app.schemas.common import Kept\n")

    report = run_duplicate_module_check("prod-both")
    codes = [i["code"] for i in report["issues"]]
    assert codes[0] == "orphan_module_breaks_build", "deletion must come first"
    assert "missing_symbol" not in codes, "those symbols die with the file"


def test_symbols_wanted_by_a_live_module_survive_the_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-live"
    _write(root, "backend/app/schemas/common.py", "class Kept:\n    pass\n")
    # `old.py` has a twin under v1, so it is an orphan; `live.py` is wired up.
    _write(root, "backend/app/api/endpoints/old.py", "from app.schemas.common import Wanted\n")
    _write(root, "backend/app/api/v1/endpoints/old.py", "from app.schemas.common import Kept\n")
    _write(root, "backend/app/services/live.py", "from app.schemas.common import Wanted\n")
    _write(root, "backend/app/main.py", "from app.services.live import *\n")

    report = run_duplicate_module_check("prod-live")
    codes = {i["code"] for i in report["issues"]}
    assert "missing_symbol" in codes, "a live module still needs the symbol defined"


def test_a_lone_unimported_file_is_not_called_an_orphan(tmp_path):
    """New code being built toward has no twin — "delete it" would be wrong advice."""
    from web.backend.services.duplicate_module_check import (
        find_orphan_modules_with_broken_imports,
    )

    root = tmp_path / "code" / "prod-lone"
    _write(root, "backend/app/core/security.py", "import os\n")
    _write(root, "backend/app/uses.py", "from app.core.security import hash_password\n")

    missing = find_missing_symbols(root)
    assert missing, "still reported as a missing symbol"
    assert find_orphan_modules_with_broken_imports(root, missing) == []


def test_package_import_of_a_router_is_not_an_orphan(tmp_path, monkeypatch):
    """Sentinel: main.py does `from .routers import auth`; the gate said DELETE auth.py."""
    from web.backend.services.duplicate_module_check import (
        find_duplicate_roles,
        find_orphan_modules_with_broken_imports,
    )

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-sentinel-auth"
    _write(
        root,
        "backend/app/main.py",
        "from .routers import auth\napp = 1\napp_router = auth.router\n",
    )
    _write(
        root,
        "backend/app/routers/auth.py",
        "from ..utils.security import get_password_hash\nrouter = 1\n",
    )
    _write(
        root,
        "backend/app/utils/security.py",
        "def hash_password(p):\n    return p\n",
    )
    _write(root, "backend/app/schemas/auth.py", "class LoginRequest:\n    pass\n")
    _write(
        root,
        "frontend/src/api/auth.ts",
        "export async function login() { return fetch('/api/auth/login') }\n",
    )

    missing = find_missing_symbols(root)
    orphans = find_orphan_modules_with_broken_imports(root, missing)
    assert orphans == [], orphans
    roles = find_duplicate_roles(root)
    assert not any(r["role"] == "auth hook" for r in roles), roles
    report = run_duplicate_module_check("prod-sentinel-auth")
    codes = {i["code"] for i in report["issues"]}
    assert "orphan_module_breaks_build" not in codes, report["issues"]
    assert "missing_symbol" in codes
    miss = next(i for i in report["issues"] if i["code"] == "missing_symbol")
    assert miss["symbol"] == "get_password_hash"
    assert "hash_password" in str(miss.get("detail") or "")
