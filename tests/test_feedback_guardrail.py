import json
import time
from pathlib import Path

from web.backend.services.feedback_guardrail import apply_feedback_guardrail


def test_feedback_guardrail_enqueues_pm_for_shipped_product(tmp_path: Path, monkeypatch):
    now = time.time()
    fb_dir = Path("/app/data/feedback")
    fb_dir.mkdir(parents=True, exist_ok=True)
    # Seed enough negative journey + bug signals
    for i in range(3):
        row = {
            "id": f"fb-{i}",
            "product_id": "prod-abc",
            "rating": 1,
            "comment": "did not work",
            "classification": "bug",
            "tags": ["journey_prompt", "no"],
            "created_at": now - 60,
        }
        (fb_dir / f"fb-test-guardrail-{i}.json").write_text(json.dumps(row), encoding="utf-8")

    products = {"prod-abc": {"id": "prod-abc", "idea": "x", "state": "COMPLETED"}}
    task_queue = []
    changed = apply_feedback_guardrail(products, task_queue, now)
    assert changed is True
    assert products["prod-abc"]["state"] == "MARKET_RESEARCHED"
    assert any(t.get("agent_type") == "pm" and t.get("product_id") == "prod-abc" for t in task_queue)

