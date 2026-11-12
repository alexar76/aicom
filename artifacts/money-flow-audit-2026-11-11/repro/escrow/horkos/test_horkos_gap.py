"""HORKOS: a broadcast that never reached a node leaves a nonce gap nothing fills."""
import os, sys
WT = "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/escrow-signer"
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, "tests"))
from conftest import FakeClock, FakeRpc, ZERO, make_settings, sign_debit, envelope  # noqa: E402
from escrow_signer import config as cfg  # noqa: E402
from escrow_signer.ledger import Ledger  # noqa: E402
from escrow_signer.policy import PolicySigner  # noqa: E402


def _signer(tmp_path, clock):
    db = str(tmp_path / "signer.db")
    ps = PolicySigner(make_settings(db), Ledger(db, clock=clock), FakeRpc(clock=clock, hot_address=ZERO), clock=clock)
    ps.boot()
    assert ps.ready
    return ps


def test_unreached_broadcast_leaves_permanent_nonce_gap(tmp_path):
    clock = FakeClock()
    s = _signer(tmp_path, clock)
    chain_expects = s.rpc.nonce  # 0: nothing ever mined from this key
    # 1) every RPC answers 429/timeout on eth_sendRawTransaction -> RpcUnavailable
    s.rpc.send_error = "unavailable"
    a = sign_debit(s, receipt=b"\x0a" * 32, channel=b"\x0a" * 32)
    d = s.handle(envelope(a))
    assert d.reason_code == "broadcast_failed"
    s.rpc.send_error = None
    # 2) the hub retries the SAME receipt: HORKOS never rebroadcasts, answers 409
    d2 = s.handle(envelope(a))
    assert (d2.status, d2.reason_code) == (409, "reserved_unresolved")
    # 3) a debit on another channel is signed one nonce ABOVE what the chain expects
    b = sign_debit(s, receipt=b"\x0b" * 32, channel=b"\x0b" * 32)
    d3 = s.handle(envelope(b))
    assert d3.status == 200
    row_b = s.ledger.get(cfg.CHAIN_ID, cfg.ESCROW, d3.receipt_id)
    assert row_b.account_nonce == chain_expects + 1   # gap at chain_expects: never minable
    # 4) a restart does not close it while any later row is still live
    s.boot()
    c = sign_debit(s, receipt=b"\x0c" * 32, channel=b"\x0c" * 32)
    d4 = s.handle(envelope(c))
    row_c = s.ledger.get(cfg.CHAIN_ID, cfg.ESCROW, d4.receipt_id)
    assert row_c.account_nonce == chain_expects + 2
