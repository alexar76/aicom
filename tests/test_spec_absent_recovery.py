"""A product must not be developed against a specification that does not exist.

Regression cover for a failure that cost roughly seventy developer/QA rounds on one
product. Its PM task was *cancelled* — not failed — so the existing recovery path, which
matches on the spec-gate's error text, never fired. The product proceeded to the architect
and then into an endless repair loop, because every gate downstream compares the build to
its spec and there was no spec to compare with:

* spec alignment burned a model call each round to report "spec is empty", then failed the
  build and told the developer the demo "invents a brand not grounded in the spec" — so the
  next round deleted correct product naming to satisfy a phantom document;
* the acceptance-pack gate counted zero scenarios against a minimum of two.

Neither verdict was reachable by editing code. The two behaviours locked in here are that
a gate missing its own input skips instead of blaming the product, and that the absence of
the artifact — rather than a particular error string — is what triggers recovery.
"""

from __future__ import annotations

import pytest

from core.spec_presence import spec_has_substance
from orchestrator.task_queue_hygiene import requeue_pm_when_spec_absent


def _priority(agent_type: str) -> int:
    return 5


def _products(state: str = "ARCH_DESIGNED") -> dict:
    return {
        "prod-x": {
            "id": "prod-x",
            "idea": "A safety companion that warns visitors about local hazards.",
            "state": state,
        }
    }


# --- the predicate -----------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [
        {},
        None,
        "not a dict",
        {"created_at": 1712345678, "delivery_profile": "full_software"},
        {"product_name": "", "description": "   ", "core_features": [], "user_stories": []},
    ],
)
def test_absent_or_bookkeeping_only_specs_have_no_substance(spec):
    assert spec_has_substance(spec) is False


@pytest.mark.parametrize(
    "spec",
    [
        {"product_name": "Sentinel"},
        {"description": "Tells a visitor what is happening near them right now."},
        {"core_features": ["advisory"]},
        {"user_stories": [{"as_a": "visitor"}]},
        {"functional_requirements": ["FR-1"]},
    ],
)
def test_one_populated_substance_field_is_enough(spec):
    """Generous on purpose: judging a thin spec is the quality gate's job, not this one's.

    A stricter bar here would rewind products that have a real-but-slim spec into another
    PM round, which is the same loop this module exists to prevent.
    """
    assert spec_has_substance(spec) is True


# --- the recovery ------------------------------------------------------------------


def test_absent_spec_requeues_pm_and_rewinds_the_product():
    products, queue = _products(), []
    task = requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority, spec_loader=lambda pid: {}
    )
    assert task is not None, "an absent spec must be recovered, not carried forward"
    assert task["agent_type"] == "pm"
    assert task["auto_requeue_reason"] == "spec_artifact_absent"
    assert queue == [task]
    # Rewound, so the pipeline walks forward through spec → architecture again rather than
    # leaving a PM task queued behind a product that still believes it has a design.
    assert products["prod-x"]["state"] == "MARKET_RESEARCHED"
    assert products["prod-x"]["pm_spec_requeue_count"] == 1


def test_a_present_spec_is_left_alone():
    products, queue = _products(), []
    result = requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority,
        spec_loader=lambda pid: {"product_name": "Sentinel", "core_features": ["a", "b"]},
    )
    assert result is None
    assert queue == []
    assert products["prod-x"]["state"] == "ARCH_DESIGNED"
    assert "pm_spec_requeue_count" not in products["prod-x"]


def test_recovery_is_bounded_rather_than_looping(monkeypatch):
    """A spec that cannot be produced must stop the product, not retry forever.

    This is the whole point: the bug being fixed was an unbounded loop, so the fix must
    not introduce a second one.
    """
    monkeypatch.setattr(
        "core.pipeline_retry_limits.pm_spec_auto_requeue_max", lambda: 2, raising=False
    )
    products, queue = _products(), []
    products["prod-x"]["pm_spec_requeue_count"] = 2
    assert requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority, spec_loader=lambda pid: {}
    ) is None
    assert queue == []


def test_does_not_pile_a_second_pm_task_on_a_pending_one():
    products = _products()
    queue = [{"product_id": "prod-x", "agent_type": "pm", "status": "pending"}]
    assert requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority, spec_loader=lambda pid: {}
    ) is None
    assert len(queue) == 1


def test_a_raising_spec_loader_is_treated_as_absent():
    """Recovering on an unreadable spec is right: proceeding blind is the expensive path."""
    def boom(pid):
        raise OSError("permission denied")

    products, queue = _products(), []
    task = requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority, spec_loader=boom
    )
    assert task is not None
    assert task["agent_type"] == "pm"


def test_unknown_product_is_ignored():
    queue = []
    assert requeue_pm_when_spec_absent(
        "prod-missing", _products(), queue, _priority, spec_loader=lambda pid: {}
    ) is None
    assert queue == []


def test_the_recovery_task_tells_pm_what_to_produce():
    """A bare 'try again' would produce the same gap; the ask names the missing fields."""
    products, queue = _products(), []
    task = requeue_pm_when_spec_absent(
        "prod-x", products, queue, _priority, spec_loader=lambda pid: {}
    )
    instructions = task["input_data"]["admin_instructions"]
    for field in ("core_features", "functional_requirements", "user_stories", "acceptance_criteria"):
        assert field in instructions, f"PM is not told to produce {field}"
    assert task["input_data"]["idea"] == products["prod-x"]["idea"]


# --- the gate that must not blame the product ---------------------------------------


@pytest.mark.asyncio
async def test_spec_alignment_gate_skips_when_there_is_no_spec():
    from agents.qa import QAAgent

    agent = QAAgent.__new__(QAAgent)  # no LLM client needed: the gate must return early
    report = {"deep_crawl": {"mode": "deep_crawl", "pages": [{"url": "/", "status": 200}]}}
    result = await QAAgent._browser_e2e_spec_alignment_llm(agent, {}, report)

    assert result["skipped"] is True
    assert result["reason"] == "pipeline_input_missing:specification"
    # Named as upstream work, so the finding is not routed to the developer as code repair.
    assert result["repair_target"] == "spec"


def test_spec_alignment_prompt_does_not_treat_401_as_a_missing_console():
    from pathlib import Path

    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    region = qa[qa.index("You are a senior QA engineer reviewing") : qa.index("Use passed=false if alignment_score")]
    assert "authentication wall" in region
    assert "401/403" in region
    assert "factory preview-serve defect" in region