#!/usr/bin/env python3
"""Return only Factory's unserved 2,000 atomic USDC to its original buyer.

Default preflight is read-only. --execute is an explicit operator refund.
--resume verifies only the one saved transaction and never signs or broadcasts.
No refund accounting, invoice, operation or business database is modified here.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import time

from eth_abi import encode
from eth_account import Account
from eth_utils import keccak

from run_paid_cycle import (Runner, CHAIN, TOKEN, PAYER, PRIVATE, HERE, L1_ORACLE,
                            FEE_CAP, atomic_json, canonical, digest, selector, utc)
from payment_guards import (Stop, require, TRANSFER, verify_exact_direct_receipt,
                            exclusive_private_checkpoint)

OPERATOR = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
AMOUNT = 2_000
ORIGINAL_TX = "0x47a095061a12704908f1c4b012ab55bab348b5050d272ed9f1b0fd3e2ff4a541"
ORIGINAL_OPERATION = "op_c0ddc6c655ed48100518ec4a37b7f966"
REFUNDS = PRIVATE / "refunds"


def transfer_data() -> str:
    return selector("transfer(address,uint256)") + encode(["address", "uint256"], [PAYER, AMOUNT]).hex()


def verify_refund_receipt(receipt: dict, transaction: dict, block: dict,
                          state: dict, head: int) -> dict:
    require(state.get("original_tx") == ORIGINAL_TX and
            state.get("original_operation") == ORIGINAL_OPERATION and
            state.get("sender") == OPERATOR and state.get("recipient") == PAYER and
            state.get("token") == TOKEN and state.get("amount_atomic") == AMOUNT and
            state.get("chain_id") == CHAIN, "Refund intent changed")
    tx_hash = state["transaction_hash"]
    require("0x" + keccak(bytes.fromhex(state["signed_transaction"][2:])).hex() == tx_hash,
            "Saved refund hash differs from signed bytes")
    require(receipt.get("transactionHash", "").lower() == tx_hash.lower() and
            int(receipt.get("status", "0x0"), 16) == 1, "Refund missing or reverted")
    mined = int(receipt["blockNumber"], 16)
    require(head - mined + 1 >= 3 and block.get("hash", "").lower() ==
            receipt.get("blockHash", "").lower() and int(block["number"], 16) == mined,
            "Refund confirmations or canonical block unavailable")
    require(transaction.get("hash", "").lower() == tx_hash.lower() and
            transaction.get("from", "").lower() == OPERATOR.lower() and
            transaction.get("to", "").lower() == TOKEN.lower() and
            int(transaction["chainId"], 16) == CHAIN and int(transaction["value"], 16) == 0 and
            int(transaction["nonce"], 16) == state["transaction"]["nonce"] and
            transaction.get("input", "").lower() == transfer_data().lower(),
            "Mined refund transaction differs from exact approved recipient/amount")
    matched, sender_out, recipient_in = 0, 0, 0
    for log in receipt.get("logs", []):
        if log.get("address", "").lower() != TOKEN.lower():
            continue
        topics = [str(topic).lower() for topic in log.get("topics", [])]
        if len(topics) < 3 or topics[0] != TRANSFER:
            continue
        sender, recipient = "0x" + topics[1][-40:], "0x" + topics[2][-40:]
        amount = int(log.get("data", "0x0"), 16)
        if sender == OPERATOR.lower():
            sender_out += amount
        if recipient == PAYER.lower():
            recipient_in += amount
        if sender == OPERATOR.lower() and recipient == PAYER.lower() and amount == AMOUNT:
            matched += 1
    require(matched == 1 and sender_out == recipient_in == AMOUNT,
            "Refund lacks exactly one approved token Transfer")
    require("l1Fee" in receipt, "Refund actual L1 fee unavailable")
    actual_fee = int(receipt["gasUsed"], 16) * int(receipt["effectiveGasPrice"], 16) + int(receipt["l1Fee"], 16)
    require(actual_fee <= int(state["fee_bound_wei"]) <= FEE_CAP,
            "Refund actual fee exceeds approved cap")
    return {"refund_transfer_exact": True, "confirmations": head - mined + 1,
            "refund_transaction_hash": tx_hash, "actual_operator_fee_wei": str(actual_fee)}


class Refund(Runner):
    def __init__(self):
        super().__init__("factory")
        self.journal_path = REFUNDS / "factory.json"
        self.summary = {"ok": False, "scope": "exact_original_factory_payment_refund",
            "client_started_utc": utc(), "original_transaction_hash": ORIGINAL_TX,
            "original_operation_id": ORIGINAL_OPERATION, "operator_sender": OPERATOR,
            "original_buyer_recipient": PAYER, "amount_atomic": AMOUNT,
            "chain_id": CHAIN, "asset": TOKEN, "operator_fee_cap_wei": str(FEE_CAP),
            "factory_full_cycle_passed": False}

    def original_unserved(self):
        state = json.loads((PRIVATE / "factory.json").read_text())
        offer = state["prepared"]["offer"]
        require(state.get("target") == "factory" and state.get("transaction_hash") == ORIGINAL_TX and
                offer.get("operation_id") == ORIGINAL_OPERATION and self.object_verified(offer),
                "Original paid operation differs from approved refund")
        require(offer.get("wallet", "").lower() == PAYER.lower() and
                offer["terms"]["pay_to"].lower() == OPERATOR.lower() and
                int(offer["terms"]["amount_units"]) == AMOUNT and
                offer["terms"]["token_contract"].lower() == TOKEN.lower() and
                offer["terms"]["chain_id"] == CHAIN,
                "Original terms differ from approved refund")
        receipt = self.rpc("eth_getTransactionReceipt", [ORIGINAL_TX])
        require(receipt is not None, "Original payment is not confirmed")
        head = int(self.rpc("eth_blockNumber", []), 16)
        block = self.rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
        proof = verify_exact_direct_receipt(receipt, self.approval(), tx_hash=ORIGINAL_TX,
            nonce=offer["invoice"]["nonce"], head_number=head, mined_block=block,
            invoice_expires_at=offer["invoice"]["expires_at"])
        operation = self.current_uncompleted_operation(state)
        return {"original_payment_exact": proof, "failed_operation_hybrid_verified": True,
                "failed_operation_sha256": digest(operation), "no_completed_receipt": True,
                "operation_status": operation["status"]}

    def current_uncompleted_operation(self, state):
        offer = state["prepared"]["offer"]
        _, operation = self.request("GET", "/ai-market/v2/operations/" + ORIGINAL_OPERATION,
                                    token=state["prepared"]["operation_token"])
        require(self.object_verified(operation), "Current failed-operation hybrid signature invalid")
        require(operation.get("operation_id") == ORIGINAL_OPERATION and
                operation.get("tx_hash", "").lower() == ORIGINAL_TX.lower() and
                operation.get("wallet", "").lower() == PAYER.lower() and
                operation.get("offer_digest") == digest(offer) and
                operation.get("input_digest") == state["input_sha256"] and
                operation.get("product_id") == self.target["product_id"] and
                operation.get("capability_id") == self.target["capability_id"],
                "Current failed-operation bindings changed")
        require(operation.get("status") == "reconciliation_required" and
                operation.get("success") is False and
                operation.get("busy") is False and
                not (operation.get("receipt") or {}).get("success"),
                "Operation completed or no longer matches the unserved refund case")
        return operation

    def refund_preflight(self):
        original = self.original_unserved()
        self.chain_clock()
        require(int(self.call(TOKEN, selector("decimals()")), 16) == 6,
                "Unexpected USDC decimals")
        pending = int(self.rpc("eth_getTransactionCount", [OPERATOR, "pending"]), 16)
        latest = int(self.rpc("eth_getTransactionCount", [OPERATOR, "latest"]), 16)
        require(pending == latest, "Operator has a pending transaction; no refund signing")
        before = {"operator_usdc_atomic": self.balance(OPERATOR),
                  "buyer_usdc_atomic": self.balance(PAYER),
                  "operator_eth_wei": int(self.rpc("eth_getBalance", [OPERATOR, "latest"]), 16)}
        require(before["operator_usdc_atomic"] >= AMOUNT,
                "Original payee has insufficient USDC; do not use another wallet")
        estimate = int(self.rpc("eth_estimateGas", [{"from": OPERATOR, "to": TOKEN,
            "data": transfer_data(), "value": "0x0"}]), 16)
        gas = (estimate * 125 + 99) // 100
        price = int(self.rpc("eth_gasPrice", []), 16)
        max_fee, priority = 2 * price, min(price, 1_000_000)
        l1 = int(self.call(L1_ORACLE, selector("getL1FeeUpperBound(uint256)") +
                           encode(["uint256"], [1024]).hex()), 16)
        bound = gas * max_fee + 100 * l1
        require(0 < gas <= 200_000 and 0 < max_fee and bound <= FEE_CAP,
                "Refund gas plus 100L1 exceeds the separate operator budget")
        require(before["operator_eth_wei"] >= bound,
                "Original payee has insufficient native gas; do not fund or change wallet")
        self.summary.update(original_payment_verified=True, failed_operation_hybrid_verified=True,
            no_completed_receipt=True, operation_status=original["operation_status"],
            failed_operation_sha256=original["failed_operation_sha256"],
            balances_before=before, operator_pending_nonce=pending,
            refund_fee_bound_wei=str(bound), gas_limit=gas, max_fee_per_gas_wei=str(max_fee))
        transaction = {"chainId": CHAIN, "nonce": pending, "to": TOKEN, "value": 0,
            "data": transfer_data(), "gas": gas, "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority, "type": 2}
        return {"phase": "prepared", "original_tx": ORIGINAL_TX,
            "original_operation": ORIGINAL_OPERATION, "sender": OPERATOR, "recipient": PAYER,
            "token": TOKEN, "chain_id": CHAIN, "amount_atomic": AMOUNT,
            "transaction": transaction, "fee_bound_wei": str(bound), "original_proof": original,
            "summary_before": self.summary}

    def execute_refund(self):
        require(not self.journal_path.exists(),
                "Prior refund journal exists; --resume only, never sign another refund")
        state = self.refund_preflight()
        # Establish exclusive durable ownership of this exact refund before key access.
        exclusive_private_checkpoint(self.journal_path, state)
        wallet = json.loads((Path.home() / ".aicom-base-deployer-v4.json").read_text())
        entry = wallet["accounts"][0] if "accounts" in wallet else wallet
        account = Account.from_key(entry["private_key"])
        wallet.clear()
        require(account.address.lower() == OPERATOR.lower(),
                "Local operator key does not own the original seller address")
        require(int(self.rpc("eth_getTransactionCount", [OPERATOR, "pending"]), 16) == state["transaction"]["nonce"] and
                int(self.rpc("eth_getTransactionCount", [OPERATOR, "latest"]), 16) == state["transaction"]["nonce"],
                "Operator nonce changed before signing")
        require(self.balance(OPERATOR) >= AMOUNT and
                int(self.rpc("eth_getBalance", [OPERATOR, "latest"]), 16) >= int(state["fee_bound_wei"]),
                "Operator balance changed before signing")
        # No automatic provider redispatch occurs here. Recheck the signed
        # operation after fee/nonce RPCs before authorizing the cash refund.
        original = json.loads((PRIVATE / "factory.json").read_text())
        current = self.current_uncompleted_operation(original)
        state["presign_operation_sha256"] = digest(current)
        atomic_json(self.journal_path, state, private=True)
        signed = account.sign_transaction(state["transaction"])
        require(len(signed.raw_transaction) <= 1024, "Refund signed size exceeds conservative L1 bound")
        tx_hash = "0x" + keccak(signed.raw_transaction).hex()
        state.update(phase="signed", transaction_hash=tx_hash,
                     signed_transaction="0x" + signed.raw_transaction.hex())
        atomic_json(self.journal_path, state, private=True)
        self.summary["refund_transaction_hash"] = tx_hash
        state.update(phase="broadcast_attempted", broadcast_client_utc=utc())
        atomic_json(self.journal_path, state, private=True)
        returned = self.rpc("eth_sendRawTransaction", [state["signed_transaction"]])
        require(str(returned).lower() == tx_hash.lower(), "Refund broadcast uncertain; reconcile saved hash")
        state["phase"] = "broadcast_returned"
        atomic_json(self.journal_path, state, private=True)
        return state

    def confirm_refund(self, state):
        require(state.get("signed_transaction") and state.get("transaction_hash"),
                "No signed refund to resume; no replacement signing")
        receipt = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            receipt = self.rpc("eth_getTransactionReceipt", [state["transaction_hash"]])
            if receipt:
                head = int(self.rpc("eth_blockNumber", []), 16)
                if head - int(receipt["blockNumber"], 16) + 1 >= 3:
                    break
            time.sleep(2)
        else:
            raise Stop("Refund confirmations pending; --resume the exact saved transaction")
        transaction = self.rpc("eth_getTransactionByHash", [state["transaction_hash"]])
        block = self.rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
        proof = verify_refund_receipt(receipt, transaction, block, state, head)
        after = {"operator_usdc_atomic": self.balance(OPERATOR),
                 "buyer_usdc_atomic": self.balance(PAYER),
                 "operator_eth_wei": int(self.rpc("eth_getBalance", [OPERATOR, "latest"]), 16)}
        before = state["summary_before"]["balances_before"]
        require(before["operator_usdc_atomic"] - after["operator_usdc_atomic"] == AMOUNT and
                after["buyer_usdc_atomic"] - before["buyer_usdc_atomic"] == AMOUNT,
                "Wallet deltas differ from exact operator-to-original-buyer refund")
        state.update(phase="refunded", chain_receipt=receipt, mined_transaction=transaction,
                     mined_block=block, balances_after=after)
        atomic_json(self.journal_path, state, private=True)
        self.summary.update(ok=True, phase="refunded", **proof, balances_after=after,
            operator_usdc_delta_atomic=-AMOUNT, buyer_usdc_delta_atomic=AMOUNT,
            original_service_charge_refunded=True, factory_full_cycle_passed=False,
            buyer_original_network_fee_not_refunded=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    REFUNDS.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(REFUNDS.stat().st_uid == os.getuid() and REFUNDS.stat().st_mode & 0o077 == 0,
            "Refund private directory ownership/mode unsafe")
    runner = Refund()
    lock = open(REFUNDS / ".operator.lock", "a+b")
    os.chmod(REFUNDS / ".operator.lock", 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            require(runner.journal_path.exists(), "No refund journal to resume")
            state = json.loads(runner.journal_path.read_text())
            runner.summary.update(state["summary_before"])
            runner.summary.update(resume_only=True, ok=False)
            runner.confirm_refund(state)
        elif args.execute:
            runner.confirm_refund(runner.execute_refund())
        else:
            runner.refund_preflight()
            runner.summary.update(ok=True, phase="readonly_preflight", operator_key_loaded=False,
                                  broadcast_attempted=False)
    except BaseException as exc:
        runner.summary.update(ok=False, error_type=type(exc).__name__,
            error=str(exc) if isinstance(exc, Stop) else "Stopped; reconcile the same private refund journal")
    finally:
        runner.client.close()
        runner.summary["client_finished_utc"] = utc()
        output = HERE / ("factory-refund.json" if args.execute or args.resume else "factory-refund-preflight.json")
        atomic_json(output, runner.summary, private=False)
        print(json.dumps(runner.summary, sort_keys=True))
        lock.close()
    return 0 if runner.summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
