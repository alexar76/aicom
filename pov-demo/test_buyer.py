"""The buyer on AIMarketEscrowV2: a depositor announces its exit and settles an hour later.

V1 settles at once and must keep doing so; V2 returns ten words from getChannel (closableAt
before status) and reverts a depositor's settleChannel until closableAt. Everything here runs
against a fake chain — no RPC, no money.
"""
import sys
from pathlib import Path

import pytest
from eth_abi import encode

sys.path.insert(0, str(Path(__file__).parent))
import buyer as b  # noqa: E402
import journey as j  # noqa: E402

ESCROW = "0x" + "e5" * 20
TOKEN = "0x" + "70" * 20
WALLET = "0x" + "aa" * 20
CH = b"\x11" * 32


class Chain:
    """getChannel answers per channel; requestClose / settleChannel change that state."""

    def __init__(self, *, v2: bool, now: int = 1_800_000_000):
        self.v2, self.now = v2, now
        self.channels = {}
        self.sent = []
        self.balance = 0

    def put(self, ch: bytes, *, balance=990_000, used=10_000, closable_at=0, status=0):
        self.channels[ch] = dict(balance=balance, used=used, closable_at=closable_at, status=status)

    def raw(self, ch: bytes) -> bytes:
        c = self.channels.get(ch, dict(balance=0, used=0, closable_at=0, status=0))
        head = ["0x" + "de" * 20, "0x" + "be" * 20, TOKEN]
        nums = [1_000_000, c["balance"], c["used"], self.now + 86_400, 0]
        if self.v2:
            return encode(["address"] * 3 + ["uint256"] * 6 + ["uint8"], head + nums + [c["closable_at"], c["status"]])
        return encode(["address"] * 3 + ["uint256"] * 5 + ["uint8"], head + nums + [c["status"]])

    # the three seams buyer.py talks to the chain through
    def call(self, to, data):
        if data[:4] == b.sel("getChannel(bytes32)"):
            return self.raw(data[4:36])
        if data[:4] == b.sel("balanceOf(address)"):
            return encode(["uint256"], [self.balance])
        raise AssertionError(f"unexpected call {data[:4].hex()}")

    def send(self, wallet, to, data, label):
        self.sent.append(label)
        ch = data[4:36]
        if label.startswith("requestClose"):
            self.channels[ch]["closable_at"] = self.now + 3600
        if label.startswith("settleChannel"):
            c = self.channels[ch]
            assert not self.v2 or (c["closable_at"] and self.now >= c["closable_at"]), "would revert"
            self.balance += c["balance"]
            c["status"] = 1
        return {"step": label, "tx": "0x" + "ab" * 32, "block": 1}

    def rpc(self, method, params):
        if method == "eth_getTransactionReceipt":
            return {"logs": []}
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(self.now)}
        if method == "eth_blockNumber":
            return hex(500)
        if method == "eth_getLogs":
            return [{"topics": [j.OPENED_TOPIC, "0x" + ch.hex(), "0x" + "00" * 12 + WALLET[2:]]}
                    for ch in self.channels]
        raise AssertionError(f"unexpected rpc {method}")


@pytest.fixture
def chain(monkeypatch, request):
    c = Chain(v2=request.param)
    monkeypatch.setattr(b, "call", c.call)
    monkeypatch.setattr(b, "rpc", c.rpc)
    monkeypatch.setattr(b.Wallet, "send", lambda self, to, data, label: c.send(self, to, data, label))
    return c


def _wallet():
    w = b.Wallet("0x" + "42" * 32)
    w.address = WALLET
    return w


@pytest.mark.parametrize("chain", [False], indirect=True)
def test_v1_decodes_as_before_and_settles_at_once(chain):
    chain.put(CH, status=0)
    st = b.channel(ESCROW, CH)
    assert (st["v2"], st["closable_at"], st["status"], st["used"]) == (False, 0, 0, 10_000)
    assert b.request_close(ESCROW, _wallet(), CH, []) == 0
    assert chain.sent == []


@pytest.mark.parametrize("chain", [True], indirect=True)
def test_v2_reads_status_after_closable_at(chain):
    chain.put(CH, closable_at=1_800_003_600, status=1)
    st = b.channel(ESCROW, CH)
    assert (st["v2"], st["closable_at"], st["status"]) == (True, 1_800_003_600, 1)


@pytest.mark.parametrize("chain", [True], indirect=True)
def test_v2_requests_close_once(chain):
    chain.put(CH)
    steps = []
    at = b.request_close(ESCROW, _wallet(), CH, steps)
    assert at == chain.now + 3600 and chain.sent == ["requestClose"] and len(steps) == 1
    assert b.request_close(ESCROW, _wallet(), CH, steps) == at
    assert chain.sent == ["requestClose"], "a second announcement would be wasted gas"


