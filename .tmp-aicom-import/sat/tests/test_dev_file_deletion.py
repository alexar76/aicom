"""Repair rounds must be able to retire a module, not only add another one.

``_apply_requested_deletions`` returns {path: previous content} so a round that is
rejected as a whole can put the files back byte for byte.
"""

from pathlib import Path

from agents.dev import _apply_requested_deletions


def _logs():
    seen = []

    def log(level, msg):
        seen.append((level, msg))

    return seen, log


def test_deletes_listed_files(tmp_path):
    root = tmp_path / "code"
    (root / "app").mkdir(parents=True)
    (root / "app" / "seed.py").write_text("x", encoding="utf-8")
    (root / "app" / "keep.py").write_text("y", encoding="utf-8")

    _, log = _logs()
    removed = _apply_requested_deletions(root, ["app/seed.py"], log=log, product_id="p")
    assert list(removed) == ["app/seed.py"]
    assert not (root / "app" / "seed.py").exists()
    assert (root / "app" / "keep.py").exists()


def test_a_path_written_this_round_survives_its_own_deletion(tmp_path):
    """files[] + delete_files on the same path is a rename, not a removal."""
    root = tmp_path / "code"
    root.mkdir()
    (root / "useAuth.tsx").write_text("new", encoding="utf-8")

    _, log = _logs()
    removed = _apply_requested_deletions(
        root, ["useAuth.tsx"], log=log, product_id="p", keep={"useAuth.tsx"}
    )
    assert removed == {}
    assert (root / "useAuth.tsx").exists()


def test_paths_outside_the_product_are_refused(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("keep me", encoding="utf-8")

    seen, log = _logs()
    removed = _apply_requested_deletions(
        root, ["../secret.txt", "/etc/passwd", ""], log=log, product_id="p"
    )
    assert removed == {}
    assert outside.exists()
    assert any("unsafe delete path" in m for _, m in seen)


def test_missing_files_and_bad_input_are_ignored(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    _, log = _logs()
    assert _apply_requested_deletions(root, ["nope.py"], log=log, product_id="p") == {}
    assert _apply_requested_deletions(root, None, log=log, product_id="p") == {}
    assert _apply_requested_deletions(root, "app/seed.py", log=log, product_id="p") == {}


def test_a_directory_path_is_not_removed(tmp_path):
    root = tmp_path / "code"
    (root / "app").mkdir(parents=True)
    _, log = _logs()
    assert _apply_requested_deletions(root, ["app"], log=log, product_id="p") == {}
    assert (root / "app").is_dir()


def test_refuses_to_delete_a_module_something_still_imports(tmp_path):
    """A delete list is model output; it removed a product's only auth hook."""
    root = tmp_path / "code"
    (root / "src" / "hooks").mkdir(parents=True)
    (root / "src" / "pages").mkdir(parents=True)
    (root / "src" / "hooks" / "useAuth.ts").write_text("export const x = 1\n", encoding="utf-8")
    (root / "src" / "pages" / "Login.tsx").write_text(
        "import { x } from '../hooks/useAuth';\n", encoding="utf-8"
    )

    seen, log = _logs()
    removed = _apply_requested_deletions(root, ["src/hooks/useAuth.ts"], log=log, product_id="p")
    assert removed == {}
    assert (root / "src" / "hooks" / "useAuth.ts").exists()
    assert any("still imported by" in m for _, m in seen)


def test_refuses_to_delete_a_python_module_still_imported(tmp_path):
    root = tmp_path / "code"
    (root / "backend" / "app" / "core").mkdir(parents=True)
    (root / "backend" / "app" / "core" / "seed.py").write_text("def s():\n    pass\n", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from app.core.seed import s\n", encoding="utf-8"
    )

    seen, log = _logs()
    removed = _apply_requested_deletions(
        root, ["backend/app/core/seed.py"], log=log, product_id="p"
    )
    assert removed == {}
    assert any("still imported by" in m for _, m in seen)


def test_files_removed_together_do_not_keep_each_other_alive(tmp_path):
    """Two halves of a superseded pair import each other; both should still go."""
    root = tmp_path / "code"
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "old_a.py").write_text("from app.old_b import q\n", encoding="utf-8")
    (root / "backend" / "app" / "old_b.py").write_text("q = 1\n", encoding="utf-8")

    _, log = _logs()
    removed = _apply_requested_deletions(
        root, ["backend/app/old_a.py", "backend/app/old_b.py"], log=log, product_id="p"
    )
    assert sorted(removed) == ["backend/app/old_a.py", "backend/app/old_b.py"]


def test_a_rename_still_works_when_the_new_file_imports_nothing_old(tmp_path):
    root = tmp_path / "code"
    (root / "src").mkdir(parents=True)
    (root / "src" / "useAuth.ts").write_text("export const x = 1\n", encoding="utf-8")
    (root / "src" / "useAuth.tsx").write_text("export const x = 1\n", encoding="utf-8")

    _, log = _logs()
    removed = _apply_requested_deletions(
        root, ["src/useAuth.ts"], log=log, product_id="p", keep={"src/useAuth.tsx"}
    )
    assert list(removed) == ["src/useAuth.ts"]
