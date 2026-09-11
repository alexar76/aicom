"""Probe whether the non-root app can write a product code tree.

The ``app`` container drops ``CAP_CHOWN``. Ownership repair is the ``data-keep``
sidecar in ``docker-compose.yml`` (root alpine on the bind mount). This module
only detects and logs: a laptop rsync as uid 501/root otherwise shows up as
mysterious developer ``PermissionError`` on README/docs, not as an ownership bug.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.paths import code_dir

logger = logging.getLogger(__name__)


def product_code_dir_writable(product_id: str, *, root: Path | None = None) -> bool:
    """True when the process can create a file at the product code root."""
    pid = str(product_id or "").strip()
    if not pid:
        return True
    path = root if root is not None else code_dir(pid)
    if not path.is_dir():
        return True
    probe = path / ".aicom_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def warn_if_product_code_unwritable(product_id: str) -> bool:
    """Log when the tree is not writable. Returns True when writable (or missing)."""
    pid = str(product_id or "").strip()
    if not pid:
        return True
    if product_code_dir_writable(pid):
        return True
    logger.error(
        "Product code tree is not writable by the app user (uid 501/root rsync?): "
        "%s — data-keep should chown /data/code to 10001; until then developer/QA "
        "cannot patch GitHub-house files.",
        pid,
    )
    return False
