#!/usr/bin/env python3
"""One explicitly authorized production payment; default is read-only preflight.

Run with the workspace .venv/bin/python. No automatic new quote/payment on retry.
--execute creates exactly one operation and transaction for one fixed target.
--resume only recovers that operation/transaction; it never broadcasts or signs.
Private protocol documents and signed bytes stay in the ignored 0700/0600 tree.
Public evidence contains selected checks/hashes, never secrets or full payloads.
"""
from __future__ import annotations

import argparse
import datetime as dt
from decimal import Decimal
from dataclasses import replace
import email.utils
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
sys.path[:0] = [str(WORKSPACE / "aimarket-hub"), str(WORKSPACE / "aimarket-agent"),
               str(HERE / "review")]

import httpx
from eth_abi import decode, encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import NoSuchResource

from aimarket_agent.topup import typed_data, calldata
from aimarket_hub.signing import Signer, receipt_signature_version
from payment_guards import (Approval, Stop, canonical, require,
                            validate_offer, verify_exact_direct_receipt,
                            exclusive_private_checkpoint)

CHAIN = 8453
TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAYER = "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a"
RPC = "https://base-rpc.publicnode.com"
READ_RPC_POOL = (("publicnode", RPC), ("base-official", "https://mainnet.base.org"),
                 ("drpc-public", "https://base.drpc.org"))
READ_METHODS = frozenset({"eth_chainId", "eth_getTransactionReceipt", "eth_blockNumber",
    "eth_getBlockByNumber", "eth_getTransactionCount", "eth_getTransactionByHash",
    "eth_getBalance", "eth_getCode", "eth_call"})
L1_ORACLE = "0x420000000000000000000000000000000000000F"
FEE_CAP = 10**13
TOTAL_FEE_CAP = 3 * FEE_CAP
PRINCIPAL_CAP = 13_000
PRIVATE = WORKSPACE / "data/secrets/hub-real-payments-2026-11-08"
BASE = "/ai-market/v2/operations"


