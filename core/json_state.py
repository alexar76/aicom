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

import contextlib
import errno
import json
import os
import shutil
import stat
import threading
import uuid
from pathlib import Path
from typing import Any


def write_text_atomic(path: str | Path, text: str, *, mode: int | None = None, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically, creating parent directories.

    Without ``mode`` a file that already exists keeps its permission bits — ``open(p, "w")``
    never changed them, and a 0600 secrets file must not come back 0644 from a rename.
    A single-file bind mount uses an in-place fallback because it cannot be replaced;
    that fallback does not provide the atomicity of a normal directory-backed file.
    """
    target = Path(path)
    if target.is_symlink():
        # ``open(p, "w")`` wrote through the link; replacing the link itself would orphan its target.
        target = Path(os.path.realpath(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        with contextlib.suppress(FileNotFoundError):
            mode = stat.S_IMODE(target.stat().st_mode)
    # A sibling, so the replace stays on one filesystem; unique per call ("x" refuses an
    # existing name), so two writers — processes or threads — never share a half-written file.
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        # Set permissions at creation, before any secret bytes reach the temp file.
        def opener(name: str, flags: int) -> int:
            return os.open(name, flags, mode if mode is not None else 0o666)

        with open(tmp, "x", encoding=encoding, opener=opener) as f:
            if mode is not None:
                os.fchmod(f.fileno(), mode)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())  # the rename is atomic; the bytes still have to reach the disk
        try:
            os.replace(tmp, target)
        except OSError as exc:
            if exc.errno != errno.EBUSY:
                raise
            # A single-file bind mount cannot be renamed over. Write in place, as before.
            if mode is not None:
                os.chmod(target, mode)
            shutil.copyfile(tmp, target)
            tmp.unlink()
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def write_json_atomic(
    path: str | Path,
    data: Any,
    *,
    indent: int | None = 2,
    mode: int | None = None,
    ensure_ascii: bool = False,
    **dumps_kwargs: Any,
) -> None:
    """Serialise ``data`` to ``path`` atomically, creating parent directories.

    Extra keyword arguments (``default``, ``sort_keys``, ``separators``) go to ``json.dumps``.
    """
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, **dumps_kwargs)
    write_text_atomic(path, text, mode=mode)
