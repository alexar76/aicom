from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state_machine import PipelineStateMachine


@pytest.mark.asyncio
async def test_state_machine_async_wrappers_json(tmp_path: Path):
    state_file = tmp_path / "pipeline.json"
    sm = PipelineStateMachine(state_file=str(state_file), use_sqlite=False)
    product = await sm.acreate_product("test idea", "prod-async-1")
    assert product.id == "prod-async-1"
    sm._create_next_task(product)

    task = await sm.aget_next_task()
    assert task is not None
    ok = await sm.acomplete_task(task.id, {"ok": True})
    assert ok is True
