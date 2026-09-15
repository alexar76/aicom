"""A product's admin_instructions is its order, and must survive repair rounds.

A wallet-binding requirement added to a live product disappeared on the next
reopen, because the reopen wrote its own base+note merge back over the charter.
"""

import re
from pathlib import Path

SOURCE = Path("web/backend/services/pipeline_reopen.py").read_text(encoding="utf-8")


def test_reopen_never_writes_merged_instructions_back_to_the_product():
    assert 'product["admin_instructions"] =' not in SOURCE, (
        "the charter must not be overwritten from a task's merged prompt"
    )


def test_the_task_still_receives_the_merged_instructions():
    """The merge is what the agent should read; it just does not become the charter."""
    assert 'input_data: dict[str, Any] = {' in SOURCE
    assert '"admin_instructions": merged_instructions' in SOURCE


def test_the_reason_is_recorded_next_to_the_code():
    assert "engineering charter" in SOURCE
