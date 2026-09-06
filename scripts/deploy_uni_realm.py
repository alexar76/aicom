"""Deploy the UNI realm's economy onto the bubble's own chain.

Speaks raw JSON-RPC with the artifacts forge already built (`contracts/evm/out`), so it
needs no forge on the target host — the prod host has none. Point it at the bubble chain
with UNI_RPC (default http://127.0.0.1:8546, the bubble's own Anvil; NOT 8545, which is the
alien-monitor demo chain that recycles itself).

Idempotent in the only sense that matters here: it always deploys fresh contracts and writes
their addresses out, so a chain that was wiped is one command from being whole again.

Accounts are Anvil's deterministic ones from the standard test mnemonic — the point of the
bubble is that its keys are worthless outside it, so they are written down on purpose:
  #0 deployer/owner, #1 the hub, #2 a buyer.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from eth_account import Account
from eth_utils import to_checksum_address

RPC = os.environ.get("UNI_RPC", "http://127.0.0.1:8546")
ROOT = Path(__file__).resolve().parents[1]

DEPLOYER = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
HUB = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
BUYER = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"


def rpc(method: str, params: list) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read())
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def artifact(path: str) -> dict:
    return json.loads((ROOT / "contracts/evm/out" / path).read_text())


def send(key: str, *, to: str | None, data: str, value: int = 0) -> dict:
    acct = Account.from_key(key)
    nonce = int(rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    tx = {
        "from": acct.address,
        "nonce": nonce,
        "gas": 6_000_000,
        "maxFeePerGas": 2_000_000_000,
        "maxPriorityFeePerGas": 1_000_000_000,
        "chainId": 31337,
        "value": value,
        "data": data,
    }
    if to:
        # eth-account rejects a non-checksummed address outright, and every address here
        # arrives lowercase from an RPC receipt.
        tx["to"] = to_checksum_address(to)
    signed = acct.sign_transaction(tx)
    tx_hash = rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex().removeprefix("0x")])
    for _ in range(60):
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            if int(receipt["status"], 16) != 1:
                raise RuntimeError(f"tx reverted: {tx_hash}")
            return receipt
        time.sleep(1)
    raise RuntimeError(f"tx not mined: {tx_hash}")


def encode_address_array(addresses: list[str]) -> str:
    """One dynamic address[] argument: offset, length, then the words."""
    head = (32).to_bytes(32, "big")
    body = len(addresses).to_bytes(32, "big")
    for a in addresses:
        body += bytes(12) + bytes.fromhex(a.lower().removeprefix("0x"))
    return (head + body).hex()


def selector(sig: str) -> str:
    from eth_utils import keccak

    return keccak(sig.encode())[:4].hex()


def main() -> int:
    print(f"chain id: {int(rpc('eth_chainId', []), 16)}  block: {int(rpc('eth_blockNumber', []), 16)}")
    hub_addr = Account.from_key(HUB).address
    buyer_addr = Account.from_key(BUYER).address
    print(f"hub: {hub_addr}\nbuyer: {buyer_addr}")

    # ── the bubble's dollar ───────────────────────────────────────────────
    token_bc = artifact("UniUSD.sol/UniUSD.json")["bytecode"]["object"]
    receipt = send(DEPLOYER, to=None, data=token_bc)
    token = receipt["contractAddress"]
    print(f"UniUSD:          {token}")

    # ── the escrow, with the hub and the token authorized at construction ──
    escrow_bc = artifact("AIMarketEscrow.sol/AIMarketEscrow.json")["bytecode"]["object"]
    args = encode_address_array([hub_addr])
    # Two dynamic arrays: offsets first, then each array's body.
    hubs = [hub_addr]
    tokens = [token]
    off1 = 64
    body1 = len(hubs).to_bytes(32, "big") + b"".join(bytes(12) + bytes.fromhex(a.lower()[2:]) for a in hubs)
    off2 = off1 + len(body1)
    body2 = len(tokens).to_bytes(32, "big") + b"".join(bytes(12) + bytes.fromhex(a.lower()[2:]) for a in tokens)
    ctor = (off1.to_bytes(32, "big") + off2.to_bytes(32, "big") + body1 + body2).hex()
    receipt = send(DEPLOYER, to=None, data=escrow_bc + ctor)
    escrow = receipt["contractAddress"]
    print(f"AIMarketEscrow:  {escrow}")

    # ── funding from nowhere: the UNI premise ─────────────────────────────
    amount = 10_000 * 10**6  # 10,000 UNI-dollars
    for who in (buyer_addr, hub_addr):
        data = "0x" + selector("mint(address,uint256)") + bytes(12).hex() + who.lower()[2:] + amount.to_bytes(32, "big").hex()
        send(DEPLOYER, to=token, data=data)
    print(f"minted {amount / 10**6:.0f} UNI-USD to the buyer and to the hub")

    # ── verify what we built, from the chain rather than from our own log ──
    def call(to: str, data: str) -> str:
        return str(rpc("eth_call", [{"to": to, "data": data}, "latest"]))

    dec = int(call(token, "0x" + selector("decimals()")), 16)
    bal = int(call(token, "0x" + selector("balanceOf(address)") + bytes(12).hex() + buyer_addr.lower()[2:]), 16)
    authorized = int(call(escrow, "0x" + selector("authorizedHubs(address)") + bytes(12).hex() + hub_addr.lower()[2:]), 16)
    sep = call(token, "0x" + selector("domainSeparator()"))
    print(f"decimals: {dec} | buyer balance: {bal / 10**6:.2f} | hub authorized in escrow: {bool(authorized)}")
    print(f"token domain separator: {sep}")

    out = {
        "network": "base", "kind": "evm", "chain_id": 31337,
        "display_name": "Base", "realm": "uni",
        "rpc": "http://host.docker.internal:8545",
        "owner_wallet": Account.from_key(DEPLOYER).address,
        "hub_wallet": hub_addr, "buyer_wallet": buyer_addr,
        "contracts": {"USDC": token, "AIMarketEscrow": escrow},
    }
    out_path = Path(os.environ.get("UNI_DEPLOYMENT_OUT", ROOT / "config/deployments/base-uni.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
