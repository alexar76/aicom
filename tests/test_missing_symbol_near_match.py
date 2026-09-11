"""Writer and caller often disagree about the name, not the behaviour."""

from pathlib import Path

from web.backend.services.duplicate_module_check import (
    find_missing_symbols,
    run_duplicate_module_check,
)


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_the_real_case_is_named_as_a_rename(tmp_path, monkeypatch):
    """security.py defined seed_demo_operator; main.py imported get_or_create_demo_operator."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-x"
    _w(root, "backend/app/core/security.py", "def seed_demo_operator():\n    pass\n")
    _w(root, "backend/app/main.py", "from app.core.security import get_or_create_demo_operator\n")

    found = find_missing_symbols(root)
    assert found[0]["did_you_mean"] == ["seed_demo_operator"]

    report = run_duplicate_module_check("prod-x")
    detail = next(i["detail"] for i in report["issues"] if i["code"] == "missing_symbol")
    assert "seed_demo_operator" in detail
    # The prescribed fix is an alias, which satisfies both names at once.
    assert "get_or_create_demo_operator = seed_demo_operator" in detail


def test_no_suggestion_when_nothing_is_close(tmp_path):
    root = tmp_path / "code" / "prod-y"
    _w(root, "backend/app/a.py", "def totally_unrelated():\n    pass\n")
    _w(root, "backend/app/b.py", "from app.a import quux\n")
    found = find_missing_symbols(root)
    assert found[0]["did_you_mean"] == []


def test_suggestion_is_capped_at_two(tmp_path):
    root = tmp_path / "code" / "prod-z"
    _w(
        root,
        "backend/app/a.py",
        "def get_user():\n    pass\ndef get_users():\n    pass\ndef get_user_by_id():\n    pass\n",
    )
    _w(root, "backend/app/b.py", "from app.a import get_userr\n")
    assert len(find_missing_symbols(root)[0]["did_you_mean"]) <= 2


def test_snake_case_words_rank_above_raw_character_overlap(tmp_path, monkeypatch):
    """difflib offered verify_password ahead of hash_password for get_password_hash."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-rank"
    _w(
        root,
        "backend/app/core/security.py",
        "def hash_password(p):\n    pass\ndef verify_password(a, b):\n    pass\n",
    )
    _w(root, "backend/app/services/seed.py", "from app.core.security import get_password_hash\n")

    found = find_missing_symbols(root)
    assert found[0]["did_you_mean"][0] == "hash_password", found[0]["did_you_mean"]


def test_the_detail_prescribes_an_alias_not_a_rename(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "code" / "prod-alias"
    _w(root, "backend/app/core/security.py", "def hash_password(p):\n    pass\n")
    _w(root, "backend/app/services/seed.py", "from app.core.security import get_password_hash\n")

    report = run_duplicate_module_check("prod-alias")
    detail = next(i["detail"] for i in report["issues"] if i["code"] == "missing_symbol")
    assert "get_password_hash = hash_password" in detail
    assert "flip-flopped" in detail
