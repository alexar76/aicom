"""A repair round is judged as a whole: it may not leave the tree worse."""

from pathlib import Path

from agents.dev import _apply_requested_deletions, _tree_defect_score


def _logs():
    seen = []
    return seen, lambda level, msg: seen.append((level, msg))


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_score_counts_unresolvable_imports_and_unbound_names(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/security.py", "import os\n")
    _write(root, "backend/app/seed.py", "from app.security import hash_password\n")
    _write(root, "backend/app/models.py", "x = Column(Boolean)\n")
    # one missing symbol + two unbound names (Column, Boolean)
    assert _tree_defect_score(root) == 3


def test_a_clean_tree_scores_zero(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/security.py", "def hash_password(p):\n    return p\n")
    _write(root, "backend/app/seed.py", "from app.security import hash_password\n")
    assert _tree_defect_score(root) == 0


def test_score_is_comparable_before_and_after_a_bad_edit(tmp_path):
    """This is the comparison the round guard makes."""
    root = tmp_path / "code"
    _write(root, "backend/app/security.py", "def hash_password(p):\n    return p\n")
    _write(root, "backend/app/seed.py", "from app.security import hash_password\n")
    before = _tree_defect_score(root)

    _write(root, "backend/app/security.py", "import os\n")  # the regression
    after = _tree_defect_score(root)

    assert before == 0 and after == 1
    assert after > before, "the guard must see this round as worse"


def test_deletions_return_content_so_a_rejected_round_can_restore_them(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/old.py", "value = 1\n")
    _write(root, "backend/app/v1/old.py", "value = 2\n")
    _, log = _logs()

    removed = _apply_requested_deletions(root, ["backend/app/old.py"], log=log, product_id="p")
    assert removed == {"backend/app/old.py": "value = 1\n"}
    assert not (root / "backend/app/old.py").exists()

    # A rejected round puts it back byte for byte.
    for rel, content in removed.items():
        (root / rel).write_text(content, encoding="utf-8")
    assert (root / "backend/app/old.py").read_text(encoding="utf-8") == "value = 1\n"


def test_nothing_requested_returns_an_empty_mapping(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    _, log = _logs()
    assert _apply_requested_deletions(root, None, log=log, product_id="p") == {}
    assert _apply_requested_deletions(root, [], log=log, product_id="p") == {}


def test_a_syntax_error_dominates_the_score(tmp_path):
    """Without this the guard rewards breaking the parser: unparseable files are
    skipped by the name check, so the defect count drops and the round looks good."""
    root = tmp_path / "code"
    _write(root, "backend/app/security.py", "def hash_password(p):\n    return p\n")
    _write(root, "backend/app/seed.py", "from app.security import hash_password\n")
    clean = _tree_defect_score(root)
    assert clean == 0

    _write(root, "backend/app/main.py", "def broken(:\n    pass\n")
    broken = _tree_defect_score(root)
    assert broken >= 10, "a file that does not parse must outweigh ordinary findings"
    assert broken > clean


def test_breaking_the_parser_can_never_look_like_an_improvement(tmp_path):
    """The real regression: three name defects replaced by one SyntaxError."""
    root = tmp_path / "code"
    _write(root, "backend/app/a.py", "x = Missing1\ny = Missing2\nz = Missing3\n")
    before = _tree_defect_score(root)
    assert before == 3

    _write(root, "backend/app/a.py", "x = Missing1\ny = Missing2\nz = (\n")  # now unparseable
    after = _tree_defect_score(root)
    assert after > before, "the guard must reject this round, not accept it"


def test_fixing_an_unregistered_model_lowers_the_score(tmp_path):
    """The score must count what the agent is told to fix, or the fix can never land."""
    root = tmp_path / "code"
    _write(root, "backend/app/models/__init__.py", "from .thing import Thing\n")
    _write(root, "backend/app/models/thing.py", "class Thing(Base):\n    __tablename__ = 'things'\n")
    _write(root, "backend/app/main.py", "Base.metadata.create_all(bind=engine)\n")
    before = _tree_defect_score(root)
    assert before >= 1, "an unregistered model must register as a defect"

    _write(
        root,
        "backend/app/main.py",
        "from app import models\nBase.metadata.create_all(bind=engine)\n",
    )
    assert _tree_defect_score(root) < before, "fixing it must lower the score"
