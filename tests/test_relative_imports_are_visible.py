"""The cheapest gate was blind to the import style the factory actually writes.

``find_missing_symbols`` builds a table of what each module defines, keyed by absolute dotted
path, then walks every import and reports names the target module never defines. ``from_imports``
reports an import the way the source spells it — dots included — so ``from .advisory import X``
arrived as ``.advisory``, matched nothing in the table, and was dropped by the same ``continue``
that correctly skips third-party packages. Silently, and for every relative import in the tree.

Measured on the live product: a tree that could not boot at all —

    backend/app/models/__init__.py:  from .advisory import Advisory, CachedMeshReading, WatchLocation
    backend/app/routers/advisory.py: from ..services.cache import MeshCache

with neither name defined anywhere — returned **zero** findings. Eighteen repair rounds never saw
the names that stopped the app from starting; the only gate that noticed was the demo journey, and
only as a uvicorn boot log ("ImportError: cannot import name 'MeshCache'") that names no file to
fix. After the fix the same tree yields six, each with the file, the importers and a near-match
suggestion — including ``seed_demo_user``, which is why the seeded demo login had been answering
422 for the whole run.

The second half was the same defect one level up: ``app/models/__init__.py`` is keyed as
``app.models.__init__``, so ``from app.models import Advisory`` — an absolute import naming the
package — missed the lookup too.

This gate votes on whether a round's work is kept, so a false critical costs more than a miss.
Hence the submodule tests below: ``from . import advisory`` imports a module, not a symbol.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import (
    find_missing_symbols,
    resolve_import_target,
)


@pytest.mark.parametrize(
    "written,importer,expected",
    [
        (".advisory", "app.models.__init__", "app.models.advisory"),
        ("..services.cache", "app.routers.advisory", "app.services.cache"),
        ("...core.db", "app.api.v1.routes", "app.core.db"),
        (".", "app.models.__init__", "app.models"),
        ("app.models.audit", "app.main", "app.models.audit"),
        ("fastapi", "app.main", "fastapi"),
    ],
)
def test_a_relative_import_resolves_to_where_it_points(written, importer, expected):
    assert resolve_import_target(written, importer) == expected


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_live_boot_blocker_is_now_reported(tmp_path):
    """Reduced from the tree the factory had been repairing for eighteen rounds."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/__init__.py": (
                "from .advisory import Advisory, CachedMeshReading, WatchLocation\n"
            ),
            "backend/app/models/advisory.py": "class Advisory:\n    pass\n",
            "backend/app/routers/advisory.py": "from ..services.cache import MeshCache\n",
            "backend/app/services/cache.py": "class ReadingCache:\n    pass\n",
        },
    )
    found = {f"{i['module']}.{i['symbol']}" for i in find_missing_symbols(code, limit=40)}
    assert "app.models.advisory.CachedMeshReading" in found, found
    assert "app.models.advisory.WatchLocation" in found, found
    assert "app.services.cache.MeshCache" in found, found
    assert "app.models.advisory.Advisory" not in found, "a defined symbol was accused"


def test_the_finding_carries_what_a_round_needs_to_act(tmp_path):
    """A boot log names no file. This gate has to, or the round guesses."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": "from .routers.auth import seed_demo_user\n",
            "backend/app/routers/auth.py": "class User:\n    pass\n",
        },
    )
    finding = find_missing_symbols(code)[0]
    assert finding["file"] == "backend/app/routers/auth.py"
    assert "backend/app/main.py" in finding["importers"]
    assert finding["did_you_mean"] == ["User"], finding


def test_a_package_level_absolute_import_is_seen(tmp_path):
    """`from app.models import X` names the package; the table keys the file as `__init__`."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/__init__.py": "from .advisory import Advisory\n",
            "backend/app/models/advisory.py": "class Advisory:\n    pass\n",
            "backend/app/main.py": "from app.models import Advisory, WatchLocation\n",
        },
    )
    found = {f"{i['module']}.{i['symbol']}" for i in find_missing_symbols(code, limit=40)}
    assert "app.models.WatchLocation" in found, found
    assert "app.models.Advisory" not in found, "a re-export was reported as missing"


def test_importing_a_submodule_is_not_a_missing_symbol(tmp_path):
    """A false critical is worse than a miss — this gate decides whether work is kept."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/__init__.py": "from . import advisory\n",
            "backend/app/models/advisory.py": "class Advisory:\n    pass\n",
            "backend/app/main.py": "from app import models\n",
            "backend/app/__init__.py": "",
        },
    )
    assert find_missing_symbols(code) == []


def test_a_module_that_synthesises_attributes_is_still_left_alone(tmp_path):
    """`__getattr__` makes a module unanalysable; the pre-existing restraint must survive."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/__init__.py": "from .dyn import anything\n",
            "backend/app/models/dyn.py": "def __getattr__(name):\n    return name\n",
        },
    )
    assert find_missing_symbols(code) == []


def test_third_party_imports_stay_silent(tmp_path):
    """The `continue` that skips packages we do not own was never the bug."""
    code = _tree(
        tmp_path / "code",
        {"backend/app/main.py": "from fastapi import FastAPI\nfrom sqlalchemy.orm import Session\n"},
    )
    assert find_missing_symbols(code) == []


