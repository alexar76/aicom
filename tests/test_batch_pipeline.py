from __future__ import annotations

from orchestrator.batch_pipeline import drain_batch_queue_into_state, enqueue_batch_items, summarize_batch


def test_batch_queue_drain_respects_limits(tmp_path):
    from pathlib import Path

    queue_path = Path(tmp_path) / "batch_pipeline_queue.json"
    enqueue_batch_items(
        [
            {"id": "q1", "batch_id": "b1", "idea": "Idea one long enough", "status": "queued"},
            {"id": "q2", "batch_id": "b1", "idea": "Idea two long enough", "status": "queued"},
        ],
        path=queue_path,
    )
    state = {"products": {}, "task_queue": []}
    out = drain_batch_queue_into_state(state=state, max_to_start=1, active_limit=10, path=queue_path)
    assert out["started"] == 1
    assert len(state["products"]) == 1
    summary = summarize_batch("b1", path=queue_path)
    assert summary["status_counts"].get("created", 0) == 1
