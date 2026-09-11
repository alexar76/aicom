"""The SQLAlchemy twin of missing_attribute: the other side of the pair does not exist.

Found the way every sibling was — a live product dead at boot with every static counter at zero:

    sqlalchemy.exc.InvalidRequestError: Mapper 'Mapper[Advisory(advisories)]' has no property
    'invoke_logs'. If this property was indicated from other mappers …

`InvokeAuditLog.advisory` pointed back at `Advisory.invoke_logs`; `Advisory` calls that field
`audit_logs`. The mapper configures lazily, so the first query kills the app, nothing importable is
wrong, every import-level detector stayed silent — and the rounds went back to guessing, measured as
two rounds editing `deps.py` while both halves of the defect sat in the models.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_mismatched_back_populates


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


ADVISORY = (
    "from sqlalchemy.orm import relationship\n\n"
    "class Advisory:\n"
    '    __tablename__ = "advisories"\n'
    '    audit_logs = relationship("InvokeAuditLog", back_populates="advisory")\n'
)


def test_the_live_mismatch_is_found_with_both_names(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/advisory.py": ADVISORY,
            "backend/app/models/audit.py": (
                "from sqlalchemy.orm import relationship\n\n"
                "class InvokeAuditLog:\n"
                '    __tablename__ = "invoke_audit_logs"\n'
                '    advisory = relationship("Advisory", back_populates="invoke_logs")\n'
            ),
        },
    )
    found = find_mismatched_back_populates(code)
    assert len(found) == 1, found
    f = found[0]
    assert (f["class"], f["attr"], f["target"], f["expected"]) == (
        "InvokeAuditLog", "advisory", "Advisory", "invoke_logs",
    )
    assert f["did_you_mean"] == ["audit_logs"]
    assert f["file"] == "backend/app/models/audit.py"
    assert "ONE-TOKEN rename" in f["detail"]
    assert "Do not delete the relationship" in f["detail"]


def test_a_correct_pair_is_silent(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/advisory.py": ADVISORY,
            "backend/app/models/audit.py": (
                "from sqlalchemy.orm import relationship\n\n"
                "class InvokeAuditLog:\n"
                '    advisory = relationship("Advisory", back_populates="audit_logs")\n'
            ),
        },
    )
    assert find_mismatched_back_populates(code) == []


def test_an_unknown_target_class_is_not_a_mismatch(tmp_path):
    """That is missing_symbol territory; guessing here would double-report it."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/audit.py": (
                "from sqlalchemy.orm import relationship\n\n"
                "class InvokeAuditLog:\n"
                '    advisory = relationship("NoSuchClass", back_populates="whatever")\n'
            ),
        },
    )
    assert find_mismatched_back_populates(code) == []


def test_a_relationship_without_back_populates_is_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/a.py": (
                "from sqlalchemy.orm import relationship\n\n"
                "class A:\n"
                '    items = relationship("B")\n'
                "class B:\n"
                "    pass\n"
            ),
        },
    )
    assert find_mismatched_back_populates(code) == []


def test_the_reciprocal_side_satisfies_via_its_own_relationship(tmp_path):
    """The other side may be a relationship rather than a column, and usually is."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/pair.py": (
                "from sqlalchemy.orm import relationship\n\n"
                "class Parent:\n"
                '    children = relationship("Child", back_populates="parent")\n'
                "class Child:\n"
                '    parent = relationship("Parent", back_populates="children")\n'
            ),
        },
    )
    assert find_mismatched_back_populates(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "bad_pairs = find_mismatched_back_populates(code_dir)" in check
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not bad_pairs" in passed_expr

    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "10 * len(find_mismatched_back_populates(code_root, limit=200))" in score
    breakdown = dev[dev.index("def _tree_defect_breakdown(") : dev.index("def _breakdown_delta(")]
    assert '"mismatched_back_populates"' in breakdown

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"mismatched_back_populates"' in qa[: qa.index("# Deletions next")]

    executor = (root / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    assert '(find_mismatched_back_populates, "mismatched_back_populates")' in executor
