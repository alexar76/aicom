"""The developer should learn it broke an import in seconds, not after a QA round."""

from pathlib import Path

from agents.dev import _self_check_written_files


def _log(level, msg):
    pass


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_reports_dangling_imports_from_files_written_this_round(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", "import os\n")
    _write(root, "backend/app/services/seed.py", "from app.core.security import hash_password\n")

    broke = _self_check_written_files(
        root, ["backend/app/services/seed.py"], log=_log, product_id="p"
    )
    assert len(broke) == 1
    assert "hash_password" in broke[0]
    assert "backend/app/core/security.py" in broke[0]


def test_ignores_defects_in_files_this_round_did_not_touch(tmp_path):
    """A pre-existing break elsewhere is QA's business, not a reason to regenerate.

    "Did not touch" means neither side: not the module missing the symbol, and
    not the module importing it.
    """
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", "import os\n")
    _write(root, "backend/app/legacy.py", "from app.core.security import hash_password\n")
    _write(root, "backend/app/unrelated.py", "value = 1\n")

    broke = _self_check_written_files(
        root, ["backend/app/unrelated.py"], log=_log, product_id="p"
    )
    assert broke == []


def test_clean_round_reports_nothing(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", "def hash_password(p):\n    return p\n")
    _write(root, "backend/app/services/seed.py", "from app.core.security import hash_password\n")

    assert _self_check_written_files(
        root, ["backend/app/services/seed.py"], log=_log, product_id="p"
    ) == []


def test_self_check_catches_a_missing_import_in_a_file_written_this_round(tmp_path):
    """The Boolean bug, caught in seconds instead of surviving fifteen rounds."""
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/models/scoring.py",
        "from sqlalchemy import Column, String\nx = Column(Boolean)\n",
    )
    broke = _self_check_written_files(
        root, ["backend/app/models/scoring.py"], log=_log, product_id="p"
    )
    assert any("Boolean" in b for b in broke)


def test_self_check_ignores_a_missing_import_in_an_untouched_file(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/legacy.py", "x = Column(Boolean)\n")
    _write(root, "backend/app/new.py", "y = 1\n")
    assert _self_check_written_files(root, ["backend/app/new.py"], log=_log, product_id="p") == []


def test_rewriting_a_module_and_dropping_a_symbol_others_import_is_caught(tmp_path):
    """The dominant regression: security.py rewritten without hash_password."""
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", "import os\n")           # written now
    _write(root, "backend/app/core/seed.py", "from app.core.security import hash_password\n")
    _write(root, "backend/app/services/x.py", "from app.core.security import hash_password\n")

    broke = _self_check_written_files(
        root, ["backend/app/core/security.py"], log=_log, product_id="p"
    )
    assert any("hash_password" in b for b in broke), broke


def test_untouched_definer_with_untouched_importers_is_still_ignored(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", "import os\n")
    _write(root, "backend/app/core/seed.py", "from app.core.security import hash_password\n")
    _write(root, "backend/app/new.py", "y = 1\n")

    assert _self_check_written_files(root, ["backend/app/new.py"], log=_log, product_id="p") == []
