"""An SDK the product never calls must not be shipped to Vercel.

Two builds died on ``uv lock`` before a line of product code ran, both because of a
dependency the product did not use:

1. ``aimarket-agent==0.1.0`` — a version that never existed. Already handled: an
   unsatisfiable pin loses its version, and is dropped when nothing imports it.
2. ``aimarket-agent`` at a version that *does* exist, next to ``httpx==0.27.0``. Every
   release of the SDK requires ``httpx>=0.28``, so there was no solution — and the check
   from (1) never fired, because that one only inspects pins the index cannot satisfy.

Hence the rule locked in here: **ours, and unimported, is dropped** regardless of whether
the pin is valid. Kept narrow on purpose — the tests below also pin the packages that must
survive, because a blanket "drop what is not imported" would strip the server, the email
validator and the DB driver, none of which appear in an import statement.

These tests never reach PyPI: every requirement they drop is dropped before the index
lookup, and the survivors are asserted by identity, so the suite is offline and fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.vercel_fullstack_adapter import resolvable_requirements


@pytest.fixture()
def code_dir(tmp_path: Path) -> Path:
    """A product tree that imports ordinary libraries and none of our SDKs."""
    app = tmp_path / "backend" / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "import httpx\n"
        "from sqlalchemy import create_engine\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )
    return tmp_path


def test_unused_sdk_is_dropped_even_when_its_pin_is_valid(code_dir):
    """The exact second failure: a real version whose httpx floor has no solution."""
    out, notes = resolvable_requirements(
        ["fastapi==0.110.0", "httpx==0.27.0", "aimarket-agent==2.2.0"], code_dir
    )
    assert "aimarket-agent==2.2.0" not in out
    assert "httpx==0.27.0" in out, "the product's own pin must survive; the SDK is what goes"
    assert "fastapi==0.110.0" in out
    assert any("nothing imports aimarket-agent" in n for n in notes)


def test_unused_sdk_is_dropped_whatever_the_constraint_shape(code_dir):
    out, _ = resolvable_requirements(
        [
            "aimarket-agent",
            "aimarket-agent>=2.0",
            "aimarket-hub==3.2.0",
            "aimarket-bridges[all]==0.1.0",
            "aimarket-agent==2.2.0; python_version>='3.11'",
        ],
        code_dir,
    )
    assert out == [], f"unused SDK survived in some form: {out}"


def test_an_sdk_the_product_actually_imports_is_kept(tmp_path: Path):
    """A product that integrates through the mesh needs the SDK — that is the whole point.

    Dropping it here would silently break the integration at runtime, which is worse than
    a failed build: the deploy would succeed and the product would not work.
    """
    app = tmp_path / "backend" / "app"
    app.mkdir(parents=True)
    (app / "mesh.py").write_text(
        "from aimarket_agent import Agent\n\nagent = Agent()\n", encoding="utf-8"
    )
    out, notes = resolvable_requirements(["aimarket-agent==2.2.0"], tmp_path)
    assert out == ["aimarket-agent==2.2.0"]
    assert notes == []


def test_third_party_runtime_deps_that_are_never_imported_survive(code_dir):
    """Why the rule is narrow rather than "drop what is not imported".

    None of these appear in an import statement in a typical generated product, and every
    one of them is required for it to run.
    """
    reqs = [
        "uvicorn[standard]==0.29.0",   # runs the app
        "email-validator==2.1.1",      # backs pydantic EmailStr
        "python-multipart==0.0.9",     # FastAPI form parsing
        "passlib[bcrypt]==1.7.4",      # reached through passlib's own backend lookup
        "alembic==1.13.1",             # invoked as a CLI
    ]
    out, notes = resolvable_requirements(list(reqs), code_dir)
    assert out == reqs
    assert notes == []


def test_no_code_dir_means_no_verdict(tmp_path: Path):
    """Without a tree to inspect, "unimported" is unknowable — so nothing is dropped."""
    out, _ = resolvable_requirements(["aimarket-agent==2.2.0"], None)
    assert out == ["aimarket-agent==2.2.0"]
