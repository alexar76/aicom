"""A repair round may change anything except the contract other files depend on."""

from pathlib import Path

from agents.dev import _revert_symbol_regressions


def _logs():
    seen = []
    return seen, lambda level, msg: seen.append((level, msg))


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


GOOD = "def hash_password(p):\n    return p\n\n\ndef verify(p, h):\n    return True\n"
DROPPED = "def verify(p, h):\n    return True\n"


def test_a_rewrite_that_drops_a_depended_on_symbol_is_rolled_back(tmp_path):
    """The regression that recurred three times: security.py loses hash_password."""
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", DROPPED)          # just written
    _write(root, "backend/app/core/seed.py", "from app.core.security import hash_password\n")

    seen, log = _logs()
    reverted = _revert_symbol_regressions(
        root, {"backend/app/core/security.py": GOOD}, log=log, product_id="p"
    )
    assert reverted == {"backend/app/core/security.py"}
    restored = (root / "backend" / "app" / "core" / "security.py").read_text(encoding="utf-8")
    assert "hash_password" in restored
    assert any("Reverted" in m for _, m in seen)


def test_a_symbol_that_never_existed_is_a_finding_not_a_regression(tmp_path):
    """Rolling back here would erase legitimate new work."""
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", DROPPED)
    _write(root, "backend/app/core/seed.py", "from app.core.security import brand_new\n")

    _, log = _logs()
    assert _revert_symbol_regressions(
        root, {"backend/app/core/security.py": DROPPED}, log=log, product_id="p"
    ) == set()


def test_a_clean_rewrite_is_left_alone(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", GOOD + "\n\ndef extra():\n    pass\n")
    _write(root, "backend/app/core/seed.py", "from app.core.security import hash_password\n")

    _, log = _logs()
    assert _revert_symbol_regressions(
        root, {"backend/app/core/security.py": GOOD}, log=log, product_id="p"
    ) == set()
    assert "extra" in (root / "backend" / "app" / "core" / "security.py").read_text(encoding="utf-8")


def test_files_not_written_this_round_are_never_touched(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/core/security.py", DROPPED)
    _write(root, "backend/app/core/seed.py", "from app.core.security import hash_password\n")

    _, log = _logs()
    # Empty snapshot = this round wrote nothing we can roll back.
    assert _revert_symbol_regressions(root, {}, log=log, product_id="p") == set()
    assert "hash_password" not in (root / "backend" / "app" / "core" / "security.py").read_text(
        encoding="utf-8"
    )


def test_more_than_ten_dropped_symbols_are_all_protected(tmp_path):
    """The report caps at ten findings; the rollback must not inherit that cap."""
    root = tmp_path / "code"
    previous = {}
    for i in range(14):
        rel = f"backend/app/mod{i}.py"
        good = f"def sym{i}():\n    return {i}\n"
        _write(root, rel, "x = 1\n")                       # rewritten, symbol dropped
        _write(root, f"backend/app/use{i}.py", f"from app.mod{i} import sym{i}\n")
        previous[rel] = good

    _, log = _logs()
    reverted = _revert_symbol_regressions(root, previous, log=log, product_id="p")
    assert len(reverted) == 14, f"only {len(reverted)} protected"
    for i in range(14):
        assert "def sym" in (root / f"backend/app/mod{i}.py").read_text(encoding="utf-8")


def test_only_the_file_that_left_a_name_unbound_is_reverted(tmp_path):
    """Rejecting a whole round for one bad file also discards its good work."""
    from agents.dev import _revert_files_with_new_undefined_names

    root = tmp_path / "code"
    _write(root, "backend/app/bad.py", "from os import path\nx = Missing\n")   # regressed
    _write(root, "backend/app/good.py", "y = 1\n")                             # fine
    previous = {
        "backend/app/bad.py": "from os import path\nMissing = 1\nx = Missing\n",
        "backend/app/good.py": "y = 0\n",
    }

    _, log = _logs()
    reverted = _revert_files_with_new_undefined_names(
        root, previous, log=log, product_id="p", already=set()
    )
    assert reverted == {"backend/app/bad.py"}
    assert "Missing = 1" in (root / "backend/app/bad.py").read_text(encoding="utf-8")
    assert (root / "backend/app/good.py").read_text(encoding="utf-8") == "y = 1\n", "good work kept"


def test_a_name_that_was_already_unbound_before_is_not_a_regression(tmp_path):
    from agents.dev import _revert_files_with_new_undefined_names

    root = tmp_path / "code"
    _write(root, "backend/app/a.py", "x = Missing\n")
    previous = {"backend/app/a.py": "x = Missing\ny = 2\n"}  # Missing already unbound

    _, log = _logs()
    assert _revert_files_with_new_undefined_names(
        root, previous, log=log, product_id="p", already=set()
    ) == set()


def test_files_already_reverted_are_not_touched_again(tmp_path):
    from agents.dev import _revert_files_with_new_undefined_names

    root = tmp_path / "code"
    _write(root, "backend/app/a.py", "x = Missing\n")
    previous = {"backend/app/a.py": "Missing = 1\nx = Missing\n"}

    _, log = _logs()
    assert _revert_files_with_new_undefined_names(
        root, previous, log=log, product_id="p", already={"backend/app/a.py"}
    ) == set()
