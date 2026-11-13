#!/usr/bin/env python3
"""Production-path canary. This tool never broadcasts or accepts a private payout signer key."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

HUB = "https://modelmarket.dev"
LOOPBACK = "http://127.0.0.1:9083"
API = "/ai-market/v2"
WITHDRAW = "/account/withdrawals"
PAYEE = "0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TOPUP_USD = 0.01
SALE_USD = 0.00002
PAYOUT_USD = "0.00001"
PAYOUT_UNITS = "10"
RUN_ID = re.compile(r"[a-f0-9]{16,32}")
TX = re.compile(r"0x[0-9a-f]{64}")
ADDRESS = re.compile(r"0x[0-9a-f]{40}")
BASE_RPCS = ("https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.drpc.org")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def request(method, path, *, key=None, body=None, idempotency=None, expected=200):
    headers = {"Accept": "application/json", "User-Agent": "modelmarket-publisher-custody-canary/1"}
    if key:
        headers["X-API-Key"] = key
    if body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    req = urllib.request.Request(LOOPBACK + API + path, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with HTTP.open(req, timeout=25) as response:
            status, data, reply_headers = response.status, response.read(1_048_577), response.headers
    except urllib.error.HTTPError as exc:
        status, data, reply_headers = exc.code, exc.read(1_048_577), exc.headers
    require(len(data) <= 1_048_576, "Hub response exceeded the canary limit")
    if status != expected:
        try:
            error_code = json.loads(data).get("error", "")
        except (ValueError, AttributeError):
            error_code = ""
        safe_code = error_code if isinstance(error_code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", error_code) else ""
        raise RuntimeError(f"{method} {path} returned HTTP {status}, expected {expected}; code={safe_code}")
    return json.loads(data), reply_headers


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r") as file:
        mode = os.fstat(file.fileno()).st_mode
        require(stat.S_ISREG(mode) and not mode & 0o077, "private state/key must be an owner-only regular file")
        return json.load(file)


def write_state(path, body):
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(body, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def open_db():
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase

    config = HubConfig()
    require(config.hub_url.rstrip("/") == HUB, "this production canary is restricted to the ModelMarket apex")
    return HubDatabase(config.db_path, database_url=config.database_url)


def idempotency_key(state):
    return f"publisher-custody-canary-{state['run_id']}"


def fixture_ids(state):
    return idempotency_key(state), f"publisher.custody.canary-{state['run_id']}@v1"


def fixture(db, state, *, remove=False):
    from aimarket_hub.models import Capability

    product, capability = fixture_ids(state)
    existing = db.get_capability(product, capability)
    if existing:
        require(existing.publisher_id == state["publisher"]["account_id"] and existing.price_per_call_usd == SALE_USD,
                "refusing to touch a fixture not owned by this canary")
    if remove:
        return bool(existing and db.delete_capability(capability) == 1)
    if not existing:
        db.upsert_capability(Capability(
            capability_id=capability, product_id=product, name="Publisher custody deployment canary",
            description="Temporary operator smoke test", price_per_call_usd=SALE_USD, source_hub="local",
            publisher_id=state["publisher"]["account_id"], prompt_template='{"custody_canary":true,"ok":true}',
        ))
        require(db.get_capability(product, capability) is not None, "could not install isolated local canary fixture")


def topup_quote(state):
    body, _ = request("POST", "/account/topup", key=state["buyer"]["api_key"],
                      body={"amount_usd": TOPUP_USD}, expected=402)
    validate_topup_quote(body)
    body["_hub"] = HUB
    return body


def validate_topup_quote(body):
    (accept,) = body.get("accepts", [])
    extra = accept["extra"]
    nonce = body.get("nonce", "")
    require(body.get("binding") == "eip3009" and TX.fullmatch(nonce) and extra["nonce"] == nonce,
            "top-up quote is not bound to its own EIP-3009 nonce")
    require(accept["scheme"] == "exact" and accept["asset"].lower() == USDC and accept["payTo"].lower() == PAYEE
            and int(accept["maxAmountRequired"]) == 10_000 and int(extra["chainId"]) == 8453
            and extra["verifyingContract"].lower() == USDC and extra["name"] == "USD Coin" and extra["version"] == "2",
            "top-up quote differs from the pinned 0.01 Base USDC terms")
    require(body["topup"]["redeem_url"] == f"{HUB}{API}/topups/{nonce}", "unexpected top-up redemption URL")


def prepare(args):
    from aimarket_hub.credits import CreditsLedger
    from aimarket_hub.publisher_withdrawals import configured_sender

    require(RUN_ID.fullmatch(args.run_id), "run ID must be 16–32 lowercase hex characters")
    require(ADDRESS.fullmatch(args.sender) and ADDRESS.fullmatch(args.recipient)
            and args.sender != args.recipient and args.sender == configured_sender(), "payout signer configuration mismatch")
    db = open_db()
    try:
        if args.state.exists():
            state = private_json(args.state)
            require((state["run_id"], state["sender"], state["recipient"]) == (args.run_id, args.sender, args.recipient),
                    "canary state belongs to a different run or wallet")
        else:
            state = {"run_id": args.run_id, "sender": args.sender, "recipient": args.recipient}
            write_state(args.state, state)
        ledger = CreditsLedger(db._conn)
        for role in ("buyer", "publisher"):
            if role not in state:
                account = ledger.create_account(label=f"publisher custody canary {args.run_id} {role}", grant_usd=0)
                state[role] = {k: account[k] for k in ("account_id", "api_key")}
                write_state(args.state, state)
        account, _ = request("GET", WITHDRAW, key=state["publisher"]["api_key"])
        require(account.get("enabled") is True, "withdrawals are not enabled in the live Hub process")
        if "sale" not in state:
            fixture(db, state)
        if "topup" not in state:
            state["topup"] = topup_quote(state)
            write_state(args.state, state)
        return state["topup"]
    finally:
        db.close()


def entries(db, account_id, receipt_id):
    rows = db._conn.execute("SELECT kind, amount_mc FROM credit_ledger WHERE account_id = ? AND receipt_id = ? ORDER BY id",
                            (account_id, receipt_id)).fetchall()
    return [{"kind": row["kind"], "amount_mc": int(row["amount_mc"])} for row in rows]


def complete(args):
    from aimarket_hub.credits import CreditsLedger

    state = private_json(args.state)
    tx = args.topup_tx.lower()
    require(TX.fullmatch(tx) and state.get("topup_tx", tx) == tx, "top-up transaction mismatch")
    validate_topup_quote(state["topup"])
    state["topup_tx"] = tx
    write_state(args.state, state)
    nonce = state["topup"]["nonce"]
    buyer, seller = state["buyer"], state["publisher"]
    for _ in range(2):
        redemption, _ = request("POST", f"/topups/{nonce}", key=buyer["api_key"], body={"tx_hash": tx})
        require(redemption.get("credited_usd") == TOPUP_USD, "top-up did not credit the expected amount")
    require(redemption.get("idempotent_replay") is True, "second top-up redemption did not replay")
    db = open_db()
    try:
        ledger = CreditsLedger(db._conn)
        if "sale" not in state:
            fixture(db, state)
            product, capability = fixture_ids(state)
            body = {"product_id": product, "capability_id": capability, "source_hub": "local", "input": {}}
            first, first_headers = request("POST", "/invoke", key=buyer["api_key"], body=body,
                                           idempotency=idempotency_key(state))
            again, replay_headers = request("POST", "/invoke", key=buyer["api_key"], body=body,
                                             idempotency=idempotency_key(state))
            require(first == again and replay_headers.get("x-aimarket-idempotency") == "replayed", "invoke was not replayed")
            require(first.get("success") is True and first.get("price_usd") == SALE_USD
                    and first.get("result", {}).get("custody_canary") is True, "invoke was not the expected paid local fixture")
            receipt_id = first["receipt"]["nonce"]
            require(receipt_id and first["receipt"].get("signature"), "paid receipt is missing its ID or signature")
            state["sale"] = {"receipt_id": receipt_id, "price_usd": first["price_usd"],
                             "first_idempotency": first_headers.get("x-aimarket-idempotency"),
                             "replay_idempotency": replay_headers.get("x-aimarket-idempotency")}
            write_state(args.state, state)
        receipt_id = state["sale"]["receipt_id"]
        seller_entries = [{"kind": "payout", "amount_mc": 1}, {"kind": "publisher_cash_accrual", "amount_mc": 1}]
        require(entries(db, seller["account_id"], receipt_id) == seller_entries, "publisher receipt entries differ")
        payer_entries = entries(db, buyer["account_id"], receipt_id)
        require(payer_entries == [{"kind": "hold", "amount_mc": 2}, {"kind": "capture", "amount_mc": 2}],
                "buyer receipt did not capture exactly once")
        repeat = ledger.pay_publisher(seller["account_id"], float(PAYOUT_USD), receipt_id=receipt_id, cash_backed=True)
        conflict = ledger.pay_publisher(seller["account_id"], SALE_USD, receipt_id=receipt_id, cash_backed=True)
        require(repeat.get("already") is True and conflict.get("error") and
                entries(db, seller["account_id"], receipt_id) == seller_entries, "publisher receipt replay changed the ledger")
        fixture(db, state, remove=True)
        withdrawal_request = {"request_id": idempotency_key(state), "amount_usdc": PAYOUT_USD, "recipient": state["recipient"]}
        if "withdrawal" not in state:
            available, _ = request("GET", WITHDRAW, key=seller["api_key"])
            require(available["withdrawable_usdc"] == float(PAYOUT_USD), "seller has unexpected withdrawable balance")
            quote, _ = request("POST", WITHDRAW + "/quote", key=seller["api_key"], body=withdrawal_request)
            require(quote["amount_atomic"] == PAYOUT_UNITS, "withdrawal quote changed the payout amount")
            state["withdrawal_quote"] = quote
            write_state(args.state, state)
        return {"topup_tx": tx, "sale": state["sale"], "seller_entries": seller_entries,
                "payer_entries": payer_entries, "receipt_replayed": True, "conflicting_amount_refused": True,
                "withdrawal_request": withdrawal_request, "withdrawal_quote": state["withdrawal_quote"],
                "publisher_account": seller["account_id"], "sender": state["sender"], "fixture_removed": True}
    finally:
        db.close()


def sign(args):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    data = json.load(sys.stdin)
    request_body, quote = data["withdrawal_request"], data["withdrawal_quote"]
    require(ADDRESS.fullmatch(args.sender) and data["sender"] == args.sender and
            request_body["amount_usdc"] == PAYOUT_USD and quote["amount_atomic"] == PAYOUT_UNITS and
            quote["request_id"] == request_body["request_id"] and type(quote["issued_at"]) is int
            and quote["issued_at"] > 0, "withdrawal quote terms differ")
    recipient = request_body["recipient"]
    require(recipient == args.recipient and ADDRESS.fullmatch(recipient), "unexpected publisher wallet")
    account = Account.from_key(private_json(args.recipient_key)["private_key"])
    require(account.address.lower() == recipient, "local keystore does not own the publisher wallet")
    expected = "\n".join(("AIMarket publisher withdrawal v1", f"hub: {HUB}", f"account: {data['publisher_account']}",
                          f"request: {request_body['request_id']}", "chain: eip155:8453", f"token: {USDC}",
                          f"amount_atomic: {PAYOUT_UNITS}", f"recipient: {recipient}", f"sender: {args.sender}",
                          f"issued_at: {quote['issued_at']}"))
    require(quote["message"] == expected, "refusing to sign a mismatched payout message")
    return {"signature": "0x" + bytes(account.sign_message(encode_defunct(text=expected)).signature).hex()}


def reserve(args):
    state = private_json(args.state)
    if "withdrawal" in state:
        return state["withdrawal"]
    signature = json.load(sys.stdin)["signature"]
    require(re.fullmatch(r"0x[0-9a-fA-F]{130}", signature), "invalid signature format")
    quote = state["withdrawal_quote"]
    body = {"request_id": idempotency_key(state), "amount_usdc": PAYOUT_USD, "recipient": state["recipient"],
            "issued_at": quote["issued_at"], "signature": signature}
    key = state["publisher"]["api_key"]
    first, _ = request("POST", WITHDRAW, key=key, body=body, expected=202)
    second, _ = request("POST", WITHDRAW, key=key, body=body, expected=202)
    public_id = first["withdrawal_id"]
    require(first["status"] == "requested" and first["sender"] == state["sender"]
            and first["recipient"] == state["recipient"] and first["amount_atomic"] == PAYOUT_UNITS
            and second["withdrawal_id"] == public_id, "withdrawal was not reserved exactly once")
    state["withdrawal"] = {"withdrawal_id": public_id, "amount_atomic": PAYOUT_UNITS,
                           "reservation_replayed": True, "sender": state["sender"], "recipient": state["recipient"]}
    write_state(args.state, state)
    return state["withdrawal"]


def verify(args):
    state = private_json(args.state)
    withdrawal_id = state["withdrawal"]["withdrawal_id"]
    key = state["publisher"]["api_key"]
    first, _ = request("GET", f"{WITHDRAW}/{withdrawal_id}", key=key)
    second, _ = request("GET", f"{WITHDRAW}/{withdrawal_id}", key=key)
    require(first == second and first["status"] == "paid" and first["sender"] == state["sender"]
            and first["recipient"] == state["recipient"] and first["amount_atomic"] == PAYOUT_UNITS
            and TX.fullmatch(first["tx_hash"]), "withdrawal is not yet reconciled to a stable paid transaction")
    db = open_db()
    try:
        account_id = state["publisher"]["account_id"]
        records = entries(db, account_id, withdrawal_id)
        require(records == [{"kind": "publisher_withdraw_requested", "amount_mc": 1},
                            {"kind": "publisher_withdraw_paid", "amount_mc": 1}], "withdrawal has unexpected ledger postings")
        return {"sale": state["sale"], "withdrawal": first, "withdrawal_entries": records}
    finally:
        db.close()


def chain_proof(args):
    tx_hash = args.tx_hash.lower()
    require(TX.fullmatch(tx_hash) and ADDRESS.fullmatch(args.sender) and ADDRESS.fullmatch(args.recipient)
            and args.sender != args.recipient, "invalid Base payout identity")

    def rpc(method, params):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(args.rpc, data=body, headers={"Content-Type": "application/json",
                                                                 "User-Agent": "aicom-production-check/1"})
        with HTTP.open(req, timeout=12) as response:
            result = json.loads(response.read(1_048_576))
        require("result" in result, f"Base RPC refused {method}")
        return result["result"]

    require(int(rpc("eth_chainId", []), 16) == 8453, "RPC is not Base mainnet")
    receipt = rpc("eth_getTransactionReceipt", [tx_hash])
    proof = {"chain_id": 8453, "rpc": args.rpc, "tx_hash": tx_hash,
             "explorer": f"https://basescan.org/tx/{tx_hash}"}
    if receipt is None:
        return {**proof, "status": "awaiting_receipt"}
    require(receipt["transactionHash"].lower() == tx_hash and int(receipt["status"], 16) == 1
            and receipt["from"].lower() == args.sender and receipt["to"].lower() == USDC,
            "receipt failed or does not match the intended payout sender and token")
    sender_topic = "0x" + args.sender[2:].rjust(64, "0")
    recipient_topic = "0x" + args.recipient[2:].rjust(64, "0")
    transfers = []
    for log in receipt["logs"]:
        topics = [value.lower() for value in log["topics"]]
        if log["address"].lower() == USDC and topics[:2] == [TRANSFER_TOPIC, sender_topic]:
            require(len(topics) == 3 and not log.get("removed"), "invalid canonical USDC Transfer log")
            transfers.append((topics[2], int(log["data"], 16)))
    require(transfers == [(recipient_topic, int(PAYOUT_UNITS))], "receipt does not have the exact single payout Transfer")
    block = rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
    require(block["hash"].lower() == receipt["blockHash"].lower(), "receipt block is not canonical")
    finalized = rpc("eth_getBlockByNumber", ["finalized", False])
    block_number = int(receipt["blockNumber"], 16)
    finalized_number = int(finalized["number"], 16)
    return {**proof, "status": "finalized" if finalized_number >= block_number else "mined_waiting_finality",
            "sender": args.sender, "recipient": args.recipient, "amount_atomic": PAYOUT_UNITS,
            "token": USDC, "receipt_block": block_number, "receipt_block_hash": block["hash"],
            "finalized_head": finalized_number, "gas_used": int(receipt["gasUsed"], 16),
            "effective_gas_price_wei": int(receipt["effectiveGasPrice"], 16)}


def cleanup(args):
    state = private_json(args.state)
    db = open_db()
    try:
        return {"fixture_removed": fixture(db, state, remove=True)}
    finally:
        db.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "complete", "reserve", "verify", "cleanup"):
        commands.add_parser(action).add_argument("--state", type=Path, required=True)
    commands.choices["prepare"].add_argument("--run-id", required=True)
    commands.choices["complete"].add_argument("--topup-tx", required=True)
    signer = commands.add_parser("sign")
    signer.add_argument("--recipient-key", type=Path, required=True)
    proof = commands.add_parser("chain-proof")
    proof.add_argument("--tx-hash", required=True)
    proof.add_argument("--rpc", choices=BASE_RPCS, default=BASE_RPCS[0])
    for action in ("prepare", "sign", "chain-proof"):
        commands.choices[action].add_argument("--sender", required=True, type=str.lower)
        commands.choices[action].add_argument("--recipient", required=True, type=str.lower)
    args = parser.parse_args()
    actions = {"prepare": prepare, "complete": complete, "sign": sign, "reserve": reserve,
               "verify": verify, "chain-proof": chain_proof, "cleanup": cleanup}
    try:
        print(json.dumps(actions[args.action](args), indent=2, sort_keys=True))
    except RuntimeError as exc:
        parser.exit(1, f"canary stopped: {exc}\n")
    except Exception as exc:
        # Never print a request, key, signature or private state on exceptions.
        parser.exit(1, f"canary stopped: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
