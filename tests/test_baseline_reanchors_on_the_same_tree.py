"""Measuring the tree we already accepted must re-anchor the baseline, not argue with it.

A round can end without changing anything: the developer's own coherence check rejects each attempt
and restores the tree. QA then measures the accepted tree again, and comparing that to the stored
baseline is comparing a tree with itself — where any difference can only come from the two numbers
being measured differently, never from the code.

Which is exactly what happened. The baseline had been re-anchored by rescoring a *stored diagnosis*
that predated the missing-symbol fix, so it read 20 while today's gates measure the same tree at 29:

    17:25  reverted a repair round (20 -> 29, severity-weighted)   31 findings
    17:32  reverted a repair round (20 -> 29, severity-weighted)   31 findings

Identical numbers, twice, for a tree neither round had touched — six missing symbols the older
diagnosis never contained. Every round was losing to a phantom, and no amount of good work could
have won, because the comparison was not about the work.

The fix is structural rather than another corrected number: the accepted tree is fingerprinted, and
a measurement of that same fingerprint sets the baseline instead of being judged against it. It
therefore also self-heals the next time a detector gets sharper.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.round_regression_guard import tree_fingerprint


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_fingerprint_ignores_installed_dependencies(tmp_path):
    """A 150 MB virtualenv must not dominate the digest or its cost."""
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n"})
    before = tree_fingerprint(code)
    _tree(code, {"node_modules/pkg/index.js": "x" * 5000, ".aicom_sandbox/venv/lib/q.py": "y\n"})
    assert tree_fingerprint(code) == before


def test_the_fingerprint_follows_the_product_own_files(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n"})
    before = tree_fingerprint(code)
    _tree(code, {"backend/app/main.py": "x = 2\n"})
    assert tree_fingerprint(code) != before


def test_a_new_file_changes_it_and_a_rename_changes_it(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n"})
    base = tree_fingerprint(code)
    _tree(code, {"backend/app/extra.py": "y = 1\n"})
    added = tree_fingerprint(code)
    assert added != base
    (code / "backend" / "app" / "extra.py").rename(code / "backend" / "app" / "other.py")
    assert tree_fingerprint(code) not in (base, added)


def test_it_is_stable_across_calls(tmp_path):
    """An unstable fingerprint would re-anchor on every round and disable the guard."""
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n", "frontend/a.tsx": "z\n"})
    assert len({tree_fingerprint(code) for _ in range(5)}) == 1


def test_a_missing_directory_has_no_fingerprint(tmp_path):
    """No opinion rather than a wrong one: an unmeasurable tree must not re-anchor anything."""
    assert tree_fingerprint(tmp_path / "nope") is None


def test_the_guard_reanchors_instead_of_reverting():
    """Structural: the branch has to come *before* the accept/revert decision.

    Placed after it, a same-tree measurement that scored worse would already have been reverted —
    which is the bug this exists to remove.
    """
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    head = src[src.index("score = qa_defect_score(qa_result)") :]
    head = head[: head.index("if not restore_snapshot(")]
    reanchor = head.index('product.get("last_accepted_tree_fingerprint")')
    decision = head.index(
        'if (verdict(previous, score) == "accept" or breakthrough) and not visual_regression:'
    )
    assert reanchor < decision, "the same-tree check runs after the revert decision"
    assert "re-anchored the baseline" in head, "a silent re-anchor hides why the number moved"


def test_the_accepted_fingerprint_is_recorded_on_accept():
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    assert 'product["last_accepted_tree_fingerprint"] = fingerprint' in src


def test_the_key_survives_the_sqlite_round_trip():
    """New product-dict fields are dropped under SQLite unless allow-listed, and a dropped
    fingerprint would silently restore the phantom-baseline behaviour."""
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_accepted_tree_fingerprint" in PRODUCT_EXTRA_KEYS


def test_runtime_artifacts_do_not_move_the_fingerprint(tmp_path):
    """The backend E2E gate boots the app inside the tree with sqlite:///./sentinel.db.

    Every QA run rewrites that file, so a fingerprint that includes it can never match the accepted
    print — which switches off the same-tree re-anchor exactly when it is needed. Measured: two
    identical reverts (2 -> 5) on a tree whose code had not changed.
    """
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n"})
    before = tree_fingerprint(code)
    _tree(code, {"backend/sentinel.db": "binary-ish contents run 1"})
    assert tree_fingerprint(code) == before
    _tree(code, {"backend/sentinel.db": "different contents run 2", "backend/app.log": "lines"})
    assert tree_fingerprint(code) == before
    # And real code still moves it.
    _tree(code, {"backend/app/main.py": "x = 2\n"})
    assert tree_fingerprint(code) != before
