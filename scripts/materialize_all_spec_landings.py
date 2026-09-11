#!/usr/bin/env python3
"""Materialize spec-built sandbox pages for every product with factory boilerplate index.html."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.paths import code_dir, data_root

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    root = data_root() / "code"
    if not root.is_dir():
        logger.info("No code dir at %s — skip", root)
        return 0

    from web.backend.services.sandbox_spec_landing import materialize_spec_landing_on_disk

    updated = 0
    skipped = 0
    for product_dir in sorted(root.iterdir()):
        if not product_dir.is_dir():
            continue
        pid = product_dir.name
        if not (product_dir / "index.html").is_file():
            skipped += 1
            continue
        try:
            if materialize_spec_landing_on_disk(pid, code_root=code_dir(pid)):
                updated += 1
                logger.info("materialized %s", pid)
        except Exception as exc:
            logger.warning("materialize failed %s: %s", pid, exc)

    logger.info("Done: %d updated, %d skipped (no index)", updated, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
