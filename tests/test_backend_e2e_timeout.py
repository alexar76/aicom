"""The backend E2E gate never finished, so it never measured the product.

Every run, without exception:

    e2e subprocess timed out after 60s (web.backend.services.backend_runtime_e2e.run_backend_runtime_e2e)

and the report then carried `backend_runtime_e2e: False` — "boot/probe failed" for an app that had not
finished booting. The gate creates a virtualenv, installs the product's dependencies, starts uvicorn and
probes it; sixty seconds does not cover that on a loaded host. A gate that cannot complete is measuring
its own budget rather than the product, and the round was handed that verdict as though it were a defect.
"""

from __future__ import annotations

import re
from pathlib import Path

QA = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")


def test_the_default_is_three_hundred_seconds():
    assert 'os.environ.get("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC", "300")' in QA
    # And the except-branch fallback must agree with it, or a malformed env var silently restores 60.
    block = QA[QA.index("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC") :][:300]
    assert "backend_timeout = 300.0" in block, block


def test_no_sixty_second_default_remains():
    block = QA[QA.index("Runtime backend E2E") :][:1200]
    assert not re.search(r'BACKEND_E2E_TIMEOUT_SEC", "60"', block)
    assert "backend_timeout = 60.0" not in block


def test_it_stays_overridable():
    """A host that genuinely cannot afford five minutes must be able to say so."""
    assert 'os.environ.get("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC"' in QA


def test_the_reason_is_recorded_next_to_the_number():
    """A bare 300 invites someone to trim it back to a round number later."""
    block = QA[max(0, QA.index("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC") - 700) : QA.index("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC")]
    assert "timed out at sixty seconds" in block or "timed out after 60s" in block
    assert "install the product" in block