def digest(value: object) -> str:
    # SELLER-OP uses studio_paid._json: its ensure_ascii default is True.
    # Full-object signatures use a different canonical (ensure_ascii=False).
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(wire.encode()).hexdigest()


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: Path, value: dict, *, private: bool) -> None:
    fd, name = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600 if private else 0o644)
        with os.fdopen(fd, "wb") as file:
            file.write(canonical(value) + b"\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def selector(name: str) -> str:
    return "0x" + keccak(text=name)[:4].hex()


def no_remote_schema(uri):
    raise NoSuchResource(ref=uri)


def validate_input(schema: dict, value: dict) -> None:
    try:
        validator = validator_for(schema)
        validator.check_schema(schema)
        validator(schema, registry=Registry(retrieve=no_remote_schema)).validate(value)
    except Exception:
        raise Stop("Input does not validate offline against the signed offer schema") from None


class Runner:
    def __init__(self, target_name: str):
        self.name = target_name
        self.target = json.loads((HERE / "targets.json").read_text())[target_name]
        self.base = self.target["base"]
        self.client = httpx.Client(timeout=35, follow_redirects=False, trust_env=False,
                                   headers={"User-Agent": "aicom-paid-cycle-verifier/1"})
        self.checked_rpc_chains = set()
        self.verifier = object.__new__(Signer)  # keyless canonical methods only
        self.journal_path = PRIVATE / (target_name + ".json")
        self.summary = {"hub": target_name, "base": self.base, "client_started_utc": utc(),
                        "financial_mutations_by_preflight": 0, "ok": False,
                        "principal_atomic": self.target["amount_atomic"],
                        "fee_cap_wei": str(FEE_CAP)}

    def request(self, method: str, path: str, *, body=None, token=""):
        headers = {"X-Operation-Token": token} if token else {}
        response = self.client.request(method, self.base + path, json=body, headers=headers)
        require(200 <= response.status_code < 300,
                "Hub refused request; retain the existing operation and payment")
        require(len(response.content) <= 2_000_000, "Hub response exceeds client bound")
        return response, response.json()

    def rpc(self, method: str, params: list):
        # Sending and valid-authorization estimation never retry or change RPC.
        # This fallback is strictly for the named read-only methods.
        pool = READ_RPC_POOL if method in READ_METHODS else READ_RPC_POOL[:1]
        for label, url in pool:
            try:
                if method in READ_METHODS and method != "eth_chainId" and url not in self.checked_rpc_chains:
                    check = self.client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                                       "method": "eth_chainId", "params": []})
                    check.raise_for_status()
                    require(int(check.json().get("result", "0x0"), 16) == CHAIN,
                            "Read-only fallback RPC is not Base mainnet")
                    self.checked_rpc_chains.add(url)
                response = self.client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                                      "method": method, "params": params})
                response.raise_for_status()
                value = response.json()
                require("error" not in value and "result" in value,
                        "Chain RPC unavailable; reconcile the saved transaction before retry")
                if method == "eth_chainId":
                    require(int(value["result"], 16) == CHAIN, "RPC is not Base mainnet")
                    self.checked_rpc_chains.add(url)
                return value["result"]
            except (httpx.HTTPError, ValueError, Stop) as exc:
                response = getattr(exc, "response", None)
                self.summary.setdefault("rpc_diagnostics", []).append({
                    "endpoint": label, "method": method,
                    "http_status": response.status_code if response is not None else None,
                    "error_type": type(exc).__name__, "params_or_body_recorded": False})
                if method not in READ_METHODS:
                    raise
        raise Stop("All bounded read-only RPC endpoints unavailable; retain the same payment")

    def call(self, to: str, data: str):
        return self.rpc("eth_call", [{"to": to, "data": data}, "latest"])

    def balance(self, who: str):
        return int(self.call(TOKEN, selector("balanceOf(address)") +
                             encode(["address"], [who]).hex()), 16)

    def chain_clock(self):
        require(int(self.rpc("eth_chainId", []), 16) == CHAIN, "Wrong RPC chain")
        block = self.rpc("eth_getBlockByNumber", ["latest", False])
        require(block and block.get("hash"), "Latest chain block unavailable")
        response, _ = self.request("GET", "/ai-market/v2/health")
        server_now = email.utils.parsedate_to_datetime(response.headers["date"]).timestamp()
        chain_now = int(block["timestamp"], 16)
        require(abs(server_now - chain_now) <= 30, "Hub and chain clocks disagree")
        return server_now, chain_now, block

    def object_verified(self, document: dict):
        return Signer.verify_object_signature(document, self.target["public_key"],
                    require_pq=True, pq_public_key_b64=self.target["pq_public_key"])

    def preflight(self):
        _, discovery = self.request("GET", "/.well-known/ai-market.json")
        require(self.object_verified(discovery), "Discovery differs from saved hybrid pins")
        _, manifest = self.request("GET", "/ai-market/v2/manifest")
        require(Signer.verify_hybrid(self.target["public_key"], manifest.get("signature", {}),
                    self.verifier.manifest_canonical(manifest), require_pq=True,
                    pq_public_key_b64=self.target["pq_public_key"]),
                "Manifest differs from saved hybrid pins")
        server_now, chain_now, block = self.chain_clock()
        pending = int(self.rpc("eth_getTransactionCount", [PAYER, "pending"]), 16)
        latest = int(self.rpc("eth_getTransactionCount", [PAYER, "latest"]), 16)
        # Pending nonce is checked again immediately before signing and broadcasting.
        require(pending == latest, "Buyer has an unresolved pending transaction")
        token_code = self.rpc("eth_getCode", [TOKEN, "latest"])
        require(token_code not in ("0x", "0x0"), "USDC code unavailable")
        require(int(self.call(TOKEN, selector("decimals()")), 16) == 6,
                "Unexpected token decimals")
        for function, wanted in [("name()", "USD Coin"), ("version()", "2")]:
            actual = decode(["string"], bytes.fromhex(self.call(TOKEN, selector(function))[2:]))[0]
            require(actual == wanted, "Token EIP-712 domain changed")
        before = {"payer_usdc_atomic": self.balance(PAYER),
                  "payee_usdc_atomic": self.balance(self.target["payee"]),
                  "payer_eth_wei": int(self.rpc("eth_getBalance", [PAYER, "latest"]), 16)}
        require(before["payer_usdc_atomic"] >= self.target["amount_atomic"] and
                before["payer_eth_wei"] >= FEE_CAP, "Insufficient owned funds")
        self.summary.update(discovery_hybrid_verified=True, manifest_hybrid_verified=True,
                            buyer=PAYER, chain_id=CHAIN, token=TOKEN,
                            payee=self.target["payee"], public_pin_source=self.target["pin_source"],
                            token_code_sha256=hashlib.sha256(bytes.fromhex(token_code[2:])).hexdigest(),
                            server_time=server_now, chain_time=chain_now,
                            controller_clock_offset_s=round(time.time() - server_now, 3),
                            pending_nonce=pending, balances_before=before,
                            latest_block_number=int(block["number"], 16))
        return pending

    def approval(self):
        return Approval(self.base, self.target["product_id"], self.target["capability_id"],
                        PAYER, CHAIN, TOKEN, self.target["payee"], self.target["amount_atomic"],
                        200_000, FEE_CAP, FEE_CAP)

    def prepare(self):
        require(not self.journal_path.exists(),
                "Prior journal exists; use --resume, never prepare a replacement payment")
        server_now, chain_now, _ = self.chain_clock()
        _, prepared = self.request("POST", BASE + "/prepare", body={
            "product_id": self.target["product_id"], "capability_id": self.target["capability_id"],
            "wallet": PAYER, "max_price_usd": float(self.target["max_price_usd"])})
        require(isinstance(prepared.get("operation_token"), str) and
                len(prepared["operation_token"]) >= 32, "Operation bearer token missing")
        offer = prepared["offer"]
        checked = validate_offer(offer, self.approval(), signature_verified=self.object_verified(offer),
                                 server_now=server_now, chain_now=chain_now)
        validate_input(offer["input_schema"], self.target["input"])
        state = {"phase": "prepared", "target": self.name, "created_client_utc": utc(),
                 "prepared": prepared, "checked": checked,
                 "input": self.target["input"], "input_sha256": digest(self.target["input"]),
                 "summary_before": self.summary}
        exclusive_private_checkpoint(self.journal_path, state)
        self.summary.update(operation_id=offer["operation_id"], offer_hybrid_verified=True,
                            offer_sha256=digest(offer), input_sha256=state["input_sha256"],
                            input_offline_validated=True)
        return state

    def aggregate_budget(self, state):
        states = [json.loads(p.read_text()) for p in PRIVATE.glob("*.json")
                  if p != self.journal_path]
        # An EIP-3009 authorization is a principal commitment even when our own
        # transaction was never built: the estimator's RPC could relay it.
        signed = [s for s in states if s.get("authorization_signature") or s.get("signed_transaction")]
        principal = sum(s["summary_before"]["principal_atomic"] for s in signed)
        fees = sum(int(s["fee_bound_wei"]) for s in signed)
        require(principal + self.target["amount_atomic"] <= PRINCIPAL_CAP and
                fees + int(state["fee_bound_wei"]) <= TOTAL_FEE_CAP,
                "Three-hub aggregate payment budget exceeded")

    def sign_and_send(self, state, expected_nonce):
        server_now, chain_now, _ = self.chain_clock()
        checked = validate_offer(state["prepared"]["offer"], self.approval(),
                                 signature_verified=self.object_verified(state["prepared"]["offer"]),
                                 server_now=server_now, chain_now=chain_now)
        offer = state["prepared"]["offer"]
        shaped = {"nonce": checked["nonce"], "accepts": [{"scheme": "exact",
            "network": "eip155:8453", "asset": TOKEN, "payTo": self.target["payee"],
            "amount": str(self.target["amount_atomic"]), "extra": {"name": "USD Coin",
            "version": "2", "chainId": CHAIN, "verifyingContract": TOKEN}}]}
        typed = typed_data(shaped, sender=PAYER, valid_before=min(checked["valid_before"], chain_now + 180))
        price = int(self.rpc("eth_gasPrice", []), 16)
        max_fee, priority = 2 * price, min(price, 1_000_000)
        l1 = int(self.call(L1_ORACLE, selector("getL1FeeUpperBound(uint256)") +
                           encode(["uint256"], [1024]).hex()), 16)
        conservative_fee = 200_000 * max_fee + 100 * l1
        require(0 < max_fee and conservative_fee <= FEE_CAP,
                "Worst-case fee envelope exceeds authorized cap before signing")
        # Approve the complete principal/fee envelope before any spendable
        # signature is created or exposed, including at-risk previous attempts.
        state["fee_bound_wei"] = str(conservative_fee)
        self.aggregate_budget(state)
        wallet = json.loads((Path.home() / ".aicom-pov-buyer.json").read_text())
        account = Account.from_key(wallet.pop("private_key"))
        wallet.clear()
        require(account.address.lower() == PAYER.lower(), "Wrong owned buyer wallet")
        signed_auth = account.sign_message(encode_typed_data(full_message=typed)).signature.hex()
        data = calldata(typed, signed_auth)
        # A valid authorization is spendable even before this buyer broadcasts.
        # Checkpoint it before giving its calldata to the RPC gas estimator.
        state.update(phase="authorization_signed", authorization=typed,
                     authorization_signature=signed_auth)
        atomic_json(self.journal_path, state, private=True)
        require(int(self.call(TOKEN, selector("authorizationState(address,bytes32)") +
                    encode(["address", "bytes32"], [PAYER, bytes.fromhex(checked["nonce"][2:])]).hex()), 16) == 0,
                "Authorization nonce was already used")
        estimate = int(self.rpc("eth_estimateGas", [{"from": PAYER, "to": TOKEN,
                                                     "data": data, "value": "0x0"}]), 16)
        gas = (estimate * 125 + 99) // 100
        bound = gas * max_fee + 100 * l1
        require(0 < gas <= 200_000 and 0 < max_fee and bound <= FEE_CAP,
                "Gas plus conservative L1 bound exceeds authorized cap")
        require(int(self.rpc("eth_getTransactionCount", [PAYER, "pending"]), 16) == expected_nonce and
                int(self.rpc("eth_getTransactionCount", [PAYER, "latest"]), 16) == expected_nonce,
                "Buyer transaction nonce changed")
        require(self.balance(PAYER) >= self.target["amount_atomic"] and
                int(self.rpc("eth_getBalance", [PAYER, "latest"]), 16) >= bound,
                "Owned balance changed or insufficient")
        server_now, chain_now, _ = self.chain_clock()
        require(int(typed["message"]["validBefore"]) - max(server_now, chain_now) >= 45 and
                offer["invoice"]["expires_at"] - max(server_now, chain_now) >= 60,
                "Gas estimation consumed authorization lifetime; stop without broadcast")
        tx = {"chainId": CHAIN, "nonce": expected_nonce, "to": TOKEN, "value": 0,
              "data": data, "gas": gas, "maxFeePerGas": max_fee,
              "maxPriorityFeePerGas": priority, "type": 2}
        signed = account.sign_transaction(tx)
        raw = signed.raw_transaction
        require(len(raw) <= 1024, "Signed transaction exceeds L1 byte-size bound")
        tx_hash = "0x" + keccak(raw).hex()
        state.update(phase="signed", transaction=tx, transaction_hash=tx_hash,
                     signed_transaction="0x" + raw.hex(), authorization=typed,
                     fee_bound_wei=str(bound), l1_fee_bound_wei=str(100 * l1))
        self.aggregate_budget(state)
        atomic_json(self.journal_path, state, private=True)
        self.summary.update(transaction_hash=tx_hash, transaction_nonce=expected_nonce,
                            gas_limit=gas, max_fee_per_gas_wei=str(max_fee),
                            fee_bound_wei=str(bound))
        server_now, chain_now, _ = self.chain_clock()
        require(int(typed["message"]["validBefore"]) - max(server_now, chain_now) >= 30,
                "Authorization too near expiry before broadcast; retain saved transaction")
        # From this durable transition onward no code may create another payment.
        state.update(phase="broadcast_attempted", broadcast_client_utc=utc())
        atomic_json(self.journal_path, state, private=True)
        sent = self.rpc("eth_sendRawTransaction", [state["signed_transaction"]])
        require(str(sent).lower() == tx_hash.lower(), "Unexpected broadcast result; reconcile saved hash")
        state["phase"] = "broadcast_returned"
        atomic_json(self.journal_path, state, private=True)

    def confirm_and_execute(self, state):
        require(state.get("transaction_hash") and state.get("signed_transaction"),
                "No signed payment saved; no replacement quote or signing on resume")
        require(state["target"] == self.name and state["input"] == self.target["input"] and
                state["input_sha256"] == digest(self.target["input"]), "Saved immutable request changed")
        offer = state["prepared"]["offer"]
        require(self.object_verified(offer), "Saved offer signature invalid")
        tx_hash = state["transaction_hash"]
        require("0x" + keccak(bytes.fromhex(state["signed_transaction"][2:])).hex() == tx_hash,
                "Saved transaction hash differs from signed bytes")
        minimum_confirmations = max(3, int(offer["terms"]["min_confirmations"]))
        require(3 <= minimum_confirmations <= 100, "Unexpected confirmation policy; retain payment")
        receipt = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            receipt = self.rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                head = int(self.rpc("eth_blockNumber", []), 16)
                if head - int(receipt["blockNumber"], 16) + 1 >= minimum_confirmations:
                    break
            time.sleep(2)
        else:
            raise Stop("Confirmations pending; use --resume with this same saved transaction")
        mined_block = self.rpc("eth_getBlockByNumber", [receipt["blockNumber"], False])
        proof = verify_exact_direct_receipt(receipt, replace(self.approval(),
            min_confirmations=minimum_confirmations), tx_hash=tx_hash,
            nonce=offer["invoice"]["nonce"], head_number=head, mined_block=mined_block,
            invoice_expires_at=offer["invoice"]["expires_at"])
        # Compare the public chain transaction with the exact signed local plan.
        mined_tx = self.rpc("eth_getTransactionByHash", [tx_hash])
        planned = state["transaction"]
        require(mined_tx and mined_tx["from"].lower() == PAYER.lower() and
                mined_tx["to"].lower() == TOKEN.lower() and
                int(mined_tx["nonce"], 16) == planned["nonce"] and
                int(mined_tx["value"], 16) == 0 and
                mined_tx.get("input", "").lower() == planned["data"].lower() and
                int(mined_tx["chainId"], 16) == CHAIN, "Mined transaction differs from approved plan")
        actual_fee = int(receipt["gasUsed"], 16) * int(receipt["effectiveGasPrice"], 16)
        require("l1Fee" in receipt, "Actual L1 fee unavailable; retain same payment")
        actual_fee += int(receipt["l1Fee"], 16)
        require(actual_fee <= int(state["fee_bound_wei"]) <= FEE_CAP,
                "Actual fee exceeds signed bound")
        state.update(phase="confirmed", chain_receipt=receipt, mined_transaction=mined_tx,
                     mined_block=mined_block)
        atomic_json(self.journal_path, state, private=True)
        operation_id = offer["operation_id"]
        request = {"input": state["input"], "wallet": PAYER, "tx_hash": tx_hash}
        token = state["prepared"]["operation_token"]
        # Same immutable request only. The server's durable claim controls retries.
        _, answer = self.request("POST", BASE + "/" + operation_id + "/invoke", body=request, token=token)
        state["last_operation_answer"] = answer
        atomic_json(self.journal_path, state, private=True)
        self.summary["operation_status"] = answer.get("status")
        self.check_answer(answer, state)
        _, persisted = self.request("GET", BASE + "/" + operation_id, token=token)
        self.check_answer(persisted, state)
        require(canonical(persisted) == canonical(answer),
                "Persistent signed GET differs from completed operation")
        _, replay = self.request("POST", BASE + "/" + operation_id + "/invoke", body=request, token=token)
        self.check_answer(replay, state)
        require(canonical(replay) == canonical(answer), "Same-operation replay did not return cached result")
        if self.name == "attested":
            result = answer.get("result") or {}
            pairs = result.get("contradictions") or []
            require(result.get("method") == "lexical-negation-v1" and len(pairs) == 1 and
                    pairs[0].get("left_index") == 0 and pairs[0].get("right_index") == 1,
                    "Attested paid result differs from the expected synthetic contradiction")
        after = {"payer_usdc_atomic": self.balance(PAYER),
                 "payee_usdc_atomic": self.balance(self.target["payee"]),
                 "payer_eth_wei": int(self.rpc("eth_getBalance", [PAYER, "latest"]), 16)}
        before = state["summary_before"]["balances_before"]
        require(before["payer_usdc_atomic"] - after["payer_usdc_atomic"] == self.target["amount_atomic"],
                "Buyer USDC delta differs from the single approved payment")
        state.update(phase="completed", answer=answer, persisted=persisted,
                     replay=replay, balances_after=after)
        atomic_json(self.journal_path, state, private=True)
        self.summary.update(ok=True, phase="completed", **proof,
                            actual_fee_wei=str(actual_fee), balances_after=after,
                            buyer_usdc_delta_atomic=before["payer_usdc_atomic"] - after["payer_usdc_atomic"],
                            payee_usdc_delta_atomic=after["payee_usdc_atomic"] - before["payee_usdc_atomic"],
                            same_operation_cached_replay=True, offer_hybrid_verified=True,
                            persisted_signed_get_identical=True,
                            response_hybrid_verified=True, charged_receipt_hybrid_verified=True,
                            charged_receipt_nonce=answer["receipt"]["nonce"],
                            result_sha256=digest(answer["result"]), result_not_stored_publicly=True,
                            operation_id=operation_id, offer_sha256=digest(offer),
                            operation_response_sha256=digest(answer),
                            ledger_rows_require_independent_readonly_confirmation=True)

    def check_answer(self, answer, state):
        offer = state["prepared"]["offer"]
        require(self.object_verified(answer), "Operation response hybrid signature invalid")
        require(answer.get("operation_id") == offer["operation_id"] and
                answer.get("product_id") == self.target["product_id"] and
                answer.get("capability_id") == self.target["capability_id"] and
                answer.get("wallet", "").lower() == PAYER.lower() and
                answer.get("tx_hash", "").lower() == state["transaction_hash"].lower() and
                answer.get("offer_digest") == digest(offer) and
                answer.get("input_digest") == state["input_sha256"], "Operation response binding mismatch")
        require(answer.get("status") == "completed" and answer.get("success") is True and
                answer.get("busy") is False, "Operation not complete; retain same operation/payment")
        receipt = answer.get("receipt") or {}
        version = receipt_signature_version(receipt)
        require(version > 0 and any(Signer.verify_hybrid(self.target["public_key"],
                    receipt.get("signature", {}), canonical_receipt, require_pq=True,
                    pq_public_key_b64=self.target["pq_public_key"])
                    for canonical_receipt in self.verifier.receipt_canonical_candidates(receipt, version)),
                "Charged receipt hybrid signature invalid")
        require(receipt.get("success") is True and not receipt.get("sandbox") and
                receipt.get("product_id") == self.target["product_id"] and
                receipt.get("capability_id") == self.target["capability_id"] and
                Decimal(str(receipt.get("price_usd"))) == Decimal(self.target["max_price_usd"]),
                "Receipt is uncharged, sandbox, or bound to another listing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", required=True, choices=("factory", "independent", "attested"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--sign-preview", action="store_true", help="Validate a signed offer; never load buyer key")
    mode.add_argument("--execute", action="store_true", help="Explicitly authorized single real payment")
    mode.add_argument("--resume", action="store_true", help="Recover same operation and transaction; no signing/broadcast")
    args = parser.parse_args()
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(PRIVATE.stat().st_mode & 0o077 == 0 and PRIVATE.stat().st_uid == os.getuid(),
            "Private journal directory ownership/mode unsafe")
    runner = Runner(args.hub)
    lock = open(PRIVATE / ".buyer.lock", "a+b")
    os.chmod(PRIVATE / ".buyer.lock", 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            require(runner.journal_path.exists(), "No prior payment to resume")
            state = json.loads(runner.journal_path.read_text())
            runner.summary.update(state["summary_before"])
            runner.summary.update(resume_only=True, ok=False)
            runner.confirm_and_execute(state)
        else:
            nonce = runner.preflight()
            if args.execute or args.sign_preview:
                if runner.journal_path.exists():
                    state = json.loads(runner.journal_path.read_text())
                    require(state.get("phase") == "prepared" and state.get("target") == args.hub and
                            state.get("input") == runner.target["input"],
                            "Prior signed/attempted payment exists; use --resume only")
                    # Preserve the original quote checkpoint but use this cycle's
                    # current balances after any earlier, separately paid hub.
                    state["summary_before"] = runner.summary
                    atomic_json(runner.journal_path, state, private=True)
                else:
                    state = runner.prepare()
                if args.execute:
                    runner.sign_and_send(state, nonce)
                    runner.confirm_and_execute(state)
                else:
                    runner.summary.update(ok=True, phase="signed_offer_preview_only",
                                          buyer_key_loaded=False, broadcast_attempted=False)
            else:
                runner.summary.update(ok=True, phase="readonly_preflight", buyer_key_loaded=False,
                                      broadcast_attempted=False)
    except BaseException as exc:
        runner.summary.update(ok=False, error_type=type(exc).__name__,
            error=str(exc) if isinstance(exc, Stop) else "Stopped; private journal must be reconciled before retry")
    finally:
        runner.client.close()
        runner.summary["client_finished_utc"] = utc()
        output = HERE / (args.hub + ("-preflight.json" if not args.execute and not args.resume else "-cycle.json"))
        atomic_json(output, runner.summary, private=False)
        print(json.dumps(runner.summary, sort_keys=True))
        lock.close()
    return 0 if runner.summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
