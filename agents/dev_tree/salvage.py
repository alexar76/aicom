"""Salvage notes: what a reverted round tried, kept for the next round."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from core.json_state import write_text_atomic

# Notes the developer leaves for its OWN next round. There is no channel from this agent back
# onto the product record — it receives `agent_input.data` and returns an AgentOutput — and
# `surrogate_repair_hint` belongs to the round guard, which writes it from the worker. So the
# note goes beside the QA reports the same agent already reads, and is consumed by
# `_load_salvage_notes` when the next repair prompt is assembled.
#
# It exists because a silent revert is an instruction to repeat. Sentinel: 12 days, the right
# file edited over and over, every edit given back for raising the static score by referencing a
# client method that did not exist yet, and each round reporting "0 files" so the repair budget
# was never charged and the loop never reached the limit that would have escalated it.
_SALVAGE_NOTES = "salvage_notes.json"
_MAX_SALVAGE_NOTES = 6


def _salvage_notes_path(code_root: Path, product_id: str) -> Path:
    # Beside the QA reports for this product, not inside the product tree: a note about the
    # product is not part of the product, and anything written into code_root would show up as
    # an untracked file in the very tree the score is measured over.
    return Path(code_root).parent.parent / "bugs" / str(product_id) / _SALVAGE_NOTES


def _record_salvage_notes(
    code_root: Path, product_id: str, introduced: dict, *, log=None
) -> None:
    if not introduced:
        return
    path = _salvage_notes_path(code_root, product_id)
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append({"given_back": {str(k): list(v) for k, v in introduced.items()}})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(existing[-_MAX_SALVAGE_NOTES:], indent=1))
    except OSError as exc:
        if log:
            log("WARNING", f"could not record salvage notes for {product_id}: {exc}")


def _load_salvage_notes(data_root, product_id: str) -> list[str]:
    """Human-readable lines for the prompt, newest last. Empty when nothing was given back."""
    path = Path(data_root) / "bugs" / str(product_id) / _SALVAGE_NOTES
    try:
        notes = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(notes, list):
        return []
    out: list[str] = []
    for entry in notes[-_MAX_SALVAGE_NOTES:]:
        given = (entry or {}).get("given_back") if isinstance(entry, dict) else None
        if not isinstance(given, dict):
            continue
        for rel, defects in given.items():
            what = ", ".join(str(d) for d in (defects or [])) or "no defect this score can name"
            out.append(f"{rel} -> introduced: {what}")
    return out


def _clear_salvage_notes(data_root, product_id: str) -> None:
    """Called when a round LANDS: the dead ends are no longer about the current tree."""
    path = Path(data_root) / "bugs" / str(product_id) / _SALVAGE_NOTES
    with contextlib.suppress(OSError):
        path.unlink()
