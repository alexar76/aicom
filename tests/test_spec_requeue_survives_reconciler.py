"""A rewind the reconciler undoes is not a rewind.

An adversarial review of the spec-absent recovery traced this mechanically, and it is the
worst kind of bug: the checkpoint added to stop a product entering development without a
specification was itself the path into that state.

The chain, all inside one worker cycle:

1. the recovery rewinds the product to ``MARKET_RESEARCHED`` and queues a PM task targeting
   ``SPEC_WRITTEN``; ``append_product_task`` cancels the running architect row;
2. the call site wrote that architect row back to ``completed``;
3. Phase 6b re-derives product state from task rows. ``completed`` rows count, only
   ``cancelled``/``blocked`` are skipped, and ``ARCH_DESIGNED`` (rank 5) outranks
   ``MARKET_RESEARCHED`` (rank 1) — so the product is put back and persisted;
4. the PM task is now three ranks behind the product, so queue hygiene cancels it as
   regressive (or archives it as superseded if PM fails), and Phase 4c heals the product
   forward: design_critic, then developer;
5. the product develops with no specification, and ``pm_spec_requeue_count`` has already
   been spent, so the remaining budget can never be used — the architecture checkpoint is
   never revisited.

Two things now prevent it: the call site leaves the superseded row cancelled, and the
requeue retires any completed row claiming a state at or past the spec stage. Both are
asserted here against the *real* reconciler and the *real* hygiene predicates rather than a
model of them, because the bug lived entirely in the interaction between them.
"""

from __future__ import annotations

import pytest

from orchestrator.pipeline_state_sync import infer_product_state_from_tasks
from orchestrator.task_queue_hygiene import (
    is_regressive_task,
    is_superseded_failed_task,
    requeue_pm_bounded,
)


def _priority(agent_type: str) -> int:
    return 5


@pytest.fixture()
def scene():
    """A product at the architecture checkpoint with the rows that cycle would hold."""
    products = {
        "prod-x": {"id": "prod-x", "idea": "A safety companion.", "state": "ARCH_DESIGNED"}
    }
    queue = [
        {
            "id": "task-arch",
            "product_id": "prod-x",
            "agent_type": "architect",
            "state": "ARCH_DESIGNED",
            "status": "completed",
        }
    ]
    return products, queue


def _reconciled(queue: list[dict]) -> str:
    """What the worker's Phase 6b would derive for prod-x from these rows."""
    rows = [t for t in queue if t.get("product_id") == "prod-x"]
    return infer_product_state_from_tasks(rows)

def _requeue(products, queue):
    return requeue_pm_bounded(
        "prod-x", products, queue, _priority,
        reason="spec_artifact_absent",
        instructions="Write the full specification JSON now.",
    )


def test_the_reconciler_agrees_with_the_rewind(scene):
    """The property that failed: re-deriving state must not undo the send-back."""
    products, queue = scene
    task = _requeue(products, queue)
    assert task is not None

    inferred = _reconciled(queue)
    assert inferred != "ARCH_DESIGNED", (
        "the reconciler still infers the state the product was rewound from, so the rewind "
        "will be reverted in the same cycle"
    )


def test_rows_claiming_a_later_stage_are_retired(scene):
    products, queue = scene
    _requeue(products, queue)
    arch = next(t for t in queue if t["id"] == "task-arch")
    assert arch["status"] == "cancelled"
    assert "superseded by a spec re-run" in arch["error"]


def test_the_requeued_task_is_not_regressive_against_the_reconciled_state(scene):
    """What actually killed the recovery: hygiene cancelled the PM task it had just queued."""
    products, queue = scene
    task = _requeue(products, queue)

    reconciled = _reconciled(queue)
    assert not is_regressive_task(reconciled, task), (
        f"the PM task is regressive against {reconciled} and would be cancelled by hygiene"
    )


def test_a_failed_recovery_task_is_not_archived_as_superseded(scene):
    """PM failing is ordinary — a transient LLM error must not end the recovery silently."""
    products, queue = scene
    task = _requeue(products, queue)

    reconciled = _reconciled(queue)
    failed = {**task, "status": "failed", "error": "LLM returned non-JSON"}
    assert not is_superseded_failed_task(failed, {**products["prod-x"], "state": reconciled}), (
        "a failed recovery task is classified as historical noise and cancelled instead of "
        "retried, so the product never gets its spec"
    )


def test_the_new_task_itself_is_never_retired(scene):
    """The retirement sweep must not cancel the task it was called to queue."""
    products, queue = scene
    task = _requeue(products, queue)
    assert task["status"] == "pending"


def test_rows_before_the_spec_stage_are_left_alone(scene):
    """Only claims the product no longer holds are retired — history stays readable."""
    products, queue = scene
    queue.append(
        {
            "id": "task-analyst",
            "product_id": "prod-x",
            "agent_type": "analyst",
            "state": "MARKET_RESEARCHED",
            "status": "completed",
        }
    )
    _requeue(products, queue)
    analyst = next(t for t in queue if t["id"] == "task-analyst")
    assert analyst["status"] == "completed"


def test_another_products_rows_are_untouched(scene):
    products, queue = scene
    products["prod-other"] = {"id": "prod-other", "idea": "Other.", "state": "ARCH_DESIGNED"}
    queue.append(
        {
            "id": "task-other-arch",
            "product_id": "prod-other",
            "agent_type": "architect",
            "state": "ARCH_DESIGNED",
            "status": "completed",
        }
    )
    _requeue(products, queue)
    other = next(t for t in queue if t["id"] == "task-other-arch")
    assert other["status"] == "completed"
    assert products["prod-other"]["state"] == "ARCH_DESIGNED"


def test_repair_rounds_reset_when_the_spec_is_rewritten(scene):
    """Rounds spent under the old spec must not terminalize the product under the new one.

    The product that exposed this had burned 12 quality repair rounds against gates that
    could not pass — the spec was absent, so nothing could satisfy them — while the cap for
    its profile is 10. Its next QA failure would have marked it FAILED for rounds it never
    had a fair chance to use, and the defect list those rounds produced described a build
    made from a different brief.
    """
    products, queue = scene
    products["prod-x"]["quality_repair_round"] = 12
    assert _requeue(products, queue) is not None
    assert products["prod-x"]["quality_repair_round"] == 0


def test_a_refused_requeue_leaves_the_repair_count_alone(scene, monkeypatch):
    """Half-applied recovery is worse than none: a decline must restore what it touched."""
    monkeypatch.setattr(
        "core.pipeline_retry_limits.pm_spec_auto_requeue_max", lambda: 1, raising=False
    )
    products, queue = scene
    products["prod-x"]["quality_repair_round"] = 7
    products["prod-x"]["pm_spec_requeue_count"] = 1  # at the cap, so the requeue declines
    assert _requeue(products, queue) is None
    assert products["prod-x"]["quality_repair_round"] == 7
    assert products["prod-x"]["state"] == "ARCH_DESIGNED"
