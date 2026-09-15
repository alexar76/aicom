"""Filters for LLM QA findings that burn repair budget without blocking ship gates."""

from __future__ import annotations

from typing import Any


def is_test_hygiene_llm_finding(bug: dict[str, Any] | Any) -> bool:
    """True for LLM opinions about pytest / test files that never ship.

    Measured on Relay: rounds 30–42 spent Dev capacity rewriting
    ``backend/tests/conftest.py`` (SESSION_SECRET, mkdtemp, shared SQLite,
    rate-limit monkeypatches) while demo score was already A and backend E2E
    was green. Those findings are test-harness taste, not product defects, and
    they do not fail a measured gate. Dropping every LLM finding whose file
    lives under ``tests/`` / ``conftest`` stops the immortal repair loop.
    """
    if not isinstance(bug, dict):
        return False
    path = str(bug.get("file") or "").replace("\\", "/").lower()
    title = f"{bug.get('title') or ''} {bug.get('description') or ''}".lower()
    in_tests = (
        "/tests/" in path
        or "/test/" in path
        or path.endswith("conftest.py")
        or "/conftest.py" in path
        or "conftest.py" in title
        or path.endswith("_test.py")
        or path.endswith(".test.ts")
        or path.endswith(".test.tsx")
        or "/integration/test_" in path
    )
    if not in_tests:
        # Titles that only name pytest fixtures without a product file still burn rounds.
        if "conftest" in title or ("pytest" in title and "session_secret" in title):
            return True
        return False
    return True
