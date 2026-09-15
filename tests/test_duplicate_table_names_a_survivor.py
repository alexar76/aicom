"""«Keep ONE and delete the other» leaves the choice to the round, so the round remakes it.

Watched live across four rounds: ``allowance_state`` was declared twice, once in ``advisory.py``
and once in ``allowance.py``. A round deleted one and the counter went to zero. The next round —
rewriting ``advisory.py`` to add an unrelated missing symbol — put it back, and the same critical
defect appeared, cleared and reappeared without ever being resolved. The instruction was complete
about the problem and silent about the answer, which is an invitation to oscillate.

So the detector decides, once, and says so. The rule has to be deterministic or it oscillates for a
new reason — which is exactly what happened on the first attempt: filename matching the table
first, then "the module declaring fewest tables", then alphabetical. That middle term is a function
of what the round itself moves, and it flipped the verdict between rounds while nobody had touched
the duplicated table. Five more rounds burned. The rule is now filename match, then alphabetical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import find_duplicate_tablenames


def _models(tmp_path: Path, files: dict[str, str]) -> Path:
    code = tmp_path / "code"
    code.parent.mkdir(parents=True, exist_ok=True)
    (code / "backend" / "app" / "models").mkdir(parents=True)
    for name, body in files.items():
        (code / "backend" / "app" / "models" / name).write_text(body, encoding="utf-8")
    return code


def test_the_module_named_after_the_table_wins(tmp_path):
    """The live case: allowance_state belongs in allowance.py, not in advisory.py."""
    code = _models(
        tmp_path,
        {
            "advisory.py": (
                'class Advisory:\n    __tablename__ = "advisories"\n'
                'class AllowanceState:\n    __tablename__ = "allowance_state"\n'
            ),
            "allowance.py": 'class AllowanceState:\n    __tablename__ = "allowance_state"\n',
        },
    )
    finding = find_duplicate_tablenames(code)[0]
    assert finding["keep"] == "backend/app/models/allowance.py"
    assert finding["remove_from"] == ["backend/app/models/advisory.py"]
    assert "KEEP the declaration in backend/app/models/allowance.py" in finding["detail"]
    assert "DELETE AllowanceState from backend/app/models/advisory.py" in finding["detail"]


def test_the_verdict_is_stable_across_runs(tmp_path):
    """An unstable rule replaces one oscillation with another."""
    code = _models(
        tmp_path,
        {
            "audit.py": 'class AllowanceState:\n    __tablename__ = "allowance_state"\n',
            "advisory.py": 'class AllowanceState:\n    __tablename__ = "allowance_state"\n',
        },
    )
    verdicts = {find_duplicate_tablenames(code)[0]["keep"] for _ in range(5)}
    assert len(verdicts) == 1, verdicts


def test_the_verdict_does_not_move_when_other_classes_move(tmp_path):
    """The tie-break used to be "fewest tables in the file", and it flipped the answer.

    It reads well — a dedicated module is a better home than a grab-bag — but it is a function of
    things the round itself moves:

        17:46  keep backend/app/models/advisory.py, remove from audit.py
        18:09  keep backend/app/models/audit.py,    remove from advisory.py

    Nobody had touched allowance_state in between; other model classes moved, the table counts
    crossed over (advisory 4, audit 3), and the verdict flipped. The round obeyed each instruction
    in turn, so the duplicate survived five rounds with the baseline stuck at 10 — the very
    oscillation that naming a survivor exists to end, reintroduced by the tie-break itself.
    """
    shared = 'class AllowanceState:\n    __tablename__ = "allowance_state"\n'
    lean = _models(
        tmp_path / "lean",
        {
            "advisory.py": shared + 'class A:\n    __tablename__ = "advisories"\n',
            "audit.py": shared
            + "".join(f'class M{i}:\n    __tablename__ = "t{i}"\n' for i in range(4)),
        },
    )
    heavy = _models(
        tmp_path / "heavy",
        {
            "advisory.py": shared
            + "".join(f'class N{i}:\n    __tablename__ = "u{i}"\n' for i in range(4)),
            "audit.py": shared + 'class B:\n    __tablename__ = "audits"\n',
        },
    )

    def keep(code):
        return next(
            f for f in find_duplicate_tablenames(code) if f["table"] == "allowance_state"
        )["keep"]

    assert keep(lean) == keep(heavy), (
        "moving unrelated model classes between the two files changed which one survives"
    )


def test_the_reason_and_the_prohibition_survive(tmp_path):
    """Naming the survivor must not cost the explanation of why it matters."""
    code = _models(
        tmp_path,
        {
            "a.py": 'class X:\n    __tablename__ = "shared"\n',
            "b.py": 'class Y:\n    __tablename__ = "shared"\n',
        },
    )
    detail = find_duplicate_tablenames(code)[0]["detail"]
    assert "InvalidRequestError" in detail
    assert "does not start at all" in detail
    assert "extend_existing=True" in detail


def test_an_intentional_extend_existing_is_still_not_a_finding(tmp_path):
    """The pre-existing escape hatch stays an escape hatch."""
    code = _models(
        tmp_path,
        {
            "a.py": 'class X:\n    __tablename__ = "shared"\n',
            "b.py": (
                'class Y:\n    __tablename__ = "shared"\n'
                "    __table_args__ = {'extend_existing': True}\n"
            ),
        },
    )
    assert find_duplicate_tablenames(code) == []


def test_a_single_declaration_is_never_reported(tmp_path):
    code = _models(tmp_path, {"a.py": 'class X:\n    __tablename__ = "solo"\n'})
    assert find_duplicate_tablenames(code) == []


@pytest.mark.parametrize(
    "table,files,expected",
    [
        # Plural table, singular module.
        ("advisories", ("advisory.py", "misc.py"), "advisory.py"),
        # Compound table, module named for its head word.
        ("watch_locations", ("watch.py", "zzz.py"), "watch.py"),
        # Nothing matches: alphabetical, so at least it is the same answer every time.
        ("pulse_log", ("qqq.py", "aaa.py"), "aaa.py"),
    ],
)
def test_name_matching_handles_plurals_and_compounds(tmp_path, table, files, expected):
    code = _models(
        tmp_path,
        {name: f'class M{i}:\n    __tablename__ = "{table}"\n' for i, name in enumerate(files)},
    )
    assert find_duplicate_tablenames(code)[0]["keep"] == f"backend/app/models/{expected}"
