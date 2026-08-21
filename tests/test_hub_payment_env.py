"""A satellite missing from AIMARKET_SELLS_FOR is given away, silently.

The hub is only the seller of record for peers it is explicitly told about
(`HubConfig.sells_on_behalf_of`). A federated capability whose peer is not declared keeps
working perfectly and simply stops being paid for: it answers 200 unpaid while still
advertising a price. There is no error, no log line, and no metric that moves.

That is not hypothetical. Forty-two oracle capabilities were free for a month before the
2026-08-04 fix, and ATLAS's six capabilities ($0.01–$0.05) were still free on 2026-08-16 —
found only because a canary started probing one capability per provider instead of one
capability. This test is the cheap half of the guard: it fails when a satellite is added
to the ecosystem map but not to the seller-of-record list.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYMENT_ENV = ROOT / "deploy" / "hub-payment.env.example"

# Satellites this hub sells for: they serve priced capabilities and bill nobody
# themselves, so the hub holds and captures the list price. Verified per entry — an
# unpaid invoke straight at the satellite answers 200, i.e. it does not invoice out of
# band. A peer that DOES bill must never be added here: the buyer would pay twice.
NON_BILLING_SATELLITES = {
    "https://oracles.modelmarket.dev/family",
    "https://iot.modelmarket.dev",
    "https://atlas.modelmarket.dev",
}


def _sells_for() -> list[str]:
    text = PAYMENT_ENV.read_text(encoding="utf-8")
    match = re.search(r"^AIMARKET_SELLS_FOR=(.*)$", text, re.MULTILINE)
    assert match, f"{PAYMENT_ENV} no longer defines AIMARKET_SELLS_FOR"
    return [p.strip().rstrip("/") for p in match.group(1).split(",") if p.strip()]


@pytest.mark.parametrize("satellite", sorted(NON_BILLING_SATELLITES))
def test_every_non_billing_satellite_is_sold_for(satellite):
    declared = _sells_for()
    assert satellite in declared, (
        f"{satellite} serves priced capabilities and does not bill for them, but the hub is "
        f"not declared its seller — every one of its capabilities is served free while "
        f"advertising a price. Add it to AIMARKET_SELLS_FOR in {PAYMENT_ENV.name}."
    )


def test_the_list_has_no_duplicates_or_trailing_slashes():
    """Matching is a scheme+host+path prefix compare, so a stray slash is a silent miss."""
    declared = _sells_for()
    assert len(declared) == len(set(declared)), f"duplicate entries: {declared}"
    raw = re.search(r"^AIMARKET_SELLS_FOR=(.*)$", PAYMENT_ENV.read_text(), re.MULTILINE).group(1)
    assert not any(p.strip().endswith("/") for p in raw.split(",")), (
        "a trailing slash changes the prefix compare — write the URL without one"
    )


def test_nothing_is_declared_that_bills_for_itself():
    """Guard on the other direction: declaring a billing peer charges the buyer twice."""
    declared = set(_sells_for())
    unexpected = declared - NON_BILLING_SATELLITES
    assert not unexpected, (
        f"{sorted(unexpected)} is declared as sold-for but is not in this file's verified "
        f"non-billing set. Confirm an unpaid invoke straight at that peer answers 200 (it "
        f"does not invoice out of band), then add it to NON_BILLING_SATELLITES here."
    )


def test_the_deploy_script_carries_the_list_forward_and_can_change_it():
    """The captured container env is the only copy; a satellite added since the last
    deploy is invisible to it, which is how atlas stayed free."""
    script = (ROOT / "scripts" / "deploy_hub_rebuild.sh").read_text(encoding="utf-8")
    assert 'SELLS_FOR="${AIMARKET_SELLS_FOR:-' in script, "no override path"
    assert '-e AIMARKET_SELLS_FOR="$SELLS_FOR"' in script, "the value never reaches the container"
    assert "would be served free" in script, "an empty list must abort the deploy"
