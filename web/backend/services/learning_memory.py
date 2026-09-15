"""
Learning memory
===============
Persists compact lessons from pipeline execution and exposes recent history
to improve future products with cross-product context.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def _memory_file(data_root: str) -> Path:
    p = Path(data_root) / "state" / "learning_memory.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_lesson(data_root: str, lesson: dict) -> None:
    row = {"created_at": time.time(), **(lesson or {})}
    p = _memory_file(data_root)
    max_bytes = int(os.environ.get("AIFACTORY_LEARNING_MEMORY_MAX_BYTES", str(2 * 1024 * 1024)))
    retention_sec = int(os.environ.get("AIFACTORY_LEARNING_MEMORY_RETENTION_SEC", str(30 * 24 * 3600)))
    dedup_window = int(os.environ.get("AIFACTORY_LEARNING_MEMORY_DEDUP_WINDOW", "200"))
    _compact_memory_file(p, max_bytes=max_bytes, retention_sec=retention_sec, dedup_window=dedup_window)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_recent_lessons(data_root: str, limit: int = 15) -> list[dict]:
    p = _memory_file(data_root)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
        if len(out) >= max(1, int(limit)):
            break
    return out


def _row_hash(row: dict) -> str:
    key = f"{row.get('product_id','')}|{row.get('agent_type','')}|{row.get('target_state','')}|{row.get('summary','')}"
    return hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()


def _compact_memory_file(p: Path, *, max_bytes: int, retention_sec: int, dedup_window: int) -> None:
    if not p.exists():
        return
    now = time.time()
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict] = []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        created = float(row.get("created_at") or 0)
        if created <= 0 or (now - created) > retention_sec:
            continue
        rows.append(row)
    # Deduplicate recent window by semantic hash, keep latest entries.
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in reversed(rows[-max(1, dedup_window):]):
        h = _row_hash(row)
        if h in seen:
            continue
        seen.add(h)
        deduped.append(row)
    deduped.reverse()
    older = rows[:-max(1, dedup_window)]
    merged = older + deduped
    blob = "\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + ("\n" if merged else "")
    # Size-based rotation/trim: keep newest tail that fits.
    if len(blob.encode("utf-8")) > max_bytes:
        keep: list[dict] = []
        size = 0
        for row in reversed(merged):
            line = json.dumps(row, ensure_ascii=False) + "\n"
            b = len(line.encode("utf-8"))
            if size + b > max_bytes and keep:
                break
            keep.append(row)
            size += b
        keep.reverse()
        blob = "\n".join(json.dumps(r, ensure_ascii=False) for r in keep) + ("\n" if keep else "")
    p.write_text(blob, encoding="utf-8")
