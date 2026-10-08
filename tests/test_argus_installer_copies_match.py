"""The curl|bash installer people run is a COPY of scripts/install_argus.sh.

The 2026-09-06 fix (one npm name, not a preference list over registry names) went into
scripts/install_argus.sh only; ecosystem-landing/install — the file actually served at
https://modeldev.modelmarket.dev/install — kept the old list for a month. Every served
copy must be byte-identical to the source.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "install_argus.sh"


@pytest.mark.parametrize("served", ["ecosystem-landing/install", "ecosystem-landing/argus/install"])
def test_served_installer_is_the_source(served):
    assert (ROOT / served).read_bytes() == SOURCE.read_bytes(), (
        f"{served} drifted from scripts/install_argus.sh — copy the source over it"
    )


def test_the_installer_names_one_package():
    text = SOURCE.read_text(encoding="utf-8")
    assert "for candidate in" not in text
