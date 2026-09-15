"""An outage is not a quality problem, and it must not spend the quality budget.

Measured on a live run. The provider began answering `402 Payment Required` at 01:05:52; it did so 114
times in the following hour. Every developer round came back with `Code generation complete: 0 files`,
and the repair counter still climbed from 33 to 58 — twenty-five rounds of budget consumed by an empty
wallet. The budget exists to stop a product looping forever on defects it cannot fix, which is a
statement about the product; a provider that will not answer says nothing about the product at all.

Left unfixed, the shape of the failure is the worst kind: the product parks at HUMAN_REVIEW_PENDING
with its budget spent and its tree untouched, and the log says "repair limit reached" — which reads as
"the factory tried forty times and could not do it".
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.task_executor_agent import _round_produced_output


class _Output:
    def __init__(self, data):
        self.data = data


def test_a_round_that_generated_nothing_is_not_productive():
    """`0 files` is the signature of a 402, a timeout or a refusal."""
    assert _round_produced_output({}, _Output({"file_count": 0, "files": []})) is False
    assert _round_produced_output({}, _Output({"files_created": 0})) is False
    assert _round_produced_output({}, _Output({})) is False
    assert _round_produced_output({}, _Output(None)) is False


def test_a_round_that_wrote_files_is_productive():
    assert _round_produced_output({}, _Output({"file_count": 3})) is True
    assert _round_produced_output({}, _Output({"files_created": 1})) is True
    assert _round_produced_output({}, _Output({"files": [{"path": "a.py"}]})) is True


def test_the_helper_answers_only_about_a_developer_round():
    """It used to say a QA output was "productive", which is what defeated the guard.

    The question is "did the developer write anything", and a QA output cannot answer it. Making the
    helper return True for one was an attempt to be safe that removed the only case it existed for:
    the budget decision is taken on the QA output, so the helper was asked exactly the wrong thing and
    always said yes. It now answers false for anything without files, and the call site reads a flag
    the developer wrote instead.
    """
    assert _round_produced_output({}, _Output({"qa_result": {}, "bug_count": 20})) is False


def test_the_executor_leaves_the_counter_alone_and_says_so():
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    region = src[src.index("new_repair_round = 0") :][:1800]
    assert '_generation_happened = bool(products[pid].get("last_round_generated", True))' in region
    assert "Repair budget not charged" in region, (
        "a silently uncharged round is indistinguishable from a counter bug"
    )
    # The increment must be the else-branch, not the default.
    assert region.index("if not _generation_happened:") < region.index(
        'products[pid]["quality_repair_round"] = new_repair_round'
    )


def test_the_flag_is_written_by_the_developer_and_read_by_the_budget():
    """The first version asked the QA output whether the developer had generated anything.

    A QA result always carries findings, so the helper answered "productive" every time, the guard
    never fired, and the counter climbed from 33 to 60 through the outage exactly as before. The test
    passed because it exercised the helper with a hypothetical developer output, never with what the
    call site actually receives.
    """
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    assert 'if agent_type == "developer" and pid in products:' in src
    assert 'products[pid]["last_round_generated"] = _round_produced_output(' in src
    assert '_generation_happened = bool(products[pid].get("last_round_generated", True))' in src
    # Written before read, in the same handler.
    assert src.index('products[pid]["last_round_generated"] =') < src.index("_generation_happened =")
    # And the helper no longer pretends a QA output can answer the question.
    helper = src[src.index("def _round_produced_output(") : src.index("def _refresh_static_findings")]
    assert "qa_result" not in helper, "the helper still treats a QA output as a productive round"


def test_the_flag_survives_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_round_generated" in PRODUCT_EXTRA_KEYS


def test_an_unknown_history_charges_the_round():
    """Defaulting to True keeps the budget meaningful when the flag has never been written."""
    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    ).read_text(encoding="utf-8")
    assert '.get("last_round_generated", True)' in src
