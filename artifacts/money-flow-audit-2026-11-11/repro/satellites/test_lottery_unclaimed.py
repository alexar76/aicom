"""Scratch repro: the relayer never claims a prize won by a wallet it derived itself
(UNI auto-wallet mesh roster, LIVE work seats), and never refunds its own sponsor /
benefactor / agent funds from a cancelled round."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

from eth_account import Account

from ailottery_relayer import economy, economy_draw
from ailottery_relayer.economy import EconomyEngine, uni_wallet_roster, live_work_roster
from ailottery_relayer.mesh import MeshAgent


def _engine_with_roster(roster, agent_keys):
    eng = object.__new__(EconomyEngine)
    sent = []
    eng.cfg = SimpleNamespace(treasurer_enabled=False, wei_to_usd=lambda w: w / 1e18)
    eng.agent_keys = agent_keys
    # exactly what __init__ builds, once, from cfg.agent_keys
    eng._key_by_addr = {Account.from_key(k).address: k for k in agent_keys}
    eng._roster = roster
    eng._name_by_addr = {p.addr: p.name for p in roster}
    eng.events = []
    eng._prev_players = 0
    winner = roster[0].addr
    eng.chain = SimpleNamespace(
        get_round=lambda rid: {"winner": winner, "prizeClaimed": False, "prizePool": 10**18,
                               "ticketRevenue": 0, "funding": 10**18, "sOpexBps": 2000},
        economy=lambda: {"opexAvailable": 0},
        participants_count=lambda rid: len(roster),
        send=lambda fn, key, value=0: sent.append((fn, key)) or {"status": 1},
    )
    eng.fn = SimpleNamespace(claimPrize=lambda rid: f"claimPrize:{rid}")
    return eng, sent, winner


def test_uni_auto_wallet_winner_prize_is_never_claimed():
    agents = [MeshAgent("agent-a", "CodeNova", 0.9), MeshAgent("agent-b", "AuditHawk", 0.3)]
    roster = uni_wallet_roster(agents, seed="seed")
    # the relayer HOLDS this key (derived), so it could claim
    assert Account.from_key(roster[0].key).address == roster[0].addr
    eng, sent, winner = _engine_with_roster(roster, agent_keys=[])
    eng.settle(5)
    assert sent == []  # no claimPrize: prize stays in the contract


def test_live_work_seat_winner_prize_is_never_claimed():
    roster = live_work_roster("seed", 3)
    eng, sent, _ = _engine_with_roster(roster, agent_keys=["0x" + "11" * 32])
    eng.settle(9)
    assert sent == []


def test_relayer_never_calls_refund_or_forfeit():
    src = inspect.getsource(economy) + inspect.getsource(economy_draw)
    assert "refund(" not in src.replace("refundable", "")
    assert "forfeitUnclaimedPrize" not in src
