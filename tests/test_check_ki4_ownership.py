"""scripts/check_ki4_ownership.py fails exactly when an EOA owns a contract above the KI-4 limit."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_ki4_ownership", Path(__file__).resolve().parents[1] / "scripts" / "check_ki4_ownership.py")
ki4 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ki4)

# Every RPC call is fake; fixture addresses must not depend on a live deployment.
REGISTRY = {"network": "base", "contracts": {
    "USDC": "0x" + "aa" * 20,
    "AIMarketEscrow": "0x" + "bb" * 20,
    "AIMarketCapabilityNFT": "0x" + "cc" * 20}}
EOA = "0x" + "12" * 20
SAFE = "0x" + "5a" * 20


def _chain(owner: str, usdc: float, safe_code: bool):
    def call(url, method, params):
        if method == "eth_getCode":
            return "0x6080" if (safe_code and params[0] == owner) else "0x"
        data = params[0]["data"]
        if data.startswith(ki4.BALANCE_OF):
            return hex(int(usdc * 1e6))
        if data == ki4.OWNER:
            return "0x" + owner[2:].rjust(64, "0")
        return "0x" + "0" * 64
    return call


@pytest.mark.parametrize("owner,usdc,safe,ok", [
    (EOA, 0.0, False, True),          # today: an EOA owner and nothing at stake
    (EOA, 999.99, False, True),
    (EOA, 1000.0, False, False),      # the KI-4 line
    (SAFE, 50_000.0, True, True),     # a Safe may hold any amount
])
def test_the_ki4_line(owner, usdc, safe, ok):
    report = ki4.check("rpc", REGISTRY, 1000.0, call=_chain(owner, usdc, safe))
    assert report["ok"] is ok
    assert report["escrow_usdc"] == pytest.approx(usdc)
    assert report["contracts"]["AIMarketEscrow"]["owner"] == owner
    assert report["contracts"]["AIMarketEscrow"]["pending_owner"] is None
    assert ("reason" in report) is (not ok)
