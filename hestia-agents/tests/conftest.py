"""Reach the sibling HESTIA sources when this package sits in the monorepo.

The admission tests want the real `hestia.scan.admit_handler` — asserting that a
handler passes a copy of the rules would prove nothing. Standalone checkouts do
not have the sibling, so those tests skip rather than fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MONOREPO_HESTIA = Path(__file__).resolve().parent.parent.parent / "hestia"

if MONOREPO_HESTIA.is_dir() and str(MONOREPO_HESTIA) not in sys.path:
    sys.path.insert(0, str(MONOREPO_HESTIA))


def admit_handler_or_skip():
    try:
        from hestia.scan import admit_handler
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources are not on the path")
    return admit_handler


@pytest.fixture
def admit():
    return admit_handler_or_skip()