def test_the_gate_this_feeds_votes_on_keeping_a_round():
    """Structural: module health is in the whitelist, so this fix changes revert decisions."""
    from core.round_regression_guard import GUARD_SCORED_GATES

    assert "module health" in GUARD_SCORED_GATES


# --- a module that does not exist at all ------------------------------------------------------


def test_an_import_of_a_module_that_does_not_exist_is_reported(tmp_path):
    """The other half of the same silence.

    `find_missing_symbols` stays quiet when the target module is unknown, which is right for
    `fastapi` — we do not own it. The same `continue` swallowed
    `from ..schemas.auth import LoginRequest` in a product whose schemas package held only
    advisory.py, analytics.py and operator.py: ModuleNotFoundError at import, app never starts,
    and the only report was a uvicorn traceback in the demo-journey log naming no file to fix.

    A relative import cannot be third-party, and an absolute import whose first segment is one of
    the product's own top-level packages cannot be either. Those two rules make it checkable.
    """
    from web.backend.services.duplicate_module_check import find_missing_modules

    code = _tree(
        tmp_path / "code",
        {
            "backend/app/__init__.py": "",
            "backend/app/schemas/advisory.py": "class A:\n    pass\n",
            "backend/app/routers/auth.py": (
                "from ..schemas.auth import LoginRequest\nfrom fastapi import APIRouter\n"
            ),
            "backend/app/main.py": "import app.services.nowhere\nfrom app.schemas.advisory import A\n",
        },
    )
    found = {i["module"] for i in find_missing_modules(code)}
    assert found == {"app.schemas.auth", "app.services.nowhere"}, found


def test_third_party_and_existing_modules_are_left_alone(tmp_path):
    from web.backend.services.duplicate_module_check import find_missing_modules

    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": (
                "from fastapi import FastAPI\nimport sqlalchemy\n"
                "from app.db import engine\nfrom .db import engine as e2\n"
            ),
            "backend/app/db.py": "engine = None\n",
        },
    )
    assert find_missing_modules(code) == []


def test_a_package_without_an_init_still_counts_as_present(tmp_path):
    """Namespace-style layouts must not be accused of not existing."""
    from web.backend.services.duplicate_module_check import find_missing_modules

    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": "from app.services.cache import MeshCache\n",
            "backend/app/services/cache.py": "class MeshCache:\n    pass\n",
        },
    )
    assert find_missing_modules(code) == []


def test_the_finding_names_the_importer_and_the_consequence(tmp_path):
    from web.backend.services.duplicate_module_check import find_missing_modules

    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/auth.py": "from ..schemas.auth import LoginRequest\n",
            "backend/app/schemas/authentication.py": "class LoginRequest:\n    pass\n",
        },
    )
    finding = find_missing_modules(code)[0]
    assert finding["severity"] == "critical"
    assert "backend/app/routers/auth.py" in finding["detail"]
    assert "ModuleNotFoundError" in finding["detail"]
    assert finding["did_you_mean"] == ["app.schemas.authentication"], finding


def test_it_leads_the_blocking_list_and_the_health_gate():
    """Structural: a detector nothing consumes changes nothing."""
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(
        encoding="utf-8"
    )
    assert "absent_modules = find_missing_modules(code_dir)" in check
    assert '"code": "missing_module"' in check

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    head = qa[: qa.index("# Deletions next")]
    assert '"missing_module"' in head
    assert head.index('"missing_module"') < head.index('"duplicate_tablename"'), (
        "a tree that cannot be imported is ranked below a duplicate table"
    )


def test_a_name_only_tests_want_points_at_the_test(tmp_path):
    """The last defect of the night, and it resisted four rounds.

    `test_rule_engine.py` imported `evaluate_advisory`; the module defines `compute_advisory`. The
    finding named the defining module, so every round went there — into a file where the anchor it
    chose appears three times — instead of the one-line import in the test.

    A test importing a name the module never had was written against an API that does not exist.
    Changing production code to satisfy it is the tail wagging the dog, and it is also the harder edit.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/rule_engine.py": "def compute_advisory():\n    return 1\n",
            "backend/tests/unit/test_rule_engine.py": (
                "from app.services.rule_engine import evaluate_advisory\n"
            ),
        },
    )
    finding = find_missing_symbols(code)[0]
    assert finding["only_tests_want_it"] is True
    assert "Fix the import in the test" in finding["fix_hint"]
    assert "compute_advisory" in finding["fix_hint"]


def test_a_name_production_code_wants_does_not_get_that_hint(tmp_path):
    """One non-test importer and it is a real gap in the module, not a wrong test."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/rule_engine.py": "def compute_advisory():\n    return 1\n",
            "backend/tests/unit/test_rule_engine.py": (
                "from app.services.rule_engine import evaluate_advisory\n"
            ),
            "backend/app/routers/advisory.py": (
                "from ..services.rule_engine import evaluate_advisory\n"
            ),
        },
    )
    finding = find_missing_symbols(code)[0]
    assert finding["only_tests_want_it"] is False
    assert finding["fix_hint"] == ""


def test_the_hint_leads_the_health_gate_detail():
    """It has to be the first thing read, or it is advice after the decision."""
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parents[1] / "web" / "backend" / "services"
           / "duplicate_module_check.py").read_text(encoding="utf-8")
    block = src[src.index('"code": "missing_symbol"') :][:900]
    assert '(item.get("fix_hint") + " ") if item.get("fix_hint") else ""' in block
