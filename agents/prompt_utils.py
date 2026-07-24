"""
Helpers for assembling agent prompts cheaply.

The key cost lever here is ``prompt_json``: artifacts (spec, architecture,
market research, telemetry, code samples) are serialized straight into agent
prompts. Pretty-printing them with ``indent=2`` adds pure whitespace tokens with
zero signal for the model — for large artifacts that is a 10-20% input-token
tax on every call. ``prompt_json`` emits the same content with compact
separators so the model sees the data, not the indentation.

Use ``indent=2`` only for JSON written to disk / shown to humans; use
``prompt_json`` for anything that goes into an LLM prompt.
"""

from __future__ import annotations

import json
from typing import Any

# Compact separators — no space after ',' or ':'. Same content, fewer tokens.
_COMPACT_SEPARATORS = (",", ":")


def prompt_json(obj: Any, *, limit: int | None = None) -> str:
    """Serialize ``obj`` compactly for embedding in an LLM prompt.

    Args:
        obj: Any JSON-serializable value.
        limit: Optional max character length; the result is truncated with an
            explicit marker so the model knows the artifact was clipped.

    Compared with ``json.dumps(obj, indent=2)`` this drops indentation and the
    spaces after separators (~10-20% fewer tokens on large artifacts) while
    keeping non-ASCII characters intact (``ensure_ascii=False``).
    """
    text = json.dumps(obj, ensure_ascii=False, separators=_COMPACT_SEPARATORS)
    if limit is not None and limit > 0 and len(text) > limit:
        return text[:limit] + "\n…[truncated]"
    return text
