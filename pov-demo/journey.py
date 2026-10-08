#!/usr/bin/env python3
"""The stranger's journey, on a schedule: a buyer that knows only what the hub publishes.

    python3 pov-demo/journey.py --hub https://uni.modelmarket.dev --rpc http://172.17.0.1:8546 \
        --publish /var/www/verify.modelmarket.dev/uni-journey.json

Every end-to-end script this ecosystem had read its addresses from its own constants, so none
of them could notice that the hub stopped publishing something a real buyer needs. On
2026-10-03 three such gaps were found by hand in one afternoon: no escrow debit address in the
well-known, new publishers invisible for a week, escrow debits not reaching the chain. This runs
the whole buyer path against the UNI bubble (virtual money, the same code as the live hub) using
nothing but the hub's public documents, and publishes a status the alerter reads.

Steps, each a check (critical unless noted):
  well_known_contracts   the hub declares escrow, escrow_hub and token
  offer_found            the catalogue has a channel-payable offer with a runnable example
  wallet_funded          the journey wallet holds a deposit (minted in the bubble if not; UNI only)
  channel_opened         openChannel on chain + /channel/open accepted
  invoke_paid            a signed, paid invoke returned the provider's result
  ledger_closed          /channel/close accounted the call
  debit_on_chain         the hub's collector debited the channel on chain (within 10 min)
  refund_on_settle       settleChannel returned the rest of the deposit
  close_requested        AIMarketEscrowV2 only: requestClose accepted. A V2 depositor settles
                         only after SETTLE_WINDOW (an hour), so the NEXT run settles this
                         channel — found from its ChannelOpened log, no state file — and
                         reports refund_on_settle for it. The bubble clock is never moved.

The wallet is Anvil account #3 of the public test mnemonic: a bubble-only key, worthless outside.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buyer as b  # noqa: E402  (reused plumbing: rpc, Wallet, channel, units, http)
from eth_abi import encode  # noqa: E402
from eth_account import Account  # noqa: E402
from eth_utils import keccak  # noqa: E402

JOURNEY_KEY = "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"   # Anvil #3
DEPOSIT = 1.00
OPENED_TOPIC = "0x" + keccak(text="ChannelOpened(bytes32,address,address,uint256,uint256)").hex()
# Runs are 6 h apart; this many blocks back covers several of them at any bubble block time.
LOG_LOOKBACK_BLOCKS = 200_000


class Run:
    def __init__(self):
        self.checks: list[dict] = []

    def check(self, name: str, ok: bool, detail: str, critical: bool = True) -> bool:
        self.checks.append({"name": name, "ok": bool(ok), "critical": critical, "detail": detail[:300]})
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")
        return ok


def pick_offer(hub: str) -> dict | None:
    _, doc = b.http("GET", f"{hub}/ai-market/v2/manifest?limit=200")
    offers = [t for t in doc.get("tools") or [] if t.get("offerable")
              and float(t.get("routed_price_usd") or t.get("price_per_call_usd") or 0) > 0
              and t.get("capability_id") != "pipeline.run@v1"
              and isinstance((t.get("input_schema") or {}).get("examples"), list)]
    offers.sort(key=lambda t: (float(t.get("routed_price_usd") or t["price_per_call_usd"]), t["capability_id"]))
    return offers[0] if offers else None


def settle_earlier_channels(escrow: str, token: str, w: "b.Wallet", run: Run) -> None:
    """V2: settle this wallet's channels from earlier runs whose settle window is over."""
    if not b.channel(escrow, bytes(32))["v2"]:
        return
    try:
        latest = int(b.rpc("eth_blockNumber", []), 16)
        logs = b.rpc("eth_getLogs", [{"address": escrow, "toBlock": "latest",
                                      "fromBlock": hex(max(0, latest - LOG_LOOKBACK_BLOCKS)),
                                      "topics": [OPENED_TOPIC, None, "0x" + "0" * 24 + w.address[2:].lower()]}])
        now = b.chain_time()
    except Exception as exc:
        run.check("earlier_channels_found", False, f"{type(exc).__name__}: {exc}", critical=False)
        return
    for entry in logs or []:
        ch = bytes.fromhex(entry["topics"][1][2:])
        st = b.channel(escrow, ch)
        if st["status"] != 0 or not st["closable_at"] or st["closable_at"] > now:
            continue
        before = b.balance_of(token, w.address)
        w.send(escrow, b.sel("settleChannel(bytes32)") + encode(["bytes32"], [ch]), "settleChannel (earlier run)")
        refunded = b.balance_of(token, w.address) - before
        run.check("refund_on_settle", refunded == st["balance"],
                  f"earlier channel 0x{ch.hex()[:10]}…: refunded {refunded / 1e6:.6f} of {st['balance'] / 1e6:.6f}")


