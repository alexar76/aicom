"""getChannel is decoded by the layout the contract actually returns.

AIMarketEscrowV2 inserts closableAt before status. Read with the V1 layout, a V2 channel
whose depositor asked to exit (closableAt != 0) — or one already refunded — decoded as Open.
"""

from __future__ import annotations

from aimarket_hub.escrow_bridge import chain


def _word(n: int) -> str:
    return format(n, "064x")


def _addr(a: str) -> str:
    return a[2:].rjust(64, "0")


DEP = "0x" + "11" * 20
TOK = "0x" + "22" * 20


def _v1(status: int) -> str:
    return "0x" + _addr(DEP) + _addr("0x" + "00" * 20) + _addr(TOK) + "".join(
        _word(x) for x in (5_000_000, 5_000_000, 0, 4_000_000_000, 0, status))


def _v2(closable_at: int, status: int) -> str:
    return "0x" + _addr(DEP) + _addr("0x" + "00" * 20) + _addr(TOK) + "".join(
        _word(x) for x in (5_000_000, 5_000_000, 0, 4_000_000_000, 0, closable_at, status))


class _Pool:
    def __init__(self, answer):
        self.answer = answer

    def call(self, method, params):
        return self.answer


def _read(monkeypatch, answer):
    monkeypatch.setattr(chain, "_pool", lambda: _Pool(answer))
    return chain.read_channel("0x" + "ab" * 32, address="0x" + "33" * 20)


def test_v1_layout_still_decodes(monkeypatch):
    ch = _read(monkeypatch, _v1(chain.STATUS_OPEN))
    assert ch.is_open and ch.closable_at == 0


def test_a_refunded_v2_channel_is_not_open(monkeypatch):
    ch = _read(monkeypatch, _v2(closable_at=0, status=2))
    assert not ch.is_open and ch.status == 2


def test_a_v2_channel_with_an_exit_request_keeps_its_real_status(monkeypatch):
    ch = _read(monkeypatch, _v2(closable_at=1_800_000_000, status=chain.STATUS_OPEN))
    assert ch.is_open and ch.closable_at == 1_800_000_000
