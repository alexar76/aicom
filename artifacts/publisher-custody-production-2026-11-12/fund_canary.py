"""Fund and top up the single ModelMarket publisher canary from its documented POV buyer."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "aimarket-agent"))
from aimarket_agent.topup import calldata, typed_data

BASE = 8453
RPCS = ("https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.drpc.org")
BUYER = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a"
PAYOUT_SENDER = "0xb35100405F7aeA3e11de2F5Bf18316be507f6Eba"
TOPUP_PAYEE = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
GAS_ORACLE = "0x420000000000000000000000000000000000000F"
FLOAT_ETH_WEI = 8_000_000_000_000
FLOAT_USDC_UNITS = 20
TOPUP_UNITS = 10_000
MAX_TX_FEE_WEI = 8_000_000_000_000
MAX_STATE_AGE_S = 3600
WALLET_FILE = Path.home() / ".aicom-pov-buyer.json"


def rpc(method: str, params: list):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    errors = []
    for url in RPCS:
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json",
                                                                    "User-Agent": "aicom-production-check/1"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                value = json.load(response)
        except urllib.error.HTTPError as exc:
            errors.append(f"HTTP {exc.code}")
        except (OSError, ValueError) as exc:
            errors.append(type(exc).__name__)
        else:
            if "result" in value:
                return value["result"]
            errors.append("JSON-RPC error")
    raise RuntimeError(f"{method}: no RPC returned a result ({', '.join(errors)})")


def word(address: str) -> str:
    return address[2:].lower().zfill(64)


def token_balance(address: str) -> int:
    return int(rpc("eth_call", [{"to": USDC, "data": "0x70a08231" + word(address)}, "latest"]), 16)


def transfer_intent(step: str, quote_path: Path | None, account) -> dict:
    if step == "fund-gas":
        assert rpc("eth_getCode", [PAYOUT_SENDER, "latest"]) == "0x"
        return {"to": PAYOUT_SENDER, "value": FLOAT_ETH_WEI, "data": "0x"}
    if step == "fund-usdc":
        assert token_balance(BUYER) >= FLOAT_USDC_UNITS + TOPUP_UNITS
        return {"to": USDC, "value": 0,
                "data": "0xa9059cbb" + word(PAYOUT_SENDER) + format(FLOAT_USDC_UNITS, "064x")}
    if quote_path is None:
        raise ValueError("topup requires the live quote file")
    offer = json.loads(quote_path.read_text())
    if "quote" in offer:
        offer = offer["quote"]
    accept = offer["accepts"][0]
    assert accept["scheme"] == "exact" and accept["payTo"].lower() == TOPUP_PAYEE.lower()
    assert accept["asset"].lower() == USDC.lower() and token_balance(BUYER) >= TOPUP_UNITS
    expires_at = int(offer["expires_at"])
    chain_now = int(rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
    if not chain_now + 60 < expires_at <= chain_now + 1000:
        raise ValueError("quote expiry is outside the live Base clock window")
    typed = typed_data(offer, sender=account.address, valid_before=min(expires_at, chain_now + 600))
    assert typed["domain"] == {"name": "USD Coin", "version": "2", "chainId": BASE,
                               "verifyingContract": accept["extra"]["verifyingContract"]}
    assert typed["domain"]["verifyingContract"].lower() == USDC.lower()
    assert int(typed["message"]["value"]) == TOPUP_UNITS
    signature = account.sign_message(encode_typed_data(full_message=typed)).signature
    return {"to": USDC, "value": 0, "data": calldata(typed, "0x" + bytes(signature).hex())}


def prepare(step: str, quote: Path | None, state_path: Path) -> dict:
    if WALLET_FILE.stat().st_mode & 0o077:
        raise ValueError("POV buyer wallet must be owner-only")
    account = Account.from_key(json.loads(WALLET_FILE.read_text())["private_key"])
    if account.address.lower() != BUYER.lower():
        raise ValueError("POV buyer key does not match the previously verified address")
    intent = transfer_intent(step, quote, account)
    pending = int(rpc("eth_getTransactionCount", [BUYER, "pending"]), 16)
    if pending != int(rpc("eth_getTransactionCount", [BUYER, "latest"]), 16):
        raise RuntimeError("POV wallet has another pending operation; resume after it settles")
    estimate = int(rpc("eth_estimateGas", [{**intent, "from": BUYER, "value": hex(intent["value"])}]), 16)
    gas = (estimate * 6 + 4) // 5
    gas_price = int(rpc("eth_gasPrice", []), 16)
    if not 0 < gas <= 150_000 or gas_price <= 0:
        raise ValueError("invalid Base fee quote")
    tx = {**intent, "type": 2, "chainId": BASE, "nonce": pending, "gas": gas,
          "maxFeePerGas": 2 * gas_price, "maxPriorityFeePerGas": min(gas_price, 1_000_000)}
    signed = account.sign_transaction(tx)
    raw = bytes(signed.raw_transaction)
    gas_data = keccak(text="getL1Fee(bytes)")[:4] + encode(["bytes"], [raw])
    l1_fee = int(rpc("eth_call", [{"to": GAS_ORACLE, "data": "0x" + gas_data.hex()}, "latest"]), 16)
    fee_limit = gas * tx["maxFeePerGas"] + 5 * l1_fee
    if fee_limit > MAX_TX_FEE_WEI:
        raise ValueError(f"Base fee exceeds the micro-canary limit ({fee_limit} wei)")
    if int(rpc("eth_getBalance", [BUYER, "latest"]), 16) < intent["value"] + fee_limit:
        raise ValueError("insufficient native gas balance")
    state = {"step": step, "from": BUYER, "tx_hash": "0x" + bytes(signed.hash).hex(), "nonce": pending,
             "gas_limit": gas, "fee_limit_wei": fee_limit, "raw": "0x" + raw.hex(), "created_at": int(time.time())}
    with os.fdopen(os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("fund-gas", "fund-usdc", "topup"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--quote", type=Path)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    args.state_dir.mkdir(mode=0o700, exist_ok=True)
    if args.state_dir.stat().st_mode & 0o077 or args.state_dir.is_symlink():
        raise SystemExit("state directory must be owner-only and not a symlink")
    if int(rpc("eth_chainId", []), 16) != BASE:
        raise SystemExit("RPC is not Base mainnet")
    state_path = args.state_dir / (args.step + ".json")
    if state_path.exists():
        if state_path.is_symlink() or state_path.stat().st_mode & 0o077:
            raise SystemExit("state must be an owner-only regular file")
        state = json.loads(state_path.read_text())
        assert state["step"] == args.step and state["from"] == BUYER
        assert "0x" + keccak(bytes.fromhex(state["raw"][2:])).hex() == state["tx_hash"]
    else:
        if not args.send:
            raise SystemExit("no saved operation; --send creates and submits the authorized transaction")
        state = prepare(args.step, args.quote, state_path)
    tx_hash = state["tx_hash"]
    public = {k: v for k, v in state.items() if k != "raw"}
    print(json.dumps(public), flush=True)
    receipt = rpc("eth_getTransactionReceipt", [tx_hash])
    if not receipt and args.send:
        if time.time() - state["created_at"] > MAX_STATE_AGE_S:
            raise SystemExit("saved transaction is too old to rebroadcast automatically; inspect its hash")
        try:
            submitted = rpc("eth_sendRawTransaction", [state["raw"]])
            assert submitted.lower() == tx_hash
        except RuntimeError:
            print("Broadcast response unavailable. Checking the saved hash only.", flush=True)
        for _ in range(12):
            time.sleep(2)
            receipt = rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
    if not receipt:
        raise SystemExit("same transaction is pending; run this step again without creating new state")
    if receipt["status"] != "0x1":
        raise SystemExit("saved transaction reverted; no replacement was signed")
    print(json.dumps({"transaction": tx_hash, "block": int(receipt["blockNumber"], 16),
                      "gas_used": int(receipt["gasUsed"], 16), "status": "mined"}))


if __name__ == "__main__":
    main()
