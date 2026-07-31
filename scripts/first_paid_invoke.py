#!/usr/bin/env python3
"""first_paid_invoke.py — drive one real, paid capability invoke end-to-end.

The point of this script is a single verifiable fact: that an outside consumer can
pay this hub and get a signed result back. It walks the full protocol path —
discover → open channel against a real escrow deposit → signed DebitAuthorization
→ invoke → close → fetch receipt — and prints every intermediate response so a
failure names its own stage.

Escrow-funded channels require an EIP-712 DebitAuthorization on every paid invoke.
Pass either ``--private-key`` / ``$AIMARKET_DEPOSITOR_PRIVATE_KEY`` (script signs)
or a ready ``--payment-authorization`` JSON blob. The deposit ``openChannel`` tx
itself is still made by the operator outside this process.

Usage
-----
    ./scripts/first_paid_invoke.py --discover "posture" --category security

    # after cast send … openChannel …
    ./scripts/first_paid_invoke.py \\
        --capability skopos.security.posture@v1 \\
        --wallet 0xYourDepositor \\
        --escrow-channel 0x… \\
        --private-key "$AIMARKET_DEPOSITOR_PRIVATE_KEY"

Exit 0 only when a paid invoke actually settled off-chain (on-chain debit+settle
is still step 7 in docs/handoff-first-paid-invoke.md).
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

DEFAULT_HUB = "https://modelmarket.dev"
DEFAULT_ESCROW = "0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D"
DEFAULT_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_HUB_ADDR = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
DEFAULT_CHAIN_ID = 8453
DEFAULT_RPC = "https://mainnet.base.org"
TIMEOUT = 60
TOKEN_DECIMALS = 6
_UNITS_PER_CENT = 10 ** (TOKEN_DECIMALS - 2)


def call(
    method: str, url: str, payload: dict | None = None, headers: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "content-type": "application/json",
            "user-agent": "first-paid-invoke/1.1 (+https://modelmarket.dev)",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read() or b"{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body.decode("utf-8", "replace")[:500]}
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


def show(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:1800])


def usd_to_base_units(usd: float) -> int:
    cents = max(1, math.ceil(round(float(usd) * 100, 6)))
    return cents * _UNITS_PER_CENT


def preflight(hub: str) -> bool | None:
    """Report the hub's payment posture. None == unreachable, False == takes no money."""
    status, doc = call("GET", f"{hub}/.well-known/ai-market.json")
    if status != 200:
        print(f"hub unreachable: {status} {doc.get('error', '')}")
        return None
    channels = (doc.get("plugin_extensions", {}).get("aimarket-channels") or {}).get("channels", {})
    print(f"hub            : {doc.get('name')} v{doc.get('hub_version')}")
    print(f"capabilities   : {doc.get('capabilities_count')} local, "
          f"{doc.get('federated_capabilities_count')} federated")
    print(f"payment_configured : {doc.get('payment_configured')}")
    print(f"payment_testnet    : {doc.get('payment_testnet')}")
    print(f"channels.demo_mode : {channels.get('demo_mode')}")

    if not doc.get("payment_configured"):
        print("\npayment_configured is false: this hub cannot verify a deposit.")
        return False
    if channels.get("demo_mode"):
        print("\nchannels are in demo mode: a 'successful' invoke would prove nothing.")
        return False
    return True


def discover(hub: str, intent: str, budget: float | None, category: str | None) -> list[dict]:
    params = {"intent": intent, "limit": "10"}
    if budget is not None:
        params["budget"] = str(budget)
    if category:
        params["category"] = category
    status, doc = call("GET", f"{hub}/ai-market/v2/search?{urllib.parse.urlencode(params)}")
    if status != 200:
        show("discovery failed", doc)
        return []
    matches = doc.get("matches") or []
    print(f"\n{len(matches)} match(es) for {intent!r}"
          + (f" in category {category!r}" if category else ""))
    for m in matches:
        print(f"  {m.get('capability_id'):<46} ${m.get('price_per_call_usd')}  "
              f"trust={m.get('trust_score')}  product={m.get('product_id')}  "
              f"{(m.get('name') or '')[:40]}")
    return matches


