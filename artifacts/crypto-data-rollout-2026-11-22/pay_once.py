"""One live paid call to the hearth's x402-seller agent, run by the owner on their own Mac.

    ~/Desktop/ai_tests/aicompany/aicom/.venv/bin/python pay_once.py

Pays exactly 3000 USDC units ($0.003) on Base from index 1 of ~/.aicom-base-deployer-v4.json (the buyer
address used for the 2026-10-05 Bazaar payments) to the treasury 0x1218…Ad0a, with the EIP-3009
authorization the hearth's 402 binds to this call; then calls the agent, calls it again (the same answer is
redelivered) and sends another request on the same payment (it must be refused). Refuses any other price,
recipient, chain or token before anything is signed. Prints no key, mnemonic or payment secret.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hestia-agents"))
from eth_account import Account  # noqa: E402

from hestia_agents.x402 import calldata, redeem_by, typed_data  # noqa: E402

HEARTH = "https://hestia.modelmarket.dev/t/x402-seller/invoke"
RPC = "https://base-rpc.publicnode.com"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TREASURY = "0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a"
PRICE_UNITS = 3000
KEYFILE = Path.home() / ".aicom-base-deployer-v4.json"
# Written (mode 0600) before the payment is sent, so a run cut short can still redeem what it paid.
STATE = Path.home() / ".aicom-pay-once-x402-seller.json"
RECEIPT_RPCS = ("https://mainnet.base.org", "https://base.meowrpc.com", "https://base-rpc.publicnode.com")
PAYLOAD = {"pay_to": "0x5FBbbCbF2Ade44F5c604E5E55f11945E1ADdD231", "days": 1, "to_block": 60800000}
OTHER = {"pay_to": "0x6b5aF9924f4CD35643c11a9fd1C983f77261A6E1", "days": 1, "to_block": 60800000}


def post(url, body, headers=None, attempts=4):
    """POST with retries on network failures (2026-11-22: connections from this Mac to the hearth
    sometimes hung for up to 70 s). Safe after paying too: the hearth redelivers a paid call."""
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
        except urllib.error.HTTPError as e:
            raw = e.read() or b"{}"
            try:
                return e.code, json.loads(raw), dict(e.headers)
            except ValueError:  # an RPC's 429 or 5xx page, not JSON
                return e.code, {"error": raw[:200].decode("utf-8", "replace")}, dict(e.headers)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt + 1 == attempts:
                raise SystemExit(f"{url.split('/')[2]} did not answer after {attempts} tries ({e})")
            print(f"  {url.split('/')[2]}: no answer ({type(e).__name__}), retrying")
            time.sleep(3)


def rpc(method, params):
    _, body, _ = post(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in body:
        raise SystemExit(f"RPC {method} refused: {body['error']}")
    return body["result"]


def receipt_of(tx_hash):
    """The receipt from the first RPC that has it; None while none does (an RPC error is not fatal)."""
    for url in RECEIPT_RPCS:
        try:
            _, body, _ = post(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt",
                                    "params": [tx_hash]}, attempts=1)
        except SystemExit:
            continue
        if body.get("result"):
            return body["result"]
    return None


def redeem(tx_hash, secret):
    paid = {"X-Payment": tx_hash, "X-Payment-Secret": secret}
    for _ in range(60):
        receipt = receipt_of(tx_hash)
        if receipt:
            break
        time.sleep(2)
    else:
        raise SystemExit(f"no receipt yet for {tx_hash}; run again later: it redeems from {STATE}")
    print(f"mined in block {int(receipt['blockNumber'], 16)}, status {receipt['status']}")
    for _ in range(30):
        status, answer, headers = post(HEARTH, PAYLOAD, paid)
        if status != 409:
            break
        time.sleep(int(headers.get("Retry-After", "3")))
    print(f"call: {status} {json.dumps(answer.get('result', answer))[:160]}")
    again = post(HEARTH, PAYLOAD, paid)
    print(f"same call again: {again[0]}, same answer: {again[1] == answer}")
    other = post(HEARTH, OTHER, paid)
    print(f"another request on this payment: {other[0]} {json.dumps(other[1])[:120]}")
    print(f"tx {tx_hash}")
    if status == 200:
        STATE.unlink(missing_ok=True)


def buyer():
    doc = json.loads(KEYFILE.read_text())
    phrase = doc.get("mnemonic") or doc.get("phrase")
    if isinstance(phrase, dict):
        phrase = phrase.get("phrase")
    if not isinstance(phrase, str):
        raise SystemExit(f"{KEYFILE} holds no mnemonic (fields: {sorted(doc)})")
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(phrase, account_path="m/44'/60'/0'/0/1")


def main():
    if STATE.exists():
        saved = json.loads(STATE.read_text())
        print(f"redeeming the payment a previous run sent: {saved['tx']}")
        return redeem(saved["tx"], saved["secret"])
    acct = buyer()
    me = acct.address
    usdc = int(rpc("eth_call", [{"to": USDC, "data": "0x70a08231" + me[2:].lower().zfill(64)}, "latest"]), 16)
    eth = int(rpc("eth_getBalance", [me, "latest"]), 16)
    print(f"buyer {me}: {usdc / 1e6} USDC, {eth / 1e18:.6f} ETH")
    if usdc < PRICE_UNITS or eth < 2 * 10**12:
        raise SystemExit("not enough USDC or ETH for gas on the buyer address; nothing was sent")

    status, quote, _ = post(HEARTH, PAYLOAD)
    accept = (quote.get("accepts") or [{}])[0]
    terms = (status, str(quote.get("pay_to", "")).lower(), str(quote.get("amount_units")),
             accept.get("network"), str((accept.get("extra") or {}).get("verifyingContract", "")).lower())
    if terms != (402, TREASURY, str(PRICE_UNITS), "base", USDC.lower()):
        raise SystemExit(f"unexpected terms, nothing signed: {terms}")
    secret = quote["payment_secret"]
    print(f"402: pay {quote['amount_usd']} USDC to {quote['pay_to']}, nonce {quote['nonce'][:18]}…")

    td = typed_data(quote, sender=me, valid_before=redeem_by(quote))
    signable = json.loads(json.dumps(td))
    for k in ("value", "validAfter", "validBefore"):
        signable["message"][k] = int(signable["message"][k])
    signable["types"] = {"EIP712Domain": [
        {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
        **{k: v for k, v in signable["types"].items() if k != "EIP712Domain"}}
    sig = acct.sign_typed_data(full_message=signable).signature.hex()
    data = calldata(td, sig if sig.startswith("0x") else "0x" + sig)

    tip = int(rpc("eth_maxPriorityFeePerGas", []), 16)
    base = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
    tx = {"to": USDC, "data": data, "value": 0, "chainId": 8453,
          "nonce": int(rpc("eth_getTransactionCount", [me, "pending"]), 16),
          "maxPriorityFeePerGas": tip, "maxFeePerGas": 2 * base + tip}
    tx["gas"] = int(int(rpc("eth_estimateGas", [{"from": me, "to": USDC, "data": data}]), 16) * 1.3)
    signed_tx = acct.sign_transaction(tx)
    tx_hash = "0x" + signed_tx.hash.hex().removeprefix("0x")
    STATE.touch(mode=0o600)
    STATE.write_text(json.dumps({"tx": tx_hash, "secret": secret, "nonce": quote["nonce"]}))
    raw = signed_tx.raw_transaction.hex()
    sent = rpc("eth_sendRawTransaction", [raw if raw.startswith("0x") else "0x" + raw])
    if sent.lower() != tx_hash.lower():
        raise SystemExit(f"the RPC reports {sent}, not {tx_hash}; {STATE} names the one signed")
    print(f"sent {tx_hash}; waiting for the receipt")
    redeem(tx_hash, secret)


if __name__ == "__main__":
    main()
