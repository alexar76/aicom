from __future__ import annotations

from typing import Any

from relay_scout.models import DiffResult, Snapshot


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(val, dict):
                out.update(_flatten(val, path))
            else:
                out[path] = val
    return out


def compute_diff(previous: Snapshot | None, current: Snapshot) -> DiffResult:
    if previous is None or previous.response_json is None or current.response_json is None:
        return DiffResult(summary="no baseline")
    prev = _flatten(previous.response_json)
    curr = _flatten(current.response_json)
    added = sorted(set(curr) - set(prev))
    removed = sorted(set(prev) - set(curr))
    changed = sorted(k for k in set(prev) & set(curr) if prev[k] != curr[k])
    summary = f"+{len(added)} -{len(removed)} ~{len(changed)}"
    return DiffResult(
        added_fields=added,
        removed_fields=removed,
        changed_fields=changed,
        summary=summary,
    )