@pytest.mark.parametrize("chain", [True], indirect=True)
def test_v2_settle_waits_out_the_window(chain):
    chain.put(CH)
    c = {"escrow": ESCROW, "token": TOKEN}
    run = {"seller": "x", "escrow_channel": "0x" + CH.hex(), "steps": []}
    b.ask_to_close(c, _wallet(), run, wait_debit=False)
    slept = []

    def sleep(s):
        slept.append(s)
        chain.now += s

    real = b.wait_closable
    b.wait_closable = lambda at: real(at, now=lambda: chain.now, sleep=sleep)
    try:
        b.settle(c, _wallet(), run)
    finally:
        b.wait_closable = real
    assert sum(slept) >= 3600
    assert chain.sent == ["requestClose", "settleChannel"]


@pytest.mark.parametrize("chain", [True], indirect=True)
def test_the_journey_settles_only_earlier_channels_whose_window_is_over(chain):
    ready, waiting, settled = b"\x01" * 32, b"\x02" * 32, b"\x03" * 32
    chain.put(ready, closable_at=chain.now - 1)
    chain.put(waiting, closable_at=chain.now + 600)
    chain.put(settled, closable_at=chain.now - 1, status=1)
    run = j.Run()
    j.settle_earlier_channels(ESCROW, TOKEN, _wallet(), run)
    assert chain.sent == ["settleChannel (earlier run)"]
    refunds = [c for c in run.checks if c["name"] == "refund_on_settle"]
    assert len(refunds) == 1 and refunds[0]["ok"], refunds


@pytest.mark.parametrize("chain", [False], indirect=True)
def test_the_journey_on_v1_reads_no_logs(chain):
    chain.put(CH)
    run = j.Run()
    j.settle_earlier_channels(ESCROW, TOKEN, _wallet(), run)
    assert chain.sent == [] and run.checks == []


class LaggingChain(Chain):
    """A public RPC a block behind: the first read after requestClose still shows closableAt 0."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.stale_reads = 0

    def send(self, wallet, to, data, label):
        out = super().send(wallet, to, data, label)
        if label.startswith("requestClose"):
            self.stale_reads = 1
            self.last_close = (data[4:36], self.channels[data[4:36]]["closable_at"])
        return out

    def call(self, to, data):
        if self.stale_reads and data[:4] == b.sel("getChannel(bytes32)"):
            self.stale_reads -= 1
            ch = data[4:36]
            saved = self.channels[ch]["closable_at"]
            self.channels[ch]["closable_at"] = 0
            try:
                return self.raw(ch)
            finally:
                self.channels[ch]["closable_at"] = saved
        return super().call(to, data)

    def rpc(self, method, params):
        if method == "eth_getTransactionReceipt" and getattr(self, "last_close", None):
            ch, at = self.last_close
            return {"logs": [{"address": ESCROW, "topics": [b.CLOSE_REQUESTED_TOPIC, "0x" + ch.hex()],
                              "data": "0x" + format(at, "064x")}]}
        return super().rpc(method, params)


@pytest.fixture
def lagging(monkeypatch):
    c = LaggingChain(v2=True)
    monkeypatch.setattr(b, "call", c.call)
    monkeypatch.setattr(b, "rpc", c.rpc)
    monkeypatch.setattr(b.Wallet, "send", lambda self, to, data, label: c.send(self, to, data, label))
    return c


def test_closable_at_comes_from_the_receipt_not_a_lagging_read(lagging):
    """2026-10-08, first real V2 run: the read after requestClose hit a node a block behind,
    saw closableAt 0, and the buyer settled at once — SettlementWindowOpen."""
    lagging.put(CH)
    at = b.request_close(ESCROW, _wallet(), CH, [])
    assert at == lagging.now + 3600


def test_settle_on_v2_never_goes_before_the_window(lagging):
    """Even told closable_at 0, settle reads the chain and waits rather than reverting."""
    lagging.put(CH, closable_at=lagging.now + 600)
    slept = []

    def sleep(s):
        slept.append(s)
        lagging.now += s

    real = b.wait_closable
    b.wait_closable = lambda at: real(at, now=lambda: lagging.now, sleep=sleep)
    try:
        b.settle({"escrow": ESCROW, "token": TOKEN}, _wallet(),
                 {"seller": "x", "escrow_channel": "0x" + CH.hex(), "steps": [], "closable_at": 0})
    finally:
        b.wait_closable = real
    assert sum(slept) >= 600 and lagging.sent == ["settleChannel"]
