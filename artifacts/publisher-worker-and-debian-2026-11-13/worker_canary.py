#!/usr/bin/env python3
"""Use existing operator test credit for one timer-driven production payout."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import canary as prior

ORIGINAL_RUN = "b35100405f7aea3e"
ORIGINAL_TOPUP = "0x46929e16ed8c343ba875b426bb1ff81105354b67aa0664f6de7e27a9ede24c23"
ORIGINAL_PAYOUT = "pwd_bde0ad7696e34caea384a434624443ac"
ORIGINAL_RECEIPT = "rcpt_ee6d172db08ebb1f727bd2315bac59cd"
ORIGINAL_BALANCE_MC = 998
SALE_MC = 2
SHARE_MC = 1
IN_PROGRESS = {"requested", "signed", "broadcast", "paid"}
PUBLISHER_ENTRIES = [{"kind": "payout", "amount_mc": SHARE_MC},
                     {"kind": "publisher_cash_accrual", "amount_mc": SHARE_MC}]
BUYER_ENTRIES = [{"kind": "hold", "amount_mc": SALE_MC}, {"kind": "capture", "amount_mc": SALE_MC}]


def payout_terms(state):
    return {"request_id": prior.idempotency_key(state), "amount_usdc": prior.PAYOUT_USD,
            "recipient": state["recipient"]}


def read_request(state):
    summary, _ = prior.request("GET", prior.WITHDRAW + "?limit=100", key=state["publisher"]["api_key"])
    matches = [row for row in summary["withdrawals"] if row["request_id"] == prior.idempotency_key(state)]
    prior.require(len(matches) <= 1, "duplicate withdrawal request ID")
    return summary, matches[0] if matches else None


def check_withdrawal(state, row):
    prior.require(row["request_id"] == prior.idempotency_key(state) and row["sender"] == state["sender"]
                  and row["recipient"] == state["recipient"] and row["amount_atomic"] == prior.PAYOUT_UNITS
                  and row["withdrawal_id"] != ORIGINAL_PAYOUT and row["status"] in IN_PROGRESS,
                  "withdrawal differs from the new canary reservation")


def check_original(old, ledger):
    prior.require(old.get("run_id") == ORIGINAL_RUN and old.get("topup_tx") == ORIGINAL_TOPUP
                  and old["withdrawal"]["withdrawal_id"] == ORIGINAL_PAYOUT
                  and old["sale"]["receipt_id"] == ORIGINAL_RECEIPT,
                  "old state does not match the documented first production canary")
    for role in ("buyer", "publisher"):
        account = old[role]
        prior.require(ledger.resolve(account["api_key"]) == account["account_id"], f"old {role} credential is inactive")
    response, _ = prior.request("GET", f"{prior.WITHDRAW}/{ORIGINAL_PAYOUT}", key=old["publisher"]["api_key"])
    prior.require(response["status"] == "paid" and response["recipient"] == old["recipient"]
                  and response["sender"] == old["sender"], "first production canary payout is not reconciled")


def check_buyer(db, state, expected_mc):
    row = db._conn.execute(
        "SELECT balance_mc, base_principal_mc, granted_mc, topped_up_mc, held_mc FROM credit_accounts WHERE account_id=?",
        (state["buyer"]["account_id"],),
    ).fetchone()
    prior.require(row and (row["balance_mc"], row["base_principal_mc"], row["granted_mc"],
                  row["topped_up_mc"], row["held_mc"]) == (expected_mc, expected_mc, 0, 1000, 0),
                  "buyer credit differs from the first canary's verified Base USDC remainder")


def prepare(args):
    from aimarket_hub.credits import CreditsLedger
    from aimarket_hub.publisher_withdrawals import configured_sender

    prior.require(prior.RUN_ID.fullmatch(args.run_id) and args.run_id != ORIGINAL_RUN and args.state != args.old_state,
                  "new state and a fresh 16–32 lowercase-hex run ID are required")
    old = prior.private_json(args.old_state)
    db = prior.open_db()
    try:
        check_original(old, CreditsLedger(db._conn))
        prior.require(configured_sender() == old["sender"], "live payout sender changed")
        expected = {key: old[key] for key in ("buyer", "publisher", "sender", "recipient")}
        expected["run_id"] = args.run_id
        if args.state.exists():
            state = prior.private_json(args.state)
            prior.require(all(state.get(key) == value for key, value in expected.items()), "state belongs to another run")
        else:
            check_buyer(db, old, ORIGINAL_BALANCE_MC)
            summary, _ = read_request(expected)
            prior.require(summary["enabled"] is True and summary["withdrawable_usdc"] == 0
                          and summary["payout_wallet"] == old["recipient"], "publisher cannot safely reuse its verified wallet")
            state = expected
            prior.write_state(args.state, state)

        if "sale" not in state:
            # Keep the same invoke identity on a retry. The first call may have committed even
            # if the process stopped before recording the response in local state.
            prior.fixture(db, state)
            product, capability = prior.fixture_ids(state)
            body = {"product_id": product, "capability_id": capability, "source_hub": "local", "input": {}}
            try:
                first, first_headers = prior.request("POST", "/invoke", key=state["buyer"]["api_key"], body=body,
                                                     idempotency=prior.idempotency_key(state))
                replay, headers = prior.request("POST", "/invoke", key=state["buyer"]["api_key"], body=body,
                                                idempotency=prior.idempotency_key(state))
                receipt_id = first["receipt"]["nonce"]
                prior.require(first == replay and headers.get("x-aimarket-idempotency") == "replayed"
                              and first.get("success") is True and first.get("price_usd") == prior.SALE_USD
                              and first.get("result", {}).get("custody_canary") is True
                              and receipt_id != ORIGINAL_RECEIPT and first["receipt"].get("signature"),
                              "new paid sale was not replayed under the same receipt")
                state["sale"] = {"receipt_id": receipt_id, "price_usd": first["price_usd"],
                                 "first_idempotency": first_headers.get("x-aimarket-idempotency"),
                                 "replay_idempotency": headers.get("x-aimarket-idempotency")}
                prior.write_state(args.state, state)
            finally:
                prior.fixture(db, state, remove=True)

        receipt_id = state["sale"]["receipt_id"]
        prior.require(prior.entries(db, state["buyer"]["account_id"], receipt_id) == BUYER_ENTRIES
                      and prior.entries(db, state["publisher"]["account_id"], receipt_id) == PUBLISHER_ENTRIES,
                      "new sale does not have exactly one capture and backed publisher credit")
        check_buyer(db, state, ORIGINAL_BALANCE_MC - SALE_MC)
        prior.fixture(db, state, remove=True)
        summary, existing = read_request(state)
        if existing:
            check_withdrawal(state, existing)
            return {"already_reserved": True, "withdrawal": existing, "sale": state["sale"]}
        prior.require(summary["withdrawable_usdc"] == float(prior.PAYOUT_USD), "new payout accrual is not available")
        terms = payout_terms(state)
        quote, _ = prior.request("POST", prior.WITHDRAW + "/quote", key=state["publisher"]["api_key"], body=terms)
        prior.require(quote["amount_atomic"] == prior.PAYOUT_UNITS, "withdrawal quote amount changed")
        state["withdrawal_quote"] = quote
        prior.write_state(args.state, state)
        return {"existing_topup_tx": ORIGINAL_TOPUP, "new_topup": False, "sale": state["sale"],
                "buyer_balance_before_usdc": 0.00998, "buyer_balance_after_usdc": 0.00996,
                "publisher_entries": PUBLISHER_ENTRIES, "buyer_entries": BUYER_ENTRIES,
                "fixture_removed": True, "withdrawal_request": terms, "withdrawal_quote": quote,
                "publisher_account": state["publisher"]["account_id"], "sender": state["sender"]}
    finally:
        db.close()


def reserve(args):
    state = prior.private_json(args.state)
    _, existing = read_request(state)
    if existing:
        check_withdrawal(state, existing)
        return {"already_reserved": True, "withdrawal": existing}
    signature = json.load(sys.stdin)["signature"]
    prior.require(isinstance(signature, str) and re.fullmatch(r"0x[0-9a-fA-F]{130}", signature), "invalid signature format")
    body = {**payout_terms(state), "issued_at": state["withdrawal_quote"]["issued_at"], "signature": signature}
    key = state["publisher"]["api_key"]
    first, _ = prior.request("POST", prior.WITHDRAW, key=key, body=body, expected=202)
    second, _ = prior.request("POST", prior.WITHDRAW, key=key, body=body, expected=202)
    check_withdrawal(state, first)
    check_withdrawal(state, second)
    prior.require(first["withdrawal_id"] == second["withdrawal_id"], "request replay used another withdrawal")
    return {"withdrawal": first, "reservation_replayed": True, "replay_status": second["status"]}


def status(args):
    state = prior.private_json(args.state)
    _, row = read_request(state)
    if not row:
        return {"status": "not_reserved", "sale": state["sale"]}
    check_withdrawal(state, row)
    return {"status": row["status"], "withdrawal": row, "sale": state["sale"]}


def verify(args):
    state = prior.private_json(args.state)
    observed = status(args)
    prior.require(observed["status"] == "paid", "timer-driven withdrawal is not finalized yet")
    expected = observed["withdrawal"]
    actual, _ = prior.request("GET", f"{prior.WITHDRAW}/{expected['withdrawal_id']}", key=state["publisher"]["api_key"])
    prior.require(prior.TX.fullmatch(actual["tx_hash"]) and actual["tx_hash"] == expected["tx_hash"]
                  and actual["status"] == "paid", "repeated read differs from the finalized withdrawal")
    db = prior.open_db()
    try:
        ledger = prior.entries(db, state["publisher"]["account_id"], expected["withdrawal_id"])
        prior.require(ledger == [{"kind": "publisher_withdraw_requested", "amount_mc": SHARE_MC},
                                {"kind": "publisher_withdraw_paid", "amount_mc": SHARE_MC}],
                      "final withdrawal must have one reservation and one paid entry")
        return {**observed, "withdrawal_entries": ledger, "existing_topup_tx": ORIGINAL_TOPUP, "new_topup": False}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "reserve", "status", "verify", "cleanup"):
        commands.add_parser(action).add_argument("--state", type=Path, required=True)
    commands.choices["prepare"].add_argument("--old-state", type=Path, required=True)
    commands.choices["prepare"].add_argument("--run-id", required=True)
    args = parser.parse_args()
    actions = {"prepare": prepare, "reserve": reserve, "status": status, "verify": verify, "cleanup": prior.cleanup}
    try:
        print(json.dumps(actions[args.action](args), indent=2, sort_keys=True))
    except RuntimeError as exc:
        parser.exit(1, f"worker canary stopped: {exc}\n")
    except Exception as exc:
        parser.exit(1, f"worker canary stopped: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