def journey(hub: str, run: Run, mint: bool) -> None:
    _, wk = b.http("GET", f"{hub}/.well-known/ai-market.json")
    roles = {e["role"]: e["address"] for e in (wk.get("contracts") or {}).get("entries", [])}
    if not run.check("well_known_contracts", all(r in roles for r in ("escrow", "escrow_hub", "token")),
                     f"declared roles: {sorted(roles)}"):
        return
    escrow, escrow_hub, token = roles["escrow"], roles["escrow_hub"], roles["token"]
    offer = pick_offer(hub)
    if not run.check("offer_found", offer is not None,
                     f"{offer['product_id']}/{offer['capability_id']} @ ${offer.get('routed_price_usd') or offer['price_per_call_usd']}"
                     if offer else "no paid, channel-payable offer with an example"):
        return
    price = float(offer.get("routed_price_usd") or offer["price_per_call_usd"])

    w = b.Wallet(JOURNEY_KEY)
    settle_earlier_channels(escrow, token, w, run)
    need = b.units(DEPOSIT)
    if b.balance_of(token, w.address) < need and mint:
        w.send(token, b.sel("mint(address,uint256)") + encode(["address", "uint256"], [w.address, need * 10]),
               "mint (bubble only)")
    if not run.check("wallet_funded", b.balance_of(token, w.address) >= need,
                     f"{b.balance_of(token, w.address) / 1e6:.2f} on {w.address}"):
        return

    ch = secrets.token_bytes(32)
    ch_hex = "0x" + ch.hex()
    allowance = b.decode(["uint256"], b.call(token, b.sel("allowance(address,address)")
                                           + encode(["address", "address"], [w.address, escrow])))[0]
    if allowance < need:
        w.send(token, b.sel("approve(address,uint256)") + encode(["address", "uint256"], [escrow, need * 100]), "approve")
    w.send(escrow, b.sel("openChannel(bytes32,address,uint256)") + encode(["bytes32", "address", "uint256"], [ch, token, need]),
           "openChannel")
    body = {"deposit_usd": DEPOSIT, "token": "USDC", "chain": "base", "wallet": w.address, "escrow_channel_id": ch_hex}
    status, opened = b.http("POST", f"{hub}/ai-market/v2/channel/open", body)
    if status != 200 and opened.get("challenge"):
        body["payer_signature"] = w.sign_text(opened["challenge"])
        status, opened = b.http("POST", f"{hub}/ai-market/v2/channel/open", body)
    chan = opened.get("channel") or opened
    ledger_id, secret = chan.get("channel_id") or opened.get("channel_id"), chan.get("channel_secret") or opened.get("channel_secret")
    if not run.check("channel_opened", status == 200 and bool(ledger_id), f"/channel/open {status}"):
        return

    nonce = b.channel(escrow, ch)["nonce"]
    rid = "0x" + secrets.token_hex(32)
    deadline = int(time.time()) + 3600
    auth = b.DebitAuthorization(channel_id=ch_hex, hub=escrow_hub, token=token, amount=b.units(price),
                                receipt_id=rid, nonce=nonce, deadline=deadline)
    sig = Account._sign_hash(b.debit_digest(auth, chain_id=b.CHAIN_ID, verifying_contract=escrow), w.acct.key).signature.hex()
    authorization = {"channelId": ch_hex, "hub": escrow_hub, "token": token, "amount": str(b.units(price)),
                     "receiptId": rid, "nonce": nonce, "deadline": deadline, "signature": sig if sig.startswith("0x") else "0x" + sig}
    headers = {"X-Payment-Channel": ledger_id, "X-Payment-Channel-Secret": secret or ""}
    status, result = b.http("POST", f"{hub}/ai-market/v2/invoke", {
        "product_id": offer["product_id"], "capability_id": offer["capability_id"],
        "source_hub": offer.get("source_hub") or "local",
        "input": offer["input_schema"]["examples"][0], "payment_authorization": authorization}, headers)
    run.check("invoke_paid", status == 200 and result.get("success") is not False,
              f"HTTP {status} {json.dumps(result)[:160] if status != 200 else ''}")

    status, closed = b.http("POST", f"{hub}/ai-market/v2/channel/close", {"channel_id": ledger_id, "wallet": w.address}, headers)
    run.check("ledger_closed", status == 200, f"used ${closed.get('used_usd')} refund ${closed.get('refund_usd')}")

    used = 0
    for _ in range(60):           # the collector runs on a timer inside the hub
        used = b.channel(escrow, ch)["used"]
        if used > 0:
            break
        time.sleep(10)
    run.check("debit_on_chain", used > 0, f"used {used / 1e6:.6f} on chain")
    closable_at = b.request_close(escrow, w, ch, [])
    if closable_at:
        run.check("close_requested", True, f"closable at {closable_at}; a later run settles it")
        return
    before = b.balance_of(token, w.address)
    w.send(escrow, b.sel("settleChannel(bytes32)") + encode(["bytes32"], [ch]), "settleChannel")
    refunded = b.balance_of(token, w.address) - before
    run.check("refund_on_settle", refunded == need - used, f"refunded {refunded / 1e6:.6f} of {need / 1e6:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default="https://uni.modelmarket.dev")
    ap.add_argument("--rpc", default="http://172.17.0.1:8546")
    ap.add_argument("--chain-id", type=int, default=31337)
    ap.add_argument("--publish", default="")
    ap.add_argument("--no-mint", action="store_true", help="never mint (anything but the UNI bubble)")
    args = ap.parse_args()
    b.RPC, b.CHAIN_ID = args.rpc, args.chain_id
    run = Run()
    try:
        journey(args.hub.rstrip("/"), run, mint=not args.no_mint)
    except Exception as exc:  # a crash is a failed journey, reported like one
        run.check("journey_completed", False, f"{type(exc).__name__}: {exc}")
    ok = all(c["ok"] for c in run.checks if c["critical"]) and bool(run.checks)
    report = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hub": args.hub,
              "ok": ok, "checks": run.checks}
    if args.publish:
        tmp = Path(args.publish + ".tmp")
        tmp.write_text(json.dumps(report, indent=1))
        tmp.replace(args.publish)
    print("VERDICT:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