def lookup_capability(hub: str, capability_id: str) -> dict | None:
    """Resolve price / product_id from public search (exact capability_id match)."""
    intents = (
        capability_id,
        capability_id.split(".", 1)[-1].split("@", 1)[0],
        capability_id.split(".", 1)[0],
    )
    for intent in intents:
        params = {"intent": intent, "limit": "25"}
        status, doc = call("GET", f"{hub}/ai-market/v2/search?{urllib.parse.urlencode(params)}")
        if status != 200:
            continue
        for m in doc.get("matches") or []:
            if m.get("capability_id") == capability_id:
                return m
    return None


def read_escrow_nonce(rpc: str, escrow: str, channel_id: str) -> int:
    """Read channels[id].nonce via cast (Foundry)."""
    import subprocess

    out = subprocess.check_output(
        [
            "cast",
            "call",
            escrow,
            "getChannel(bytes32)(address,address,address,uint256,uint256,uint256,uint256,uint256,uint8)",
            channel_id,
            "--rpc-url",
            rpc,
        ],
        text=True,
    )
    # 9 lines: depositor, hub, token, deposit, balance, used, expiresAt, nonce, status
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) < 9:
        raise RuntimeError(f"unexpected getChannel output: {out!r}")
    nonce_word = lines[7].split()[0]
    return int(nonce_word, 0)


