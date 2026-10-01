"""The AI surrogate's repair hint is produced, persisted, surfaced to the developer,
and a degenerate fill verdict fails closed instead of parking."""

import asyncio

import pytest

from core.surrogate_review import SurrogateVerdict


# --- persistence (R1: it now has a downstream consumer) ----------------------

def test_repair_hint_survives_sqlite_extras_roundtrip():
    from orchestrator.product_extras import extract_product_extras, merge_product_extras

    extras = extract_product_extras({"id": "p1", "surrogate_repair_hint": "add a pricing block"})
    assert merge_product_extras({"id": "p1"}, extras)["surrogate_repair_hint"] == "add a pricing block"


# --- the hint reaches the developer prompt -----------------------------------

def test_remediation_ai_guidance_reaches_developer_brief():
    from llm.agent_prompt_split import build_developer_user_data

    data = build_developer_user_data(
        idea="x", category="saas", tags=[], admin_instructions="",
        architecture={}, specification={}, delivery_mode="web_app",
        delivery_profile="full_software", implementation_plan={}, analyst_brief=None,
        remediation={"ai_reviewer_guidance": "add a 3-tier pricing block"},
    )
    assert data["user_brief"]["remediation"]["ai_reviewer_guidance"] == "add a 3-tier pricing block"


# --- bridge: producer (approve) + fail-safe (fill → block, no dead fields) ----

class _StubReviewer:
    decision = "approve"
    rationale = "add the missing pricing block"

    def __init__(self, data_root, llm_router=None):
        pass

    async def decide(self, point, product, context):
        return SurrogateVerdict(
            point=point, decision=self.decision, confidence=0.9,
            rationale=self.rationale, fill={"k": "v"}, product_id=str(product.get("id") or ""),
        )


def _resolve(tmp_path, monkeypatch, decision, point):
    # Isolate the bridge from mode resolution (which has its own tests and now also
    # gates on auto_pipeline) — we are testing the bridge's routing logic here.
    monkeypatch.setattr("orchestrator.autonomy_bridge.is_full_autonomy", lambda **k: True)
    stub = type("R", (_StubReviewer,), {"decision": decision})
    monkeypatch.setattr("orchestrator.autonomy_bridge.SurrogateReviewer", stub)
    from orchestrator.autonomy_bridge import resolve_human_gate_async

    product = {"id": "p1"}
    state = asyncio.run(resolve_human_gate_async(product, point=point, data_root=tmp_path))
    return state, product


def test_approve_on_qa_exhaust_sets_repair_hint(tmp_path, monkeypatch):
    state, product = _resolve(tmp_path, monkeypatch, "approve", "qa_repair_exhausted")
    assert state == "BUG_FOUND"
    assert product["surrogate_repair_hint"] == "add the missing pricing block"
    assert product["quality_repair_round"] == 0


def test_fill_verdict_fails_closed_not_parked(tmp_path, monkeypatch):
    state, product = _resolve(tmp_path, monkeypatch, "fill", "qa_repair_exhausted")
    # Degenerate fill at an approve/block gate must resolve (fail closed), never None.
    assert state == "FAILED"
    # Dead fields are gone.
    assert "surrogate_fill" not in product
    assert "owner_feedback_synthetic" not in product


def test_block_routes_to_failed_on_post_devops(tmp_path, monkeypatch):
    state, _ = _resolve(tmp_path, monkeypatch, "block", "post_devops_gate")
    assert state == "FAILED"
