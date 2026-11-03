"""V2 keys its replay flag by (channelId, receiptId): ``usedReceipts(receiptId)`` read raw
always says "not used" there, so a receipt collected out of band would stay owed in the
hub's queue and block its channel (2026-10-08 review). The hub asks ``isReceiptUsed``
when it knows the channel, and falls back to V1's flag when that function does not exist."""
from __future__ import annotations

import pytest

from aimarket_hub.escrow_bridge import chain
from aimarket_hub.escrow_bridge.eip712 import crypto_available

pytestmark = pytest.mark.skipif(not crypto_available(), reason="eth-utils not installed")

ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
CHANNEL = "0x" + "11" * 32
RECEIPT = "0x" + "22" * 32
TRUE = "0x" + "0" * 63 + "1"
FALSE = "0x" + "0" * 64


class _Pool:
    def __init__(self, v2: bool, used: bool):
        self.v2, self.used, self.calls = v2, used, []

    def call(self, method, params):
        data = params[0]["data"]
        self.calls.append(data[:10])
        if data.startswith("0x" + chain.selector(chain.IS_RECEIPT_USED_SIG).hex()):
            if not self.v2:
                raise RuntimeError("execution reverted")
            return TRUE if self.used else FALSE
        # usedReceipts(receiptId): on V2 the raw id is never a key, so it reads false
        return FALSE if self.v2 else (TRUE if self.used else FALSE)


def test_v2_asks_the_channel_keyed_flag(monkeypatch):
    monkeypatch.setattr(chain, "_pool", lambda: _Pool(v2=True, used=True))
    assert chain.receipt_already_used(RECEIPT, address=ESCROW, channel_id=CHANNEL) is True


def test_v1_falls_back_to_its_global_flag(monkeypatch):
    monkeypatch.setattr(chain, "_pool", lambda: _Pool(v2=False, used=True))
    assert chain.receipt_already_used(RECEIPT, address=ESCROW, channel_id=CHANNEL) is True


def test_without_a_channel_the_v1_read_is_unchanged(monkeypatch):
    monkeypatch.setattr(chain, "_pool", lambda: _Pool(v2=False, used=False))
    assert chain.receipt_already_used(RECEIPT, address=ESCROW) is False
