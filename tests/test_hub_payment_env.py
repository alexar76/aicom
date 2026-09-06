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
    # Added 2026-08-24 with the security layer. Verified per entry, by reading the satellite
    # rather than assuming: none of the three has any payment gate at all — no 402 branch, no
    # escrow, no quota, no paid-tier secret. BASANOS declares a price and bills nobody
    # (`grep -riE '402|payment|escrow|quota'` over the satellite finds only its own price
    # declarations); MOMUS leaves `free_tier_max` empty on all seven capabilities so
    # `enforce_free_tier` iterates over nothing, and its `economics.py` pays bounties OUT from
    # a separate Treasury key — the opposite direction of money; THEMIS says in its own
    # federation module that the verdict is not for sale.
    "https://basanos.modelmarket.dev",
    "https://momus.modelmarket.dev",
    "https://themis.modelmarket.dev",
}
# WARDEN is deliberately absent, and this is the reason rather than an oversight: warden/ has
# no server at all (11 TypeScript source files, zero HTTP listeners; its entry point is an
# in-process `warden.vet(ref, tools)` call). warden.modelmarket.dev serves one static file for
# every path, so even `/health` answers 200 with HTML — any check that only asserts a 200
# marks it up forever. There is no upstream for the hub to be seller of record FOR.


def _assignments(key: str, path: Path = None) -> list[str]:
    """Every assignment of ``key``, in file order."""
    text = (path or PAYMENT_ENV).read_text(encoding="utf-8")
    return re.findall(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)


def _sells_for() -> list[str]:
    """The value the CONTAINER will run with — the LAST assignment, not the first.

    `docker --env-file` passes duplicates through in order and the process keeps the final
    one. Reading the first (`re.search`) is how this test stayed green through 2026-08-24
    while prod served atlas free: the deployed file declared atlas on one line and eleven
    later lines dropped it again, so every reader that stopped at the first match reported a
    list the hub was not using.
    """
    found = _assignments("AIMARKET_SELLS_FOR")
    assert found, f"{PAYMENT_ENV} no longer defines AIMARKET_SELLS_FOR"
    return [p.strip().rstrip("/") for p in found[-1].split(",") if p.strip()]


def test_no_key_is_assigned_twice():
    """A second assignment silently overrides the first, and only the last one is live.

    This is a whole-file rule, not a SELLS_FOR rule: any duplicated key in an env file
    means the value a reader sees depends on whether it reads top-down or bottom-up.
    """
    text = PAYMENT_ENV.read_text(encoding="utf-8")
    keys = re.findall(r"^([A-Z_0-9]+)=", text, re.MULTILINE)
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, (
        f"{PAYMENT_ENV.name} assigns {dupes} more than once. Only the LAST assignment "
        f"reaches the container; collapse each key to a single line."
    )


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
    raw = _assignments("AIMARKET_SELLS_FOR")[-1]
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


def test_the_rebuild_script_reads_env_the_way_docker_does():
    """The capture must collapse duplicates to the LAST assignment, and be read that way.

    Two separate mistakes made the same silent regression possible, so both are pinned: the
    capture emitted every duplicate, and the SELLS_FOR read took `head -1` of them.
    """
    script = (ROOT / "scripts" / "deploy_hub_rebuild.sh").read_text(encoding="utf-8")
    assert "last[key] = entry" in script, (
        "the environment capture no longer collapses duplicate assignments; a duplicated "
        "key round-trips into the next container and its live value stops being readable"
    )
    assert "| head -1 | cut -d= -f2-" not in script, (
        "SELLS_FOR is being read from the FIRST assignment again — docker keeps the last"
    )
    assert "| tail -1 | cut -d= -f2-" in script, "SELLS_FOR must be read as last-wins"
