#!/usr/bin/env python3
"""Register this domain's agents in the ERC-8004 IdentityRegistry on Base mainnet.

    .venv/bin/python deploy/erc-8004/register.py --key-file ~/.aicom-base-deployer-v4.json            # dry run
    .venv/bin/python deploy/erc-8004/register.py --key-file ~/.aicom-base-deployer-v4.json --send     # send

One `register(string agentURI)` per agent in build.AGENTS, agentURI =
https://modelmarket.dev/.well-known/erc-8004/<slug>.json. The dry run estimates gas and Base's L1
data fee for every transaction and refuses to send if the wallet cannot pay for all of them. A
slug already in ids.json is skipped, and a registration that was sent but never confirmed (its
hash is written to pending.json before sending) is settled before anything new goes out, so a
rerun never registers an agent twice. The key is read
from the key file into this process and never printed; transactions are signed here and only the
raw signed bytes leave it. Run build.py afterwards to put the agentIds into the files.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

from eth_account import Account
from eth_utils import keccak

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import AGENTS, BASE  # noqa: E402

RPC = "https://mainnet.base.org"
CHAIN_ID = 8453
REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
GAS_ORACLE = "0x420000000000000000000000000000000000000F"   # OP-stack GasPriceOracle
REGISTERED = "0x" + keccak(text="Registered(uint256,string,address)").hex()


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json",
                                                          "user-agent": "aicom-erc8004/1.0"})
    out = json.load(urllib.request.urlopen(req, timeout=30))
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def register_calldata(uri: str) -> str:
    # register(string): selector + offset (0x20) + length + utf-8 bytes padded to 32
    sel = keccak(text="register(string)")[:4]
    raw = uri.encode()
    pad = (32 - len(raw) % 32) % 32
    return "0x" + (sel + (32).to_bytes(32, "big") + len(raw).to_bytes(32, "big") + raw + b"\0" * pad).hex()


def l1_fee(raw_tx: bytes) -> int:
    # getL1Fee(bytes)
    sel = keccak(text="getL1Fee(bytes)")[:4]
    pad = (32 - len(raw_tx) % 32) % 32
    data = "0x" + (sel + (32).to_bytes(32, "big") + len(raw_tx).to_bytes(32, "big") + raw_tx + b"\0" * pad).hex()
    return int(rpc("eth_call", [{"to": GAS_ORACLE, "data": data}, "latest"]), 16)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()

    accounts = json.load(open(os.path.expanduser(args.key_file)))["accounts"]
    acct = Account.from_key(accounts[0]["private_key"])
    del accounts
    ids_path = os.path.join(HERE, "ids.json")
    ids = json.load(open(ids_path)) if os.path.exists(ids_path) else {}
    pending_path = os.path.join(HERE, "pending.json")
    pending = json.load(open(pending_path)) if os.path.exists(pending_path) else {}
    # A registration sent but never confirmed is settled first. Without this a rerun after a poll
    # timeout or an RPC error took a fresh nonce and registered the same agent a second time.
    for slug, p in list(pending.items()):
        receipt = rpc("eth_getTransactionReceipt", [p["tx"]])
        if not receipt:
            sys.exit(f"refusing: {slug} has a sent registration with no receipt yet ({p['tx']}); "
                     f"wait for it, or delete {slug} from pending.json once it is known to be dropped")
        if receipt["status"] == "0x1":
            record(ids, ids_path, slug, p["uri"], p["tx"], receipt)
        else:
            print(f"  {slug}: earlier registration {p['tx']} reverted; it will be sent again")
        del pending[slug]
        save(pending_path, pending)

    todo = [s for s in AGENTS if s not in ids]
    balance = int(rpc("eth_getBalance", [acct.address, "latest"]), 16)
    nonce = int(rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    base_fee = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
    prio = int(rpc("eth_maxPriorityFeePerGas", []), 16)
    max_fee = base_fee * 2 + prio
    print(f"from {acct.address}  balance {balance / 1e18:.9f} ETH  nonce {nonce}  "
          f"baseFee {base_fee} wei  to register: {todo or 'nothing'}")

    plan, total = [], 0
    for i, slug in enumerate(todo):
        uri = f"{BASE}/{slug}.json"
        data = register_calldata(uri)
        gas = int(int(rpc("eth_estimateGas", [{"from": acct.address, "to": REGISTRY, "data": data}]), 16) * 1.25)
        tx = {"chainId": CHAIN_ID, "nonce": nonce + i, "to": REGISTRY, "value": 0, "data": data, "gas": gas,
              "maxFeePerGas": max_fee, "maxPriorityFeePerGas": prio, "type": 2}
        signed = acct.sign_transaction(tx)
        raw = bytes(signed.raw_transaction)
        cost = gas * max_fee + l1_fee(raw)
        total += cost
        plan.append((slug, uri, raw, "0x" + bytes(signed.hash).hex()))
        print(f"  {slug:<13} gas<= {gas}  worst-case cost {cost / 1e18:.9f} ETH  uri {uri}")
    print(f"worst-case total {total / 1e18:.9f} ETH of {balance / 1e18:.9f}")
    if total > balance:
        sys.exit("refusing: the wallet cannot pay for every registration")
    if not args.send:
        print("dry run — nothing sent")
        return

    for slug, uri, raw, tx_hash in plan:
        # Recorded BEFORE sending: if the send call errors after the node accepted it, the hash
        # is still known, and the next run settles it instead of registering again.
        pending[slug] = {"tx": tx_hash, "uri": uri}
        save(pending_path, pending)
        rpc("eth_sendRawTransaction", ["0x" + raw.hex()])
        print(f"  {slug}: sent {tx_hash}", flush=True)
        receipt = None
        for _ in range(60):
            receipt = rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
            time.sleep(2)
        if not receipt:
            sys.exit(f"  {slug}: not mined after 2 minutes; rerun later to settle {tx_hash} (kept in pending.json)")
        if receipt["status"] != "0x1":
            del pending[slug]
            save(pending_path, pending)
            sys.exit(f"  {slug}: transaction reverted: {tx_hash}")
        record(ids, ids_path, slug, uri, tx_hash, receipt)
        del pending[slug]
        save(pending_path, pending)


def save(path, value) -> None:
    with open(path, "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def record(ids, ids_path, slug, uri, tx_hash, receipt) -> None:
    agent_id = next(int(log["topics"][1], 16) for log in receipt["logs"]
                    if log["address"].lower() == REGISTRY.lower() and log["topics"][0] == REGISTERED)
    ids[slug] = agent_id
    save(ids_path, ids)
    with open(os.path.join(HERE, "registrations.log"), "a") as f:
        f.write(json.dumps({"slug": slug, "agentId": agent_id, "tx": tx_hash, "uri": uri,
                            "block": int(receipt["blockNumber"], 16)}) + "\n")
    print(f"  {slug}: agentId {agent_id}  block {int(receipt['blockNumber'], 16)}")


if __name__ == "__main__":
    main()
