#!/usr/bin/env python3
"""Pay a hub credits top-up from your own wallet, end to end (docs: aimarket-hub/docs/credits-topup.md).

Two steps, so the account key and the wallet key never have to sit on the same machine:

  1. Quote — whoever holds the ACCOUNT's API key asks the hub for terms (valid 15 minutes):

       python3 scripts/credits_topup_pay.py quote --hub https://hub.example \\
           --api-key-file account.key --amount 1 --out quote.json

  2. Pay — whoever holds the WALLET signs and sends it. Without --yes nothing is signed or sent:
     it prints what would be paid, from which address, to whom, on which chain.

       python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key
       python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key --yes

What `pay --yes` does: signs an EIP-3009 transferWithAuthorization over the quote's nonce (from your
wallet, to the hub's payTo, exactly the quoted amount), sends that transaction itself (you pay the
gas — the hub holds no key and submits nothing), waits for the hub's confirmations, then asks the
hub to credit it. The hub checks it on chain: the authorization for THIS nonce, the transfer right
after it, to its own wallet, never credited before. The credit goes to the account that asked for
the quote, whoever paid.

Plain transfers (a wallet app, no quote) are credited too, once the sending wallet is linked to the
account — on hubs whose well-known shows payment_rails.credits.topup.deposit_watch.enabled:

       python3 scripts/credits_topup_pay.py link --hub https://hub.example \
           --api-key-file account.key --ask

`link` signs the hub's link message with the wallet (a signature, not a transaction: nothing is
spent) and registers it; any transfer from that wallet already waiting at the hub is credited then.

The wallet key file holds a 0x-hex private key, or JSON with "private_key". It is read, used and
never printed. --wallet-key-env NAME reads it from an environment variable instead.
Needs eth_account (pip install eth-account).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aimarket-agent"))
from aimarket_agent.topup import calldata, typed_data  # noqa: E402

UA = {"User-Agent": "aicom-credits-topup/1", "Content-Type": "application/json"}
DEFAULT_RPCS = ("https://mainnet.base.org", "https://base.drpc.org", "https://base-rpc.publicnode.com")


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:400]}


class Rpc:
    def __init__(self, urls: list[str]):
        self.urls = urls

    def __call__(self, method: str, params: list):
        last = "no RPC answered"
        for _round in range(4):
            for url in self.urls:
                try:
                    status, out = http("POST", url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                except (urllib.error.URLError, TimeoutError) as exc:
                    last = str(exc)
                    continue
                if "result" in out:
                    return out["result"]
                last = str(out.get("error") or status)
            time.sleep(3)
        raise RuntimeError(f"{method}: {last}")


def read_secret(path: str | None, env: str | None, ask: str = "") -> str:
    if ask:
        import getpass

        raw = getpass.getpass(ask).strip()          # typed, never echoed or stored
    elif env:
        raw = os.environ.get(env, "").strip()
    else:
        try:
            raw = Path(path).read_text().strip()
        except OSError as exc:
            sys.exit(f"cannot read the key file {path!r}: {exc.strerror}. "
                     "Pass the real path, or use --ask to type the key instead.")
    if raw.startswith("{"):
        doc = json.loads(raw)
        raw = str(doc.get("private_key") or doc.get("api_key") or "").strip()
    if "=" in raw and not raw.startswith("0x"):          # KEY=value / url=key lines
        raw = raw.rsplit("=", 1)[1].strip()
    if not raw:
        sys.exit("the secret is empty")
    return raw


def cmd_quote(args) -> int:
    key = read_secret(args.api_key_file, args.api_key_env)
    status, body = http("POST", f"{args.hub.rstrip('/')}/ai-market/v2/account/topup",
                        {"amount_usd": args.amount}, {"X-API-Key": key})
    if status != 402 or not body.get("nonce"):
        print(json.dumps(body, indent=2)[:1500])
        sys.exit(f"the hub did not quote (HTTP {status})")
    body["_hub"] = args.hub.rstrip("/")
    Path(args.out).write_text(json.dumps(body, indent=2))
    t = body.get("topup", {})
    print(f"quote saved to {args.out}: ${t.get('amount_usd')} to {t.get('pay_to')} on {t.get('network')}, "
          f"nonce {body['nonce'][:12]}…, offered until {time.strftime('%H:%M:%S', time.localtime(body.get('expires_at', 0)))}")
    return 0


def cmd_pay(args) -> int:
    from eth_account import Account
    from eth_utils import to_checksum_address

    offer = json.loads(Path(args.quote).read_text())
    topup = offer.get("topup") or {}
    hub = offer.get("_hub") or args.hub
    accept = offer["accepts"][0]
    chain_id = int(topup.get("chain_id") or accept["extra"]["chainId"])
    asset = to_checksum_address(accept["asset"])
    amount_units = int(accept["maxAmountRequired"])
    try:
        account = Account.from_key(read_secret(
            args.wallet_key_file, args.wallet_key_env,
            "wallet private key (hidden, not stored): " if args.ask else ""))
    except ValueError:
        sys.exit("that is not a private key (64 hex digits, with or without 0x)")
    rpc = Rpc(args.rpc or list(DEFAULT_RPCS))

    if int(rpc("eth_chainId", []), 16) != chain_id:
        sys.exit(f"the RPC is not chain {chain_id}")
    usdc = int(rpc("eth_call", [{"to": asset, "data": "0x70a08231" + account.address[2:].lower().rjust(64, "0")}, "latest"]), 16)
    eth = int(rpc("eth_getBalance", [account.address, "latest"]), 16)
    expires = float(offer.get("expires_at") or 0)
    print(f"hub          {hub}")
    print(f"pay          {amount_units / 1e6:.2f} USDC  →  {accept['payTo']}  (chain {chain_id})")
    print(f"from         {account.address}   balance {usdc / 1e6:.6f} USDC, {eth / 1e18:.6f} ETH")
    print(f"quote nonce  {offer['nonce']}  (offered for {max(0, int(expires - time.time()))} s more)")
    print(f"credited to  the account that asked for the quote, after {topup.get('min_confirmations', 2)} confirmations")
    if usdc < amount_units:
        sys.exit("not enough USDC in this wallet")
    if expires and time.time() > expires:
        sys.exit("the quote has expired: ask for a new one")
    if not args.yes:
        print("\nnothing signed or sent. Add --yes to pay.")
        return 0

    typed = typed_data(offer, sender=account.address, valid_before=int(time.time()) + 600)
    signature = Account.sign_typed_data(account.key, full_message=typed).signature.hex()
    data = calldata(typed, signature if signature.startswith("0x") else "0x" + signature)
    nonce = int(rpc("eth_getTransactionCount", [account.address, "pending"]), 16)
    base = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
    tip = 10_000_000
    tx = {"chainId": chain_id, "nonce": nonce, "to": asset, "value": 0, "data": data,
          "maxPriorityFeePerGas": tip, "maxFeePerGas": base * 2 + tip, "type": 2}
    tx["gas"] = int(int(rpc("eth_estimateGas", [{"from": account.address, "to": asset, "data": data}]), 16) * 1.3)
    if eth < tx["gas"] * tx["maxFeePerGas"]:
        sys.exit("not enough ETH for gas")
    raw = account.sign_transaction(tx).raw_transaction
    tx_hash = rpc("eth_sendRawTransaction", ["0x" + raw.hex().removeprefix("0x")])
    print(f"\nsent         {tx_hash}")
    need = int(topup.get("min_confirmations") or 2)
    receipt = None
    for _ in range(180):
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            if int(receipt["status"], 16) != 1:
                sys.exit(f"the transaction reverted: {tx_hash}")
            head = int(rpc("eth_blockNumber", []), 16)
            if head - int(receipt["blockNumber"], 16) + 1 >= need:
                break
        time.sleep(2)
    print(f"mined        block {int(receipt['blockNumber'], 16)}, {need}+ confirmations")
    redeem = topup.get("redeem_url") or f"{hub}/ai-market/v2/topups/{offer['nonce']}"
    for _ in range(10):
        status, body = http("POST", redeem, {"tx_hash": tx_hash})
        if status == 200:
            again = " (already credited before — not counted twice)" if body.get("idempotent_replay") else ""
            print(f"credited     ${body.get('credited_usd')} of ${body.get('paid_usd')} paid{again}")
            return 0
        if status in (409, 425, 429, 503) or body.get("retryable"):
            time.sleep(6)
            continue
        break
    print(json.dumps(body, indent=2)[:1200])
    print(f"\nthe money is on chain ({tx_hash}); redeem again later with:\n"
          f"  curl -X POST {redeem} -H 'content-type: application/json' -d '{{\"tx_hash\":\"{tx_hash}\"}}'")
    return 1


def cmd_link(args) -> int:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    hub = args.hub.rstrip("/")
    key = read_secret(args.api_key_file, args.api_key_env)
    status, known = http("GET", f"{hub}/.well-known/ai-market.json")
    watch = (((known.get("payment_rails") or {}).get("credits") or {}).get("topup") or {}).get("deposit_watch") or {}
    if status != 200 or not watch.get("enabled"):
        sys.exit(f"this hub does not credit plain transfers: {watch.get('reason') or f'HTTP {status}'}")
    status, me = http("GET", f"{hub}/ai-market/v2/account", headers={"X-API-Key": key})
    if status != 200 or not me.get("account_id"):
        sys.exit(f"the account key was refused (HTTP {status})")
    try:
        wallet = Account.from_key(read_secret(
            args.wallet_key_file, args.wallet_key_env,
            "wallet private key (hidden, not stored): " if args.ask else ""))
    except ValueError:
        sys.exit("that is not a private key (64 hex digits, with or without 0x)")
    issued = int(time.time())
    message = (watch["link_message"].replace("<account_id>", me["account_id"])
               .replace("<address>", wallet.address.lower()).replace("<unix seconds>", str(issued)))
    signature = wallet.sign_message(encode_defunct(text=message)).signature.hex()
    status, body = http("POST", f"{hub}/ai-market/v2/account/payer-wallets", {
        "address": wallet.address, "issued_at": issued,
        "signature": signature if signature.startswith("0x") else "0x" + signature}, {"X-API-Key": key})
    if status != 200:
        print(json.dumps(body, indent=2)[:1200])
        sys.exit(f"the hub did not link the wallet (HTTP {status})")
    print(f"linked       {wallet.address} → {me['account_id']} ({body.get('linked')})")
    print(f"pay to       {watch.get('wallet')}  — plain USDC transfers from this wallet are credited "
          f"within ~{watch.get('interval_s', 60)} s of their confirmations")
    if body.get("credited_now"):
        print(f"credited now {body['credited_now']} transfer(s) that were waiting")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quote", help="ask the hub for terms (needs the ACCOUNT key)")
    q.add_argument("--hub", required=True)
    q.add_argument("--amount", type=float, required=True, help="USD, whole cents, at least 1")
    q.add_argument("--api-key-file")
    q.add_argument("--api-key-env")
    q.add_argument("--out", default="quote.json")
    pay = sub.add_parser("pay", help="sign, send and redeem (needs the WALLET key)")
    pay.add_argument("--quote", required=True)
    pay.add_argument("--hub", default="")
    pay.add_argument("--wallet-key-file")
    pay.add_argument("--wallet-key-env")
    pay.add_argument("--ask", action="store_true", help="type the wallet key at a hidden prompt instead")
    pay.add_argument("--rpc", action="append", help="Base RPC URL (repeatable); defaults to three public ones")
    pay.add_argument("--yes", action="store_true", help="actually sign and send")
    ln = sub.add_parser("link", help="credit plain transfers from a wallet (needs BOTH keys; signs, spends nothing)")
    ln.add_argument("--hub", required=True)
    ln.add_argument("--api-key-file")
    ln.add_argument("--api-key-env")
    ln.add_argument("--wallet-key-file")
    ln.add_argument("--wallet-key-env")
    ln.add_argument("--ask", action="store_true", help="type the wallet key at a hidden prompt instead")
    args = p.parse_args(argv)
    if args.cmd in ("quote", "link") and not (args.api_key_file or args.api_key_env):
        p.error(f"{args.cmd} needs --api-key-file or --api-key-env")
    if args.cmd in ("pay", "link") and not (args.wallet_key_file or args.wallet_key_env or args.ask):
        p.error(f"{args.cmd} needs --ask, --wallet-key-file or --wallet-key-env")
    return {"quote": cmd_quote, "pay": cmd_pay, "link": cmd_link}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
