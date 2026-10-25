#!/usr/bin/env python3
"""KI-4 as a check that can fail: who owns the live escrow and NFT, and what is at stake.

docs/known-issues.md KI-4 allows a single-EOA owner "for testnet drills and mainnet pilots with
< $1k TVL". Nothing measured that; this does. It reads the canonical deployment
(config/deployments/base-mainnet.json), asks Base for owner(), pendingOwner(), whether the
owner holds code (a Safe does, an EOA does not) and how much USDC the escrow holds, prints one
JSON object, and exits 1 when an EOA owns a contract while the escrow holds the limit or more.

    python3 scripts/check_ki4_ownership.py                 # limit $1000
    KI4_TVL_LIMIT_USD=250 BASE_RPC=https://... python3 scripts/check_ki4_ownership.py

Read-only: eth_call and eth_getCode, no key, no transaction.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OWNER, PENDING_OWNER, BALANCE_OF = "0x8da5cb5b", "0xe30c3978", "0x70a08231"


def rpc(url: str, method: str, params: list[Any]) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "aicom-ki4-check/1"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # the operator chooses the RPC URL
        out = json.load(resp)
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def _address(word: str) -> str:
    return "0x" + word[-40:]


def check(url: str, registry: dict[str, Any], limit_usd: float, call: Any = rpc) -> dict[str, Any]:
    contracts = registry["contracts"]
    escrow, usdc = contracts["AIMarketEscrow"], contracts["USDC"]
    held = int(call(url, "eth_call", [{"to": usdc, "data": BALANCE_OF + escrow[2:].lower().rjust(64, "0")}, "latest"]), 16)
    tvl = held / 1e6
    report: dict[str, Any] = {"network": registry.get("network"), "escrow_usdc": tvl, "limit_usd": limit_usd, "contracts": {}}
    breach = False
    for name in ("AIMarketEscrow", "AIMarketCapabilityNFT"):
        addr = contracts[name]
        owner = _address(call(url, "eth_call", [{"to": addr, "data": OWNER}, "latest"]))
        pending = _address(call(url, "eth_call", [{"to": addr, "data": PENDING_OWNER}, "latest"]))
        owner_is_contract = call(url, "eth_getCode", [owner, "latest"]) not in ("0x", "0x0", "")
        report["contracts"][name] = {"address": addr, "owner": owner, "owner_is_contract": owner_is_contract,
                                     "pending_owner": None if int(pending, 16) == 0 else pending}
        breach = breach or (not owner_is_contract and tvl >= limit_usd)
    report["ok"] = not breach
    if breach:
        report["reason"] = (f"an EOA owns a contract while the escrow holds {tvl:.2f} USDC (KI-4 limit "
                            f"{limit_usd:.0f}): move ownership to a Safe (scripts/multisig_transfer_runbook.sh)")
    return report


def main() -> int:
    registry = json.loads((ROOT / "config" / "deployments" / "base-mainnet.json").read_text())
    report = check(os.environ.get("BASE_RPC", "https://mainnet.base.org"), registry,
                   float(os.environ.get("KI4_TVL_LIMIT_USD", "1000")))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
