"""`AIMARKET_SUPPLY_OPERATOR_PUBLISHERS` was configured in production and read by nothing.

The attested hub set it to its three bundled providers, and
`docs/production-postgres.md` described exactly what it does: "bypasses only the
external collateral requirement for those exact IDs; every unlisted community
publisher still needs verified stake". No code referenced the variable, so the
operator's own first-party providers could not publish at all once the $25
production stake gate came in — a gate stricter than documented, failing closed
and silently, which is the hardest kind of misconfiguration to see.

These tests pin both halves: the exemption applies, and it applies to nothing else.
"""
from __future__ import annotations

import pytest

from aimarket_hub.supply_security import SupplySecurityPolicy


@pytest.fixture()
def clean_env(monkeypatch):
    for name in ("AIMARKET_SUPPLY_OPERATOR_PUBLISHERS", "AIMARKET_SUPPLY_PRODUCT_ALLOWLIST",
                 "AIMARKET_SUPPLY_SECURITY_RELAXED", "AIMARKET_SUPPLY_MIN_STAKE_USD"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_the_list_is_parsed_from_the_environment(clean_env):
    clean_env.setenv("AIMARKET_SUPPLY_OPERATOR_PUBLISHERS",
                     " memory-market , truth-layer ,, attested-deal ")
    policy = SupplySecurityPolicy.from_config(_config())
    assert policy.operator_publishers == ("memory-market", "truth-layer", "attested-deal")


def test_an_unset_list_exempts_nobody(clean_env):
    policy = SupplySecurityPolicy.from_config(_config())
    assert policy.operator_publishers == ()


def test_the_exemption_covers_collateral_and_nothing_else():
    """A first-party provider still passes every other gate.

    The waiver is deliberately narrow: it is checked at one place, inside the
    `min_stake_usd` branch, so credential, ownership, rate-limit, allowlist and
    signature gates are untouched by it.
    """
    import inspect

    from aimarket_hub import supply_security

    source = inspect.getsource(supply_security)
    assert source.count("self.policy.operator_publishers") == 1, (
        "the operator exemption must be consulted in exactly one place — the collateral "
        "branch — or it silently becomes a general-purpose bypass"
    )
    stake_branch = source.split("if self.policy.min_stake_usd > 0:", 1)[1]
    head = stake_branch.split("return publisher_id, pubkey", 1)[0]
    assert "operator_publishers" in head
    assert "supply_stake_get" in head, "unlisted publishers must still be asked for stake"


def _config():
    class _C:
        min_trust_score = 0.25

    return _C()
