"""The ERC-8004 feedback wallet signs calldata carrying a third party's endpoint string;
it must bound what goes in, and what one transaction may cost."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "erc-8004"))
feedback = pytest.importorskip("feedback")


@pytest.mark.parametrize("url,ok", [
    ("https://agent.example/mcp", True),
    ("http://agent.example/mcp", False),
    ("https://agent.example/" + "a" * 300, False),
    ("https://agent.example/a b", False),
    ("https://agent.example/\x00x", False),
    ("javascript:alert(1)", False),
])
def test_only_short_plain_https_endpoints_go_into_signed_calldata(url, ok):
    assert feedback.endpoint_ok(url) is ok


def test_a_transaction_over_the_caps_is_refused_before_signing(monkeypatch):
    answers = {
        "eth_getTransactionCount": "0x1",
        "eth_getBlockByNumber": {"baseFeePerGas": hex(5_000_000_000)},   # 5 gwei base
        "eth_maxPriorityFeePerGas": hex(1_000_000),
        "eth_estimateGas": hex(100_000),
    }
    monkeypatch.setattr(feedback, "rpc", lambda method, params, tries=6: answers[method])

    class _Acct:
        address = "0x" + "11" * 20

        def sign_transaction(self, tx):
            raise AssertionError("must not sign")

    with pytest.raises(SystemExit, match="caps"):
        feedback.send_one(_Acct(), "0x00")
