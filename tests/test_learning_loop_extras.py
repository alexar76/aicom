"""Tests for the finished learning-loop pieces: L4 apply, claim refine, credit assignment."""

import asyncio
import json
from pathlib import Path

from core.outcome_memory import _extract_root_cause
from core.playbook import distill, llm_refine_enabled, load_rules, refine_playbook_claims
from core.process_bandit import arm_config, assign_build_arm, default_arms
from core.quality_settings import max_pipeline_repair_rounds_for_product


# --- L4 apply: arm assignment + repair-budget override -----------------------

def test_arm_config_presets():
    assert arm_config("light")["max_quality_loops"] == 3
    assert arm_config("heavy")["max_quality_loops"] == 10
    assert arm_config("balanced")["max_quality_loops"] is None


def test_assign_build_arm_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROCESS_BANDIT", raising=False)
    p = {"category": "saas"}
    assert assign_build_arm(tmp_path, p) is None
    assert "config_arm" not in p


def test_assign_build_arm_enabled_tags_and_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROCESS_BANDIT", "1")
    p = {"category": "saas"}
    arm = assign_build_arm(tmp_path, p)
    assert arm in default_arms()
    assert p["config_arm"] == arm
    expected = arm_config(arm)["max_quality_loops"]
    if isinstance(expected, int):
        assert p["max_quality_loops_override"] == expected
    else:
        assert "max_quality_loops_override" not in p


def test_assign_build_arm_idempotent(tmp_path):
    p = {"category": "saas", "config_arm": "heavy"}
    assert assign_build_arm(tmp_path, p) == "heavy"


def test_l4_fields_survive_sqlite_extras_roundtrip():
    # Regression: config_arm + override must be in PRODUCT_EXTRA_KEYS or the L4 loop
    # silently breaks under USE_SQLITE (fields dropped on persist/reload).
    from orchestrator.product_extras import extract_product_extras, merge_product_extras

    product = {"id": "p1", "config_arm": "heavy", "max_quality_loops_override": 10}
    extras = extract_product_extras(product)
    assert extras.get("config_arm") == "heavy"
    assert extras.get("max_quality_loops_override") == 10
    reloaded = merge_product_extras({"id": "p1"}, extras)
    assert reloaded["config_arm"] == "heavy"
    assert reloaded["max_quality_loops_override"] == 10


def test_learning_frozen_survives_sqlite_extras_roundtrip():
    from orchestrator.product_extras import extract_product_extras, merge_product_extras

    product = {"id": "p1", "learning_frozen": True}
    extras = extract_product_extras(product)
    assert extras.get("learning_frozen") is True
    reloaded = merge_product_extras({"id": "p1"}, extras)
    assert reloaded["learning_frozen"] is True


def test_surrogate_decisions_survive_sqlite_extras_roundtrip():
    # Surrogate audit trail accumulates across stages, read at terminal — must persist
    # under USE_SQLITE or outcomes.jsonl loses the AI-gate decisions.
    from orchestrator.product_extras import extract_product_extras, merge_product_extras

    decisions = [{"point": "post_devops_gate", "decision": "approve", "confidence": 0.8}]
    extras = extract_product_extras({"id": "p1", "surrogate_decisions": decisions})
    reloaded = merge_product_extras({"id": "p1"}, extras)
    assert reloaded["surrogate_decisions"] == decisions


def test_l4_reward_fed_back_on_terminal(tmp_path):
    # End-to-end: a build carrying config_arm feeds realized EV to that arm's bandit history.
    from core.outcome_memory import record_terminal_outcome
    from core.process_bandit import arm_stats

    record_terminal_outcome(
        tmp_path,
        {"id": "b1", "state": "COMPLETED", "category": "saas", "config_arm": "heavy"},
    )
    stats = arm_stats(tmp_path, "saas")
    assert stats.get("heavy", {}).get("n") == 1


def test_repair_override_honored_and_capped(monkeypatch):
    monkeypatch.delenv("AIFACTORY_MAX_QUALITY_LOOPS", raising=False)
    assert max_pipeline_repair_rounds_for_product({"max_quality_loops_override": 3}) == 3
    monkeypatch.setenv("AIFACTORY_MAX_QUALITY_LOOPS", "5")
    assert max_pipeline_repair_rounds_for_product({"max_quality_loops_override": 10}) == 5


# --- LLM claim refine (opt-in, deterministic without router) ------------------

class _FakeRouter:
    async def generate(self, *, prompt, task_type=None, config=None):
        return "Always include a 3-tier pricing block."


def _seed_active_rule(data_root: Path):
    eps = [{"category": "saas", "objective": {"shipped": True, "ev": 2.0}, "root_cause": {"signal": ""}} for _ in range(4)]
    eps += [{"category": "saas", "objective": {"shipped": False, "ev": -1.0}, "root_cause": {"signal": "no pricing"}} for _ in range(3)]
    fp = data_root / "state" / "episodes.jsonl"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(json.dumps(e) for e in eps) + "\n", encoding="utf-8")
    distill(data_root)


def test_refine_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PLAYBOOK_LLM_REFINE", raising=False)
    _seed_active_rule(tmp_path)
    assert asyncio.run(refine_playbook_claims(tmp_path, llm_router=_FakeRouter())) == 0
    assert not llm_refine_enabled()


def test_refine_rewrites_claim_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PLAYBOOK_LLM_REFINE", "1")
    _seed_active_rule(tmp_path)
    n = asyncio.run(refine_playbook_claims(tmp_path, llm_router=_FakeRouter()))
    assert n == 1
    rule = next(r for r in load_rules(tmp_path) if r["status"] == "active")
    assert rule["claim"] == "Always include a 3-tier pricing block."
    assert rule["claim_refined"] is True
    # Second pass is a no-op — already-refined rules are not re-spent.
    assert asyncio.run(refine_playbook_claims(tmp_path, llm_router=_FakeRouter())) == 0


# --- Deeper credit assignment ------------------------------------------------

def test_extract_root_cause_from_task_history():
    product = {
        "tasks": [
            {"agent_type": "architect", "status": "completed"},
            {"agent_type": "developer", "status": "failed", "error": "missing pricing block"},
        ],
        "last_gate": "demo_quality",
    }
    rc = _extract_root_cause(product)
    assert rc["stage"] == "developer"
    assert rc["gate"] == "demo_quality"
    assert "pricing" in rc["signal"]
    assert {"stage": "developer", "status": "failed"} in rc["decisions"]


def test_extract_root_cause_fallback_fields():
    rc = _extract_root_cause({"human_review_kind": "qa_repair_exhausted", "human_review_reason": "gates failed"})
    assert rc["stage"] == "qa_repair_exhausted"
    assert rc["signal"] == "gates failed"
