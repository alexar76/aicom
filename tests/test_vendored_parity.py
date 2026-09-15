"""Vendored copies must not drift from their canonical source.

A satellite that ships as its own repository cannot import from a sibling satellite's folder, and the
sibling is not a published package — so a few files are copied verbatim, with a parity test to keep the
copy honest. `alien-monitor/backend/chain_net.py` is one of those copies.

**Why this file lives in `tests/` rather than next to the copy.** There WAS a parity test, at
`alien-monitor/tests/test_chain_net_parity.py`, and it never ran: the root `pytest.ini` sets
`testpaths = tests`, so CI collects `tests/` and nothing else. The copy drifted a whole feature behind
(the canonical module had moved to loading contract addresses from
`config/deployments/base-mainnet.json`, the copy still held a hardcoded dict) and nobody found out
until a full-suite run months later.

So the guard is placed where CI already looks. A check that depends on somebody remembering to widen a
test path is not a check. The satellite-local test stays as well — it is the one that runs inside the
satellite's own repository CI, where the canonical file is absent and it correctly skips.

Adding a vendored copy? Add the pair to VENDORED and nothing else needs to change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# (vendored copy, canonical source, why the copy exists)
VENDORED: tuple[tuple[str, str, str], ...] = (
    (
        "alien-monitor/backend/chain_net.py",
        "aimarket-hub/aimarket_hub/chain_net.py",
        "alien-monitor publishes as its own repository and cannot see aimarket-hub/; the hub is not "
        "a published package, so it cannot be a dependency either",
    ),
)


@pytest.mark.parametrize("copy_rel,canonical_rel,reason", VENDORED,
                         ids=[c.split("/")[-1] for c, _, _ in VENDORED])
def test_vendored_copy_matches_canonical(copy_rel: str, canonical_rel: str, reason: str) -> None:
    copy_path, canonical_path = ROOT / copy_rel, ROOT / canonical_rel
    assert copy_path.is_file(), f"vendored copy missing: {copy_rel}"
    if not canonical_path.is_file():
        # A trimmed checkout (a satellite mirror) legitimately has no canonical file. Skipping there is
        # correct; skipping in the monorepo would defeat the whole point, so say which case this is.
        pytest.skip(f"canonical source absent — trimmed checkout, not the monorepo ({canonical_rel})")

    copied = copy_path.read_text(encoding="utf-8")
    canonical = canonical_path.read_text(encoding="utf-8")
    assert copied == canonical, (
        f"{copy_rel} has drifted from {canonical_rel}.\n"
        f"  The copy exists because: {reason}\n"
        f"  Re-vendor with:  cp {canonical_rel} {copy_rel}\n"
        f"  Then check the copy's own tests still pass — the canonical version may have gained "
        f"behaviour the copy's host does not expect."
    )


def test_every_vendored_pair_is_justified() -> None:
    """A copy without a stated reason is a copy nobody will dare delete."""
    for copy_rel, canonical_rel, reason in VENDORED:
        assert len(reason) > 40, f"{copy_rel} is vendored without a real justification"
        assert copy_rel != canonical_rel


def test_the_satellite_local_test_still_exists() -> None:
    """The satellite's own copy of this check must survive: it is what runs inside that satellite's
    repository CI, where the canonical file is absent. Deleting it as 'redundant' would remove the only
    check that runs in the place the copy actually ships from."""
    local = ROOT / "alien-monitor" / "tests" / "test_chain_net_parity.py"
    assert local.is_file(), (
        "alien-monitor/tests/test_chain_net_parity.py is gone — this root test does not replace it, "
        "it complements it (this one runs in monorepo CI, that one in the satellite's own CI)")
