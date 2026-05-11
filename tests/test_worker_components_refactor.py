from orchestrator.worker_components import PeerReviewEngine, TaskOrchestrator


def _priority(agent: str) -> int:
    return {"hardening": 4, "design_critic": 5}.get(agent, 5)


def test_enqueue_refactor_sprint_creates_hardening_task(monkeypatch):
    monkeypatch.setenv("AIFACTORY_REFACTOR_INTERVAL_SEC", "1")
    orch = TaskOrchestrator(_priority)
    products = {"prod-1": {"id": "prod-1", "state": "COMPLETED", "idea": "x", "last_refactor_sprint_at": 0}}
    queue = []
    changed = orch.enqueue_refactor_sprint(products, queue, now=100)
    assert changed is True
    assert any(t.get("agent_type") == "hardening" for t in queue)


def test_design_critic_block_loops_back_to_architect():
    engine = PeerReviewEngine(_priority)
    product_state = {
        "peer_reviews": {
            "design_critic": {"recommended": "block", "blockers": ["contrast"], "notes": "fix CTA contrast"}
        }
    }
    queue = []
    task = {"product_id": "prod-1", "agent_type": "design_critic"}
    product_row = {"idea": "x"}
    blocked = engine.apply_block(task, product_state, queue, product_row)
    assert blocked is True
    assert any(t.get("agent_type") == "architect" for t in queue)


def test_design_critic_force_proceed_after_max_iterations(monkeypatch):
    monkeypatch.setenv("AIFACTORY_DESIGN_REVIEW_MAX_ITERS", "2")
    engine = PeerReviewEngine(_priority)
    product_state = {
        "design_review_iterations": 2,
        "peer_reviews": {
            "design_critic": {"recommended": "block", "blockers": ["missing contracts"], "notes": "iterate"}
        },
    }
    queue = []
    blocked = engine.apply_block({"product_id": "prod-1", "agent_type": "design_critic"}, product_state, queue, {"idea": "x"})
    assert blocked is False
    assert queue == []
    assert "design_review_forced_proceed" in product_state
