"""When one half of a product is green, a repair round must not touch it."""

from pathlib import Path

from agents.dev import _revert_out_of_scope_writes


def _logs():
    seen = []
    return seen, lambda level, msg: seen.append((level, msg))


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_backend_edits_are_reverted_when_the_round_is_scoped_to_frontend(tmp_path):
    """The real case: boot+contract+module-health green, only the frontend failing."""
    root = tmp_path / "code"
    _w(root, "backend/app/main.py", "NEW backend\n")
    _w(root, "frontend/src/App.tsx", "NEW frontend\n")
    previous = {"backend/app/main.py": "OLD backend\n", "frontend/src/App.tsx": "OLD frontend\n"}

    seen, log = _logs()
    reverted = _revert_out_of_scope_writes(
        root, previous, ["backend/app/main.py", "frontend/src/App.tsx"], ["frontend/"],
        log=log, product_id="p",
    )
    assert reverted == {"backend/app/main.py"}
    assert (root / "backend/app/main.py").read_text(encoding="utf-8") == "OLD backend\n"
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == "NEW frontend\n"
    assert any("out-of-scope" in m for _, m in seen)


def test_new_files_invented_outside_the_scope_are_removed(tmp_path):
    root = tmp_path / "code"
    _w(root, "backend/app/extra.py", "invented\n")
    _, log = _logs()
    reverted = _revert_out_of_scope_writes(
        root, {}, ["backend/app/extra.py"], ["frontend/"], log=log, product_id="p"
    )
    assert reverted == {"backend/app/extra.py"}
    assert not (root / "backend/app/extra.py").exists()


def test_no_scope_means_no_restriction(tmp_path):
    root = tmp_path / "code"
    _w(root, "backend/app/main.py", "NEW\n")
    _, log = _logs()
    assert _revert_out_of_scope_writes(
        root, {"backend/app/main.py": "OLD\n"}, ["backend/app/main.py"], [], log=log, product_id="p"
    ) == set()
    assert (root / "backend/app/main.py").read_text(encoding="utf-8") == "NEW\n"


def test_scope_matching_is_prefix_based_and_slash_tolerant(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/a.tsx", "keep\n")
    _w(root, "backend/x.py", "revert\n")
    _, log = _logs()
    reverted = _revert_out_of_scope_writes(
        root, {"backend/x.py": "old\n"}, ["frontend/src/a.tsx", "backend/x.py"],
        ["frontend"],  # no trailing slash
        log=log, product_id="p",
    )
    assert reverted == {"backend/x.py"}


def test_multiple_scopes_are_all_allowed(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/a.tsx", "keep\n")
    _w(root, "shared/b.ts", "keep\n")
    _w(root, "backend/c.py", "revert\n")
    _, log = _logs()
    reverted = _revert_out_of_scope_writes(
        root, {"backend/c.py": "old\n"},
        ["frontend/a.tsx", "shared/b.ts", "backend/c.py"], ["frontend/", "shared/"],
        log=log, product_id="p",
    )
    assert reverted == {"backend/c.py"}
