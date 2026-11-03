"""How many rows one request may read.

A list endpoint clamps the caller's ``limit`` into ``1..maximum``: one request can neither
ask the database for an unbounded scan nor receive an unbounded response, and a limit of
zero or less still returns one row instead of an error. Where a missing limit has a page
size of its own, ``default`` stands in for it.
"""

from __future__ import annotations

from typing import Any


def page_limit(value: Any, *, maximum: int, default: int | None = None) -> int:
    """``value`` as a row count in ``1..maximum``; a falsy value means ``default`` when one is given."""
    rows = int(value or default) if default is not None else int(value)
    return max(1, min(rows, maximum))
