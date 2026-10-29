"""Redact sensitive fields before sending fleet context to external LLMs."""

from __future__ import annotations

import os
from typing import Any

_SNAPSHOT_SENSITIVE_KEYS = (
    "failed_logins",
    "recent_logins",
    "raw_sections",
)


def llm_include_auth_logs() -> bool:
    return os.environ.get("SKOPOS_LLM_INCLUDE_AUTH_LOGS", "").lower() in ("1", "true", "yes")


def sanitize_snapshot_dict(data: dict[str, Any]) -> dict[str, Any]:
    if llm_include_auth_logs():
        return dict(data)
    out = dict(data)
    for key in _SNAPSHOT_SENSITIVE_KEYS:
        out.pop(key, None)
    return out
