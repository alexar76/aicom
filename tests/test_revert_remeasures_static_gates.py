"""A restored diagnosis can be older than the detectors that would explain the tree.

Restoring the accepted diagnosis alongside the accepted tree fixed a compounding loop — the next
round used to be handed the rejected round's findings and edited against a description of a tree
that no longer existed. That part stands.

What it did not account for: the diagnosis was produced by the detectors that existed *then*. The
missing-symbol detector learned to resolve relative imports and immediately found six names the
product imports and defines nowhere — ``MeshCache``, ``CachedMeshReading``, ``seed_demo_user`` —
on the very tree that had just been restored, while the diagnosis handed to the next round listed
none of them. The round was about to be sent to repair a tree whose reason for not booting was
known and withheld.

Static findings are a pure function of the tree: measured twice on an unchanged tree they came back
identical, which is exactly why these gates are the ones allowed to vote. So re-deriving them costs
one cheap pass and cannot disagree with itself. Anything an LLM or a browser produced is left as
restored — re-running those would be neither cheap nor repeatable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.task_executor_agent import _refresh_static_findings

STALE = {
    "source": "qa",
    "qa_findings": [
        {"severity": "high", "title": "Demo/TZ gate: low_spec_alignment", "description": "..."},
        {"severity": "medium", "title": "Module health: duplicate_modules", "description": "old"},
        {"severity": "high", "title": "Browser E2E: a11y_missing_h1", "description": "..."},
    ],
}


@pytest.fixture
def broken_tree(tmp_path: Path) -> Path:
    """Reduced from the live product: two imports of names defined nowhere."""
    code = tmp_path / "code"
    (code / "backend" / "app" / "models").mkdir(parents=True)
    (code / "backend" / "app" / "services").mkdir(parents=True)
    (code / "backend" / "app" / "models" / "__init__.py").write_text(
        "from .advisory import Advisory, CachedMeshReading\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "models" / "advisory.py").write_text(
        "class Advisory:\n    pass\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "services" / "cache.py").write_text(
        "class ReadingCache:\n    pass\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "services" / "atlas.py").write_text(
        "from .cache import MeshCache\n", encoding="utf-8"
    )
    return code


def test_the_withheld_boot_blockers_are_added(broken_tree):
    merged = _refresh_static_findings(STALE, broken_tree, "prod-x")
    symbols = {
        b["description"].split(" never defines ")[1].split(",")[0]
        for b in merged["qa_findings"]
        if b["title"] == "Module health: missing_symbol"
    }
    assert symbols == {"CachedMeshReading", "MeshCache"}, merged["qa_findings"]


def test_the_finding_says_where_to_define_it(broken_tree):
    merged = _refresh_static_findings(STALE, broken_tree, "prod-x")
    finding = next(b for b in merged["qa_findings"] if "CachedMeshReading" in b["description"])
    assert finding["file"] == "backend/app/models/advisory.py"
    assert "models/__init__.py" in finding["description"], "the importer is not named"
    assert finding["severity"] == "critical"


def test_stale_static_findings_are_replaced_not_duplicated(broken_tree):
    """The old `Module health: duplicate_modules` line described the previous detector pass."""
    merged = _refresh_static_findings(STALE, broken_tree, "prod-x")
    titles = [b["title"] for b in merged["qa_findings"]]
    assert "Module health: duplicate_modules" not in titles
    assert len([t for t in titles if t.startswith("Module health:")]) == 2


def test_findings_from_gates_that_cannot_be_cheaply_repeated_survive(broken_tree):
    """Re-running a browser crawl or an LLM judgement here would be neither cheap nor stable."""
    merged = _refresh_static_findings(STALE, broken_tree, "prod-x")
    titles = [b["title"] for b in merged["qa_findings"]]
    assert "Demo/TZ gate: low_spec_alignment" in titles
    assert "Browser E2E: a11y_missing_h1" in titles


def test_the_boot_blockers_lead(broken_tree):
    """The round works top-down; nothing else matters while the app does not start."""
    merged = _refresh_static_findings(STALE, broken_tree, "prod-x")
    assert merged["qa_findings"][0]["title"].startswith("Module health:")


def test_a_clean_tree_leaves_the_diagnosis_exactly_as_restored(tmp_path):
    """No static defects is not a licence to rewrite the stored diagnosis."""
    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    assert _refresh_static_findings(STALE, code, "prod-x") is STALE


def test_an_unreadable_tree_does_not_lose_the_diagnosis(tmp_path):
    """A tidy-up must never be able to destroy the work list."""
    assert _refresh_static_findings(STALE, tmp_path / "nope", "prod-x") == STALE


def test_the_revert_path_calls_it():
    """Structural: the fix is inert unless the guard uses it."""
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    revert = src[src.index("accepted_ctx = product.get(") :]
    revert = revert[: revert.index("product[\"surrogate_repair_hint\"]")]
    assert "_refresh_static_findings(accepted_ctx, code_root, pid)" in revert
