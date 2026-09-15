"""A module-level name assigned inside an `if` is still defined.

Measured live, and it cost rounds at the very end of a product's repair cycle:

    backend/app/db.py
        if settings.database_url.startswith("sqlite"):
            engine = create_engine(...)      # indented — invisible to a column-zero regex
        else:
            engine = create_engine(...)
        SessionLocal = sessionmaker(bind=engine)   # ...two lines below, using it

    backend/app/main.py
        from app.db import Base, engine, SessionLocal   # reported as a MISSING SYMBOL

`missing_symbol` weighs 10 in the tree score, so one false accusation is enough to make a good
round look like a regression and get it reverted. Conditional engines, clients and settings are an
everyday pattern — a detector that cannot see them is worse than one that misses a real defect.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import (
    _module_level_bindings,
    find_missing_symbols,
)

LIVE_DB = '''from sqlalchemy import create_engine
from .config import settings

if settings.database_url.startswith("sqlite"):
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_the_live_shape_is_no_longer_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": LIVE_DB,
            "backend/app/main.py": "from app.db import Base, engine, SessionLocal\n",
        },
    )
    assert [f for f in find_missing_symbols(code) if f.get("symbol") == "engine"] == []


def test_bindings_from_every_top_level_block(tmp_path):
    names = _module_level_bindings(
        "if x:\n    a = 1\nelse:\n    a = 2\n"
        "try:\n    b = 1\nexcept ValueError:\n    b = 2\nfinally:\n    c = 3\n"
        "for i in range(3):\n    d = i\n"
        "with open('f') as fh:\n    e = fh\n"
        "g, h = 1, 2\n"
        "k: int = 5\n"
    )
    assert {"a", "b", "c", "d", "e", "g", "h", "k"} <= names


def test_locals_and_attributes_are_not_module_bindings():
    """A name assigned inside a function is not importable, and claiming otherwise would hide a
    real missing symbol — the opposite failure, and the more dangerous one."""
    names = _module_level_bindings(
        "def f():\n    hidden = 1\n    return hidden\n"
        "class C:\n    attr = 2\n"
        "visible = 3\n"
    )
    assert "visible" in names
    assert "f" in names and "C" in names
    assert "hidden" not in names
    assert "attr" not in names


def test_a_genuinely_missing_symbol_is_still_reported(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/db.py": LIVE_DB,
            "backend/app/main.py": "from app.db import engine, nonexistent_thing\n",
        },
    )
    reported = {f.get("symbol") for f in find_missing_symbols(code)}
    assert "nonexistent_thing" in reported
    assert "engine" not in reported


def test_an_unparsable_file_does_not_crash_the_detector(tmp_path):
    assert _module_level_bindings("def broken(:\n") == set()
