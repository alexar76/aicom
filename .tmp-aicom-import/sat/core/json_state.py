"""Crash-safe JSON state writes.

``open(path, "w")`` truncates first and writes second: a process killed between the two —
OOM, a container recreate, a full disk — leaves a zero-byte file where the state used to be.
Found on the factory host on 2026-09-11: ``data/state/pending_payments.json`` was 0 bytes and
every restart logged "Could not load pending payments file". The same pattern guarded nothing
in ``data/config/admin.json``, whose loss would take the admin's TOTP/WebAuthn registration
with it.

Write through a sibling temp file and ``os.replace`` it into place instead: the rename is
atomic, so a reader sees either the old file or the new one, never a truncated one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: str | Path, data: Any, *, indent: int | None = 2, mode: int | None = None) -> None:
    """Serialise ``data`` to ``path`` atomically, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The temp file is a sibling so the replace stays on one filesystem, and carries the pid so
    # two writers cannot clobber each other's half-written file.
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # the rename is atomic; the bytes still have to reach the disk
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
