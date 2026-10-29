"""Crash-safe file writes.

``open(path, "w")`` truncates first and writes second, so a process killed in between leaves
an empty or half-written state file. Write a sibling temp file, fsync it and rename it into
place instead: a reader sees the old file or the new one, never a torn one.
"""

from __future__ import annotations

import contextlib
import os
import stat
import threading
import uuid
from pathlib import Path


def write_text_atomic(path: str | Path, text: str, *, mode: int | None = None, encoding: str = "utf-8") -> None:
    """Replace ``path`` with ``text`` in one rename. An existing file keeps its permission bits."""
    target = Path(path)
    if target.is_symlink():
        target = Path(os.path.realpath(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        with contextlib.suppress(FileNotFoundError):
            mode = stat.S_IMODE(target.stat().st_mode)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "x", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
