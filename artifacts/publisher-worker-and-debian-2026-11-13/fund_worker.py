"""Send exactly 1 Base USDC from the established treasury to the payout worker."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

from eth_account import Account
from eth_utils import keccak

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publisher-custody-production-2026-11-12"))
from fund_canary import BASE, PAYOUT_SENDER, TOPUP_PAYEE, USDC, rpc, token_balance, word

AMOUNT = 1_000_000
FEE_CAP = 8_000_000_000_000
KEY_FILE = Path.home() / ".aicom-base-deployer-v4.json"
TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()


def private_json(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("expected an owner-only regular file")
        return json.load(stream)


def prepare(journal: Path) -> dict:
    from eth_abi import encode

    wallet = private_json(KEY_FILE)
    entry = wallet["accounts"][0] if "accounts" in wallet else wallet
    account = Account.from_key(entry["private_key"])
    if account.address.lower() != TOPUP_PAYEE.lower():
        raise ValueError("treasury key does not match its established address")
    if token_balance(TOPUP_PAYEE) < AMOUNT or rpc("eth_getCode", [PAYOUT_SENDER, "latest"]) != "0x":
        raise ValueError("treasury balance or payout recipient does not match")
    before = token_balance(PAYOUT_SENDER)
    nonce = int(rpc("eth_getTransactionCount", [TOPUP_PAYEE, "pending"]), 16)
    if nonce != int(rpc("eth_getTransactionCount", [TOPUP_PAYEE, "latest"]), 16):
        raise ValueError("treasury has another pending transaction")
    data = "0xa9059cbb" + word(PAYOUT_SENDER) + format(AMOUNT, "064x")
    estimate = int(rpc("eth_estimateGas", [{"from": TOPUP_PAYEE, "to": USDC, "data": data, "value": "0x0"}]), 16)
    price = int(rpc("eth_gasPrice", []), 16)
    gas = (estimate * 6 + 4) // 5
    if not 0 < gas <= 150_000 or price <= 0:
        raise ValueError("invalid Base gas quote")
    signed = account.sign_transaction({"chainId": BASE, "type": 2, "nonce": nonce, "to": USDC, "data": data,
                                       "value": 0, "gas": gas, "maxFeePerGas": 2 * price,
                                       "maxPriorityFeePerGas": min(price, 1_000_000)})
    raw = bytes(signed.raw_transaction)
    oracle_call = keccak(text="getL1Fee(bytes)")[:4] + encode(["bytes"], [raw])
    l1_fee = int(rpc("eth_call", [{"to": "0x420000000000000000000000000000000000000F",
                                   "data": "0x" + oracle_call.hex()}, "latest"]), 16)
    bound = gas * 2 * price + l1_fee * 5
    if bound > FEE_CAP or int(rpc("eth_getBalance", [TOPUP_PAYEE, "latest"]), 16) < bound:
        raise ValueError("treasury gas exceeds the test budget or available balance")
    state = {"chain_id": BASE, "amount_atomic": AMOUNT, "sender": TOPUP_PAYEE, "recipient": PAYOUT_SENDER,
             "token": USDC, "tx_hash": "0x" + bytes(signed.hash).hex(), "raw": "0x" + raw.hex(),
             "treasury_nonce": nonce, "gas_bound_wei": bound, "payout_balance_before_atomic": before}
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return state


def main() -> None:
    if len(sys.argv) != 2 or int(rpc("eth_chainId", []), 16) != BASE:
        raise SystemExit("expected an owner-only journal path and Base mainnet")
    journal = Path(sys.argv[1])
    state = private_json(journal) if journal.exists() else prepare(journal)
    tx_hash = state["tx_hash"]
    if (state["chain_id"], state["amount_atomic"], state["sender"], state["recipient"], state["token"]) != (
            BASE, AMOUNT, TOPUP_PAYEE, PAYOUT_SENDER, USDC):
        raise ValueError("saved funding intent does not match")
    if "0x" + keccak(bytes.fromhex(state["raw"][2:])).hex() != tx_hash:
        raise ValueError("saved funding transaction does not match its hash")
    receipt = rpc("eth_getTransactionReceipt", [tx_hash])
    if not receipt:
        try:
            returned = rpc("eth_sendRawTransaction", [state["raw"]])
            if returned.lower() != tx_hash:
                raise ValueError("broadcast returned a different hash")
        except RuntimeError:
            print(f"Checking the saved transaction after an ambiguous response: {tx_hash}", file=sys.stderr)
        for _ in range(15):
            time.sleep(2)
            receipt = rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
    if not receipt:
        raise SystemExit(f"same funding transaction still pending: {tx_hash}")
    if receipt["status"] != "0x1" or receipt["transactionHash"].lower() != tx_hash:
        raise ValueError("funding receipt failed or names another transaction")
    topics = [TRANSFER_TOPIC, "0x" + word(TOPUP_PAYEE), "0x" + word(PAYOUT_SENDER)]
    matched = [int(log["data"], 16) for log in receipt["logs"]
               if log["address"].lower() == USDC.lower() and [x.lower() for x in log["topics"]] == topics]
    if matched != [AMOUNT]:
        raise ValueError("funding receipt does not show the exact 1 USDC transfer")
    print(json.dumps({**{k: v for k, v in state.items() if k != "raw"},
                      "block": int(receipt["blockNumber"], 16), "status": "mined",
                      "payout_balance_after_atomic": token_balance(PAYOUT_SENDER)}, indent=2))


if __name__ == "__main__":
    main()
