#!/usr/bin/env python3
"""A buyer agent hires two sellers it has never met and pays only for verified work.

    python3 pov-demo/buyer.py --key-file ~/.aicom-pov-buyer.json --n 1000009 --deposit 1.00 --yes

What it does, in the order a careful agent would:

1. The human's task and limit. The task is "factor N". The limit is the money the human put
   in this wallet and the deposit per seller: an escrow channel holds the deposit, and the
   agent cannot spend a cent more than it — the contract refuses.
2. Find sellers. It asks the hub for `math.factor@v1` and gets two offers from two
   publishers it has no history with.
3. Pay on verification, both of them. For each seller: open an escrow channel on Base, open
   the hub's ledger channel against it, sign a debit authorization for the price, and invoke
   with `verify: {requested: true, intent: …}`. The hub holds the price, the verifier judges
   the delivery against the intent, and the hold is captured (pass) or released (fail).
4. Settle. A passing seller is debited on chain by the hub (the escrow bridge submits the
   authorization); the agent then settles the channel and gets the remainder back. A failing
   seller is never debited, and settling returns the whole deposit.
5. Record everything: every transaction hash, the verdicts, the receipts, into a JSON run log
   (pov-demo/runs/) that docs/pay-on-verified-demo.md is written from.

Nothing moves without --yes. Raw JSON-RPC + eth_account (no web3); the key never leaves the
process and is never printed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from eth_abi import decode, encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_checksum_address

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "aimarket-hub"))
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization, debit_digest  # noqa: E402

HUB = "https://modelmarket.dev"
RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
CHAIN_ID = 8453
CAPABILITY = "math.factor@v1"
UA = {"user-agent": "pov-demo-buyer/1 (+https://modelmarket.dev)", "content-type": "application/json"}


def sel(sig: str) -> bytes:
    return keccak(text=sig)[:4]


# ── plumbing ──────────────────────────────────────────────────────────────────

def http(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 360):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:400]}


def rpc(method: str, params: list):
    for wait in (0, 2, 5, 10, 20, 30):
        time.sleep(wait)
        try:
            status, out = http("POST", RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30)
        except (urllib.error.URLError, TimeoutError):
            continue
        if status == 429 or "result" not in out:
            if "error" in out and status != 429:
                raise RuntimeError(f"{method}: {out['error']}")
            continue
        return out["result"]
    raise RuntimeError(f"{method}: RPC kept failing")


def call(to: str, data: bytes) -> bytes:
    return bytes.fromhex(rpc("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"])[2:])


class Wallet:
    def __init__(self, key: str):
        self.acct = Account.from_key(key)
        self.address = self.acct.address

    def send(self, to: str, data: bytes, label: str) -> dict:
        to = to_checksum_address(to)  # hubs may publish lower-case addresses; signers refuse them
        nonce = int(rpc("eth_getTransactionCount", [self.address, "pending"]), 16)
        base = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
        tip = 10_000_000  # 0.01 gwei; Base is cheap and this is not urgent
        tx = {"chainId": CHAIN_ID, "nonce": nonce, "to": to, "value": 0, "data": "0x" + data.hex(),
              "maxPriorityFeePerGas": tip, "maxFeePerGas": base * 2 + tip, "type": 2}
        tx["gas"] = int(int(rpc("eth_estimateGas", [{"from": self.address, "to": to, "data": tx["data"]}]), 16) * 1.3)
        raw = self.acct.sign_transaction(tx).raw_transaction
        txh = rpc("eth_sendRawTransaction", ["0x" + raw.hex()])
        for _ in range(90):
            rcpt = rpc("eth_getTransactionReceipt", [txh])
            if rcpt:
                ok = int(rcpt["status"], 16) == 1
                print(f"  {label}: {txh} {'ok' if ok else 'REVERTED'} (block {int(rcpt['blockNumber'], 16)})")
                if not ok:
                    raise RuntimeError(f"{label} reverted: {txh}")
                return {"step": label, "tx": txh, "block": int(rcpt["blockNumber"], 16)}
            time.sleep(2)
        raise RuntimeError(f"{label}: no receipt for {txh}")

    def sign_text(self, text: str) -> str:
        sig = self.acct.sign_message(encode_defunct(text=text)).signature.hex()
        return sig if sig.startswith("0x") else "0x" + sig


def units(usd: float) -> int:
    return math.ceil(round(usd * 100, 6)) * 10_000  # whole cents, 6-decimal USDC


def balance_of(token: str, who: str) -> int:
    return decode(["uint256"], call(token, sel("balanceOf(address)") + encode(["address"], [who])))[0]


def channel(escrow: str, ch: bytes) -> dict:
    raw = call(escrow, sel("getChannel(bytes32)") + encode(["bytes32"], [ch]))
    f = decode(["(address,address,address,uint256,uint256,uint256,uint256,uint256,uint8)"], raw)[0]
    return dict(zip(("depositor", "hub", "token", "deposit", "balance", "used", "expires", "nonce", "status"), f))


# ── the agent ─────────────────────────────────────────────────────────────────

def contracts(hub: str) -> dict:
    status, wk = http("GET", f"{hub}/.well-known/ai-market.json")
    pov = wk.get("pay_on_verified") or {}
    if not pov.get("enabled"):
        sys.exit(f"this hub does not offer Pay-on-Verified: {pov.get('reason')}")
    roles = {e["role"]: e["address"] for e in (wk.get("contracts") or {}).get("entries", [])}
    for need in ("escrow", "escrow_hub", "token"):
        if need not in roles:
            sys.exit(f"the hub declares no {need} address; cannot pay through escrow")
    return {"escrow": roles["escrow"], "escrow_hub": roles["escrow_hub"], "token": roles["token"],
            "verifier": pov.get("verifier"), "threshold": pov.get("score_threshold"),
            "appeal_window_s": pov.get("appeal_window_s", 0),
            # A pass is final only after the appeal window, and only then can the hub collect
            # the signature; it must still be valid. The channel itself lives 24 h.
            "auth_lifetime_s": int(min(max(float(pov.get("authorization_min_lifetime_s") or 3600), 3600) + 600, 23 * 3600))}


def find_sellers(hub: str) -> list[dict]:
    q = urllib.parse.urlencode({"intent": "prime factorization", "limit": "25"})
    _, doc = http("GET", f"{hub}/ai-market/v2/search?{q}")
    offers = [m for m in doc.get("matches") or [] if m.get("capability_id") == CAPABILITY]
    return sorted(offers, key=lambda m: m.get("product_id", ""))


def hire(hub: str, c: dict, w: Wallet, offer: dict, n: int, deposit: float, log: dict,
         existing_channel: str = "", existing_steps: list | None = None) -> dict:
    product, price = offer["product_id"], float(offer["price_per_call_usd"])
    run = {"seller": product, "publisher": offer.get("publisher_id"), "price_usd": price,
           "steps": list(existing_steps or [])}
    print(f"\n── {product} (${price}) ──")
    if existing_channel:
        ch = bytes.fromhex(existing_channel[2:])
        print(f"  resuming escrow channel {existing_channel}")
    else:
        ch = secrets.token_bytes(32)
        run["steps"].append(w.send(c["escrow"], sel("openChannel(bytes32,address,uint256)")
                                   + encode(["bytes32", "address", "uint256"], [ch, c["token"], units(deposit)]),
                                   f"openChannel ${deposit:.2f}"))
    run["escrow_channel"] = "0x" + ch.hex()
    body = {"deposit_usd": deposit, "token": "USDC", "chain": "base", "wallet": w.address,
            "escrow_channel_id": run["escrow_channel"]}
    for attempt in range(8):
        status, opened = http("POST", f"{hub}/ai-market/v2/channel/open", body)
        if status != 200 and opened.get("challenge"):
            body["payer_signature"] = w.sign_text(opened["challenge"])
            status, opened = http("POST", f"{hub}/ai-market/v2/channel/open", body)
        # The hub reads the chain through its own RPC node, which can be a block or two behind
        # the one that mined our openChannel: "no escrow channel … must call openChannel".
        if status == 200 or "no escrow channel" not in str(opened.get("error", "")):
            break
        time.sleep(5)
    if status != 200:
        raise RuntimeError(f"channel/open {status}: {opened}")
    chan = opened.get("channel") or opened
    ledger_id, secret = chan.get("channel_id") or opened.get("channel_id"), chan.get("channel_secret") or opened.get("channel_secret")
    run["ledger_channel"] = ledger_id

    nonce = channel(c["escrow"], ch)["nonce"]
    receipt_id = "0x" + secrets.token_hex(32)
    deadline = int(time.time()) + c["auth_lifetime_s"]
    auth = DebitAuthorization(channel_id=run["escrow_channel"], hub=c["escrow_hub"], token=c["token"],
                              amount=units(price), receipt_id=receipt_id, nonce=nonce, deadline=deadline)
    sig = Account._sign_hash(debit_digest(auth, chain_id=CHAIN_ID, verifying_contract=c["escrow"]), w.acct.key).signature.hex()
    authorization = {"channelId": run["escrow_channel"], "hub": c["escrow_hub"], "token": c["token"],
                     "amount": str(units(price)), "receiptId": receipt_id, "nonce": nonce, "deadline": deadline,
                     "signature": sig if sig.startswith("0x") else "0x" + sig}
    intent = (f"Return the prime factorization of {n}: a list of prime numbers whose product is exactly {n}.")
    invoke = {"product_id": product, "capability_id": CAPABILITY, "source_hub": "local", "input": {"n": n},
              "payment_authorization": authorization,
              "verify": {"requested": True, "intent": intent, "mode": "auto", "wait": True, "wait_timeout_s": 300}}
    t0 = time.time()
    status, result = http("POST", f"{hub}/ai-market/v2/invoke", invoke,
                          {"X-Payment-Channel": ledger_id, "X-Payment-Channel-Secret": secret or ""})
    run["invoke_status"], run["invoke_seconds"] = status, round(time.time() - t0, 1)
    run["delivered"] = result.get("result")
    run["verification"] = result.get("verification")
    # The signed work receipt: what HISTOR anchors, and what a reader verifies without us.
    run["receipt"] = result.get("receipt") or (result.get("result") or {}).get("receipt")
    run["receipt_id"] = receipt_id
    v = run["verification"] or {}
    print(f"  delivered {json.dumps(run['delivered'])[:90]}")
    print(f"  verdict: {v.get('verdict') or v.get('status')} score={v.get('verify_score')} "
          f"settled={v.get('settled')} reasons={v.get('delivery_reasons')}")
    status, closed = http("POST", f"{hub}/ai-market/v2/channel/close",
                          {"channel_id": ledger_id, "wallet": w.address},
                          {"X-Payment-Channel": ledger_id, "X-Payment-Channel-Secret": secret or ""})
    run["ledger_close"] = {"status": status, "body": closed}
    print(f"  ledger close: HTTP {status} {json.dumps(closed)[:220]}")
    log["runs"].append(run)
    return run


def settle(c: dict, w: Wallet, run: dict, wait_debit: bool) -> None:
    ch = bytes.fromhex(run["escrow_channel"][2:])
    if wait_debit:
        print(f"  waiting for the hub's on-chain debit of {run['seller']} (escrow bridge sweep)…")
        # A pass is provisional for the appeal window, then the sweep (every 15 min) collects.
        for _ in range(int((float(c.get("appeal_window_s") or 0) + 2400) / 10)):
            if channel(c["escrow"], ch)["used"] > 0:
                break
            time.sleep(10)
        else:
            raise RuntimeError("the hub never debited the channel on chain")
    st = channel(c["escrow"], ch)
    run["onchain_before_settle"] = {"used_units": st["used"], "balance_units": st["balance"], "hub": st["hub"]}
    step = w.send(c["escrow"], sel("settleChannel(bytes32)") + encode(["bytes32"], [ch]), "settleChannel")
    run["steps"].append(step)
    # Read the refund from the receipt's Transfer events, not a balance difference: two reads
    # can land on nodes a block apart and report a refund of zero.
    transfer = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
    logs = rpc("eth_getTransactionReceipt", [step["tx"]])["logs"]
    run["refunded_units"] = sum(int(l["data"], 16) for l in logs
                                if l["address"].lower() == c["token"].lower() and l["topics"][0] == transfer
                                and l["topics"][2][-40:].lower() == w.address[2:].lower())
    print(f"  refunded on chain: {run['refunded_units'] / 1e6:.6f} USDC, hub took {st['used'] / 1e6:.6f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key-file", default=os.path.expanduser("~/.aicom-pov-buyer.json"))
    ap.add_argument("--hub", default=HUB)
    ap.add_argument("--n", type=int, default=1000009)
    ap.add_argument("--deposit", type=float, default=1.00)  # the escrow MIN_DEPOSIT is $1.00
    ap.add_argument("--yes", action="store_true", help="actually move money")
    ap.add_argument("--only", default="", help="hire just this product (e.g. quickfactor)")
    args = ap.parse_args()
    hub = args.hub.rstrip("/")
    w = Wallet(json.loads(Path(args.key_file).read_text())["private_key"])
    c = contracts(hub)
    usdc, eth = balance_of(c["token"], w.address), int(rpc("eth_getBalance", [w.address, "latest"]), 16)
    offers = find_sellers(hub)
    if args.only:
        offers = [o for o in offers if o["product_id"] == args.only]
    print(f"buyer {w.address}: {usdc / 1e6:.6f} USDC, {eth / 1e18:.6f} ETH")
    print(f"hub escrow {c['escrow']} debited by {c['escrow_hub']}, verifier {c['verifier']}")
    print(f"task: factor {args.n}; limit ${args.deposit:.2f} per seller; sellers found: "
          + ", ".join(f"{o['product_id']} (${o['price_per_call_usd']}, {o.get('publisher_id')})" for o in offers))
    need = units(args.deposit) * len(offers)
    if len(offers) < (1 if args.only else 2):
        sys.exit("expected two sellers" if not args.only else f"no seller {args.only}")
    if usdc < need or eth < 50_000_000_000_000:
        sys.exit(f"fund the buyer first: needs {need / 1e6:.2f} USDC and ~0.00005 ETH")
    if not args.yes:
        print("\ndry run: nothing sent. Re-run with --yes to move money.")
        return 0
    log = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hub": hub, "buyer": w.address,
           "n": args.n, "deposit_usd": args.deposit, "contracts": c, "runs": [], "steps": []}
    allowance = decode(["uint256"], call(c["token"], sel("allowance(address,address)")
                                         + encode(["address", "address"], [w.address, c["escrow"]])))[0]
    if allowance < need:
        log["steps"].append(w.send(c["token"], sel("approve(address,uint256)")
                                   + encode(["address", "uint256"], [c["escrow"], need]), f"approve ${need / 1e6:.2f}"))
    for offer in offers:
        hire(hub, c, w, offer, args.n, args.deposit, log)
    for run in log["runs"]:
        print(f"\n── settle {run['seller']} ──")
        passed = (run.get("verification") or {}).get("verdict") == "passed"
        settle(c, w, run, wait_debit=passed)
    out = HERE / "runs" / f"{log['started_utc'].replace(':', '')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(log, indent=1))
    print(f"\nrun log: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
