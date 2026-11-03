"""Hub-side self-slash: consumer cost/conduct bond enforcement (register → breach → slash → federate).

Mirrors the publisher stake/slash path: a bond must be backed by staked collateral, and a
declared-ceiling-vs-observed-spend breach slashes that stake and federates the attestation
through the same slash registry. LUMEN + signer are mocked so the unit test does no network.
"""
from unittest.mock import MagicMock

import pytest

from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.supply_security import SupplySecurity


@pytest.fixture
def ss(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "10")
    db = HubDatabase(str(tmp_path / "hub.db"))
    s = SupplySecurity(db, HubConfig(), signer=MagicMock(), slash_registry=MagicMock())
    s.refresh_publisher_trust = lambda pid: 0.5  # avoid the LUMEN oracle network call in unit tests
    return s


def test_self_bond_requires_backing_stake(ss):
    with pytest.raises(ValueError):
        ss.register_self_bond("agent-1", "0xabc", ceiling_usd=0.5, bond_usd=1.0)  # no stake yet


def test_register_then_within_bond_no_slash(ss):
    ss.stake("agent-1", 2.0)
    rec = ss.register_self_bond("agent-1", "0xAbC", ceiling_usd=0.5, bond_usd=1.0, commitment="cafe")
    assert rec["status"] == "bonded"
    assert rec["bond_usd"] == 1.0 and rec["staked_usd"] >= 1.0
    v = ss.slash_self_bond("agent-1", observed_spend_usd=0.4)
    assert v["verdict"] == "within-bond"
    assert v["slashed_usd"] == 0.0
    ss.slash_registry.record_local_slash.assert_not_called()


def test_breach_slashes_stake_and_federates(ss):
    ss.stake("agent-1", 2.0)
    ss.register_self_bond("agent-1", "0xAbC", ceiling_usd=0.5, bond_usd=1.0)
    before = ss.db.supply_stake_get("agent-1")
    v = ss.slash_self_bond("agent-1", observed_spend_usd=0.9, evidence="hub-settlement#1")
    assert v["verdict"] == "self-slash"
    assert v["overspend_usd"] == pytest.approx(0.4)   # 0.9 - 0.5
    assert v["slashed_usd"] == pytest.approx(0.4)     # min(bond 1.0, overspend 0.4)
    assert ss.db.supply_stake_get("agent-1") == pytest.approx(before - 0.4)
    ss.slash_registry.record_local_slash.assert_called_once()
    assert ss.db.self_bond_get("agent-1")["slashed_usd"] == pytest.approx(0.4)


def test_penalty_capped_at_declared_bond(ss):
    ss.stake("agent-1", 5.0)
    ss.register_self_bond("agent-1", "0xAbC", ceiling_usd=0.5, bond_usd=1.0)
    v = ss.slash_self_bond("agent-1", observed_spend_usd=10.0)  # overspend 9.5, capped at bond 1.0
    assert v["slashed_usd"] == pytest.approx(1.0)


def test_slash_unknown_agent_raises(ss):
    with pytest.raises(ValueError):
        ss.slash_self_bond("nobody", 5.0)