def build_payment_authorization(
    *,
    escrow_channel: str,
    hub_addr: str,
    token: str,
    amount_units: int,
    nonce: int,
    private_key: str,
    escrow: str,
    chain_id: int,
    deadline: int | None = None,
    receipt_id: str | None = None,
) -> dict:
    """Sign an EIP-712 DebitAuthorization with the depositor key."""
    # Prefer in-tree helper when PYTHONPATH includes aimarket-hub; else inline digest via
    # eth_account typed data is riskier — import the package from the monorepo.
    repo_hub = os.path.join(os.path.dirname(__file__), "..", "aimarket-hub")
    if repo_hub not in sys.path:
        sys.path.insert(0, os.path.abspath(repo_hub))
    from eth_account import Account
    from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization, debit_digest

    rid = receipt_id or ("0x" + secrets.token_hex(32))
    dl = int(deadline if deadline is not None else time.time() + 3600)
    auth = DebitAuthorization(
        channel_id=escrow_channel,
        hub=hub_addr,
        token=token,
        amount=int(amount_units),
        receipt_id=rid,
        nonce=int(nonce),
        deadline=dl,
    )
    digest = debit_digest(auth, chain_id=chain_id, verifying_contract=escrow)
    signed = Account._sign_hash(digest, Account.from_key(private_key).key)
    sig = signed.signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    return {
        "channelId": escrow_channel,
        "hub": hub_addr,
        "token": token,
        "amount": str(amount_units),
        "receiptId": rid,
        "nonce": nonce,
        "deadline": dl,
        "signature": sig,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default=DEFAULT_HUB)
    ap.add_argument("--discover", metavar="INTENT", help="list matching capabilities and exit")
    ap.add_argument("--category", help="discovery category filter, e.g. security")
    ap.add_argument("--capability", help="capability_id to invoke")
    ap.add_argument("--product", default="", help="product_id (defaults from catalogue lookup)")
    ap.add_argument("--input", default="{}", help="JSON input payload for the capability")
    ap.add_argument("--deposit", type=float, default=1.0, help="channel deposit in USD")
    ap.add_argument("--token", default="USDC")
    ap.add_argument("--chain", default="base")
    ap.add_argument("--wallet", default="", help="the wallet that opened the escrow channel")
    ap.add_argument("--tx", default="", help="on-chain deposit transaction hash (unsupported on prod image)")
    ap.add_argument("--payer-signature", default="", help="EIP-191 signature over the challenge")
    ap.add_argument(
        "--escrow-channel",
        default="",
        help="AIMarketEscrow channelId already funded on-chain. Replaces --tx/--payer-signature "
        "entirely. This is the ONLY working funding path on the modelmarket.dev image — see "
        "docs/handoff-first-paid-invoke.md",
    )
    ap.add_argument(
        "--private-key",
        default=os.environ.get("AIMARKET_DEPOSITOR_PRIVATE_KEY", ""),
        help="depositor key used to sign DebitAuthorization (or set AIMARKET_DEPOSITOR_PRIVATE_KEY)",
    )
    ap.add_argument(
        "--payment-authorization",
        default="",
        help="path to a JSON DebitAuthorization (+ signature) already signed by the depositor",
    )
    ap.add_argument("--escrow", default=DEFAULT_ESCROW)
    ap.add_argument("--token-address", default=DEFAULT_USDC)
    ap.add_argument("--hub-address", default=DEFAULT_HUB_ADDR)
    ap.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID)
    ap.add_argument("--rpc", default=os.environ.get("RPC", DEFAULT_RPC))
    ap.add_argument("--price", type=float, default=0.0, help="override price_per_call_usd (base units derived)")
    args = ap.parse_args()

    hub = args.hub.rstrip("/")
    ready = preflight(hub)
    if ready is None:
        return 1

    if args.discover:
        discover(hub, args.discover, args.deposit, args.category)
        return 0

    if not ready:
        print(
            "\nSTOP — see docs/payment-enable-runbook.md. Running the paid flow against a "
            "hub in this state would prove nothing."
        )
        return 1

    if not args.capability:
        print("\n--capability is required (or use --discover to find one)")
        return 2
    if not args.wallet:
        print("\n--wallet is required: a channel is credited only to the wallet that paid.")
        return 2
    if not args.tx and not args.escrow_channel:
        print("\nNeed either --escrow-channel (funded via AIMarketEscrow.openChannel) or --tx"
              "\n(a direct deposit transfer). On modelmarket.dev only the escrow path works:"
              "\nthe tx-hash verifier is not present in the hub image.")
        return 2

    cap_meta = lookup_capability(hub, args.capability)
    price = args.price or (float(cap_meta["price_per_call_usd"]) if cap_meta else 0.0)
    product = args.product or (cap_meta.get("product_id") if cap_meta else "") or args.capability.split(".", 1)[0]
    if price <= 0:
        print("\ncould not resolve a positive price — pass --price")
        return 2
    print(f"\ninvoke target   : {product} / {args.capability} @ ${price}")

    # ── open ───────────────────────────────────────────────────────────
    open_body = {
        "deposit_usd": args.deposit,
        "token": args.token,
        "chain": args.chain,
        "wallet": args.wallet,
    }
    if args.escrow_channel:
        open_body["escrow_channel_id"] = args.escrow_channel
    else:
        open_body["tx_hash"] = args.tx
        open_body["payer_signature"] = args.payer_signature
    status, opened = call("POST", f"{hub}/ai-market/v2/channel/open", open_body)
    show(f"channel/open → {status}", opened)

    if challenge := opened.get("challenge"):
        print("\nSign this exact string with the paying wallet and re-run with"
              " --payer-signature:\n\n"
              f"  {challenge}\n\n"
              "  cast wallet sign --account <your-account> "
              f"{json.dumps(challenge)}\n")
        return 3

    channel = opened.get("channel") or opened
    channel_id = channel.get("channel_id") or opened.get("channel_id")
    if not channel_id:
        print("\nno channel was opened — stopping before invoke")
        return 1
    channel_secret = channel.get("channel_secret") or opened.get("channel_secret") or ""
    if not channel_secret:
        print("\nWARNING: open returned no channel_secret — invoke will likely be refused")

    # ── payment authorization (escrow-backed channels) ─────────────────
    payment_authorization = None
    if args.payment_authorization:
        with open(args.payment_authorization, encoding="utf-8") as fh:
            payment_authorization = json.load(fh)
    elif args.escrow_channel:
        if not args.private_key:
            print(
                "\nSTOP — escrow-backed invoke needs a DebitAuthorization.\n"
                "  Pass --private-key / $AIMARKET_DEPOSITOR_PRIVATE_KEY, or\n"
                "  --payment-authorization path/to/auth.json\n"
            )
            # Still close so we don't leave a ledger channel holding the claim.
            call("POST", f"{hub}/ai-market/v2/channel/close", {
                "channel_id": channel_id,
                "wallet": args.wallet,
            })
            return 2
        try:
            nonce = read_escrow_nonce(args.rpc, args.escrow, args.escrow_channel)
        except Exception as exc:
            print(f"\nfailed to read on-chain nonce via cast: {exc}")
            call("POST", f"{hub}/ai-market/v2/channel/close", {
                "channel_id": channel_id,
                "wallet": args.wallet,
            })
            return 1
        amount_units = usd_to_base_units(price)
        payment_authorization = build_payment_authorization(
            escrow_channel=args.escrow_channel,
            hub_addr=args.hub_address,
            token=args.token_address,
            amount_units=amount_units,
            nonce=nonce,
            private_key=args.private_key,
            escrow=args.escrow,
            chain_id=args.chain_id,
        )
        show("payment_authorization (signed)", {
            **payment_authorization,
            "signature": payment_authorization["signature"][:20] + "…",
        })

    # ── invoke ─────────────────────────────────────────────────────────
    try:
        payload = json.loads(args.input)
    except json.JSONDecodeError as exc:
        print(f"--input is not valid JSON: {exc}")
        return 2

    invoke_body: dict = {
        "product_id": product,
        "capability_id": args.capability,
        "input": payload,
    }
    if payment_authorization is not None:
        invoke_body["payment_authorization"] = payment_authorization

    status, result = call(
        "POST",
        f"{hub}/ai-market/v2/invoke",
        invoke_body,
        headers={
            "X-Payment-Channel": channel_id,
            **({"X-Payment-Channel-Secret": channel_secret} if channel_secret else {}),
        },
    )
    show(f"invoke → {status}", result)
    invoke_ok = status == 200 and result.get("success") is not False and not result.get("error")

    # ── close ──────────────────────────────────────────────────────────
    status, closed = call("POST", f"{hub}/ai-market/v2/channel/close", {
        "channel_id": channel_id,
        "wallet": args.wallet,
    })
    show(f"channel/close → {status}", closed)

    if receipt_id := (result.get("receipt_id") or (result.get("receipt") or {}).get("id")):
        show("receipt", call("GET", f"{hub}/ai-market/v2/p/provenance/receipt/{receipt_id}")[1])
        print(f"\nverify: {hub}/ai-market/v2/p/provenance/verify/{receipt_id}")

    if invoke_ok and payment_authorization:
        print("\nPAID INVOKE SETTLED (off-chain ledger).")
        print("Next — on-chain debit+settle with the HUB key (0x1218), using:")
        print(f"  CHANNEL_ID={args.escrow_channel}")
        print(f"  amount={payment_authorization['amount']}")
        print(f"  receiptId={payment_authorization['receiptId']}")
        print(f"  nonce={payment_authorization['nonce']}")
        print(f"  deadline={payment_authorization['deadline']}")
        print(f"  signature={payment_authorization['signature']}")
        print("Record tx hashes in docs/onchain-journal.md")
        # Persist for step 7 without re-prompting secrets
        out_path = os.environ.get("FIRST_PAID_RESULT", "/tmp/first_paid_result.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "escrow_channel": args.escrow_channel,
                    "ledger_channel": channel_id,
                    "payment_authorization": payment_authorization,
                    "invoke": result,
                    "close": closed,
                    "price_usd": price,
                    "product_id": product,
                    "capability_id": args.capability,
                    "self_test_depositor": args.wallet,
                },
                fh,
                indent=2,
            )
        print(f"saved {out_path}")
        return 0
    if invoke_ok:
        print("\nPAID INVOKE SETTLED — record the tx hashes in docs/onchain-journal.md")
        return 0
    print("\nInvoke did not succeed; see the stage output above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
