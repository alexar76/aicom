"""Offline checks only: no real quote, key, funds, RPC, or Hub database."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from payment_guards import (Approval, Stop, exclusive_private_checkpoint,
                            validate_offer, verify_exact_direct_receipt,
                            AUTHORIZATION_USED, TRANSFER)

PAYER = "0x" + "11" * 20
PAYEE = "0x" + "22" * 20
TOKEN = "0x" + "33" * 20
NONCE = "0x" + "44" * 32
TX = "0x" + "55" * 32
BLOCK = "0x" + "66" * 32


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Financial guard tests must make zero actual network calls")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def approval():
    return Approval("https://owned.example/hub", "product", "safe.read@v1", PAYER,
                    8453, TOKEN, PAYEE, 2000, 200_000, 10**9, 10**10)


@pytest.fixture
def offer():
    return {"protocol": "SELLER-OP/1", "operation_id": "op_" + "01" * 16,
            "product_id": "product", "capability_id": "safe.read@v1", "wallet": PAYER,
            "terms": {"chain_id": 8453, "decimals": 6, "token_contract": TOKEN,
                      "min_confirmations": 1,
                      "pay_to": PAYEE, "amount_units": 2000, "amount_usd": .002,
                      "fee_units": 0, "offer_to": PAYEE,
                      "eip712_name": "USD Coin", "eip712_version": "2"},
            "invoice": {"nonce": NONCE, "expires_at": 1300}, "expires_at": 1300}


def test_expiry_bound_to_invoice_not_controller_clock(offer, approval):
    result = validate_offer(offer, approval, signature_verified=True,
                            server_now=1100, chain_now=1100)
    assert result["valid_before"] == 1285
    assert result["valid_before"] < offer["invoice"]["expires_at"]


@pytest.mark.parametrize("change", ["price", "recipient", "chain", "payer", "token",
                                    "fee", "expiry", "domain", "operation"])
def test_immutable_terms_fail_closed(offer, approval, change):
    changed = deepcopy(offer)
    if change == "price":
        changed["terms"]["amount_units"] += 1
    elif change == "recipient":
        changed["terms"]["pay_to"] = PAYER
    elif change == "chain":
        changed["terms"]["chain_id"] = 31337
    elif change == "payer":
        changed["wallet"] = PAYEE
    elif change == "token":
        changed["terms"]["token_contract"] = PAYEE
    elif change == "fee":
        changed["terms"]["fee_units"] = 1
    elif change == "expiry":
        changed["invoice"]["expires_at"] = changed["expires_at"] = 1120
    elif change == "domain":
        changed["terms"]["eip712_version"] = "1"
    else:
        changed["protocol"] = "unknown"
    with pytest.raises(Stop):
        validate_offer(changed, approval, signature_verified=True, server_now=1100, chain_now=1100)


def test_unsigned_offer_or_bad_clock_refused(offer, approval):
    with pytest.raises(Stop):
        validate_offer(offer, approval, signature_verified=False, server_now=1100, chain_now=1100)
    with pytest.raises(Stop):
        validate_offer(offer, approval, signature_verified=True, server_now=1100, chain_now=4500)


def topic(address):
    return "0x" + address[2:].zfill(64)


@pytest.fixture
def chain_receipt():
    return {"transactionHash": TX, "status": "0x1", "blockNumber": "0x64", "blockHash": BLOCK,
            "logs": [{"address": TOKEN, "topics": [AUTHORIZATION_USED, topic(PAYER), NONCE], "data": "0x"},
                     {"address": TOKEN, "topics": [TRANSFER, topic(PAYER), topic(PAYEE)], "data": hex(2000)}]}


def proof(receipt, approval, **kwargs):
    return verify_exact_direct_receipt(receipt, approval, tx_hash=TX, nonce=NONCE,
        head_number=kwargs.get("head", 102), mined_block={"hash": BLOCK, "number": "0x64", "timestamp": hex(1100)},
        invoice_expires_at=kwargs.get("expiry", 1300))


def test_chain_proof_exact_adjacent_authorization_transfer(chain_receipt, approval):
    assert proof(chain_receipt, approval)["chain_receipt_exact"] is True


@pytest.mark.parametrize("change", ["wrong_nonce", "overpay", "wrong_recipient", "extra_spend",
                                    "reverted", "unrelated_transfer", "not_adjacent"])
def test_transfer_proof_refuses_lookalikes(chain_receipt, approval, change):
    changed = deepcopy(chain_receipt)
    if change == "wrong_nonce":
        changed["logs"][0]["topics"][2] = TX
    elif change == "overpay":
        changed["logs"][1]["data"] = hex(2001)
    elif change == "wrong_recipient":
        changed["logs"][1]["topics"][2] = topic(PAYER)
    elif change == "extra_spend":
        changed["logs"].append(deepcopy(changed["logs"][1]))
    elif change == "reverted":
        changed["status"] = "0x0"
    elif change == "unrelated_transfer":
        changed["logs"][0]["address"] = PAYEE
    else:
        changed["logs"].insert(1, {"address": TOKEN, "topics": [TX], "data": "0x"})
    with pytest.raises(Stop):
        proof(changed, approval)


def test_paid_after_expiry_and_insufficient_confirmations_refused(chain_receipt, approval):
    with pytest.raises(Stop):
        proof(chain_receipt, approval, expiry=1100)
    with pytest.raises(Stop):
        proof(chain_receipt, approval, head=101)


def test_checkpoint_is_exclusive_and_private(tmp_path):
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "private.json"
    exclusive_private_checkpoint(path, {"transaction_hash": TX, "phase": "signed"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        exclusive_private_checkpoint(path, {"transaction_hash": BLOCK})
    assert json.loads(path.read_text())["transaction_hash"] == TX


def test_checkpoint_refuses_public_directory(tmp_path):
    os.chmod(tmp_path, 0o755)
    with pytest.raises(Stop):
        exclusive_private_checkpoint(tmp_path / "private.json", {"transaction_hash": TX})


def test_protocol_digest_uses_server_ascii_canonical():
    spec = importlib.util.spec_from_file_location("paid_runner", HERE.parent / "run_paid_cycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import hashlib
    payload = {"schema": {"description": "проверка"}}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        allow_nan=False).encode()).hexdigest()
    assert module.digest(payload) == expected
    module.validate_input({"type": "object", "properties": {"v": {"type": "integer"}},
                           "required": ["v"]}, {"v": 1})
    with pytest.raises(Stop):
        module.validate_input({"$ref": "http://metadata.internal/schema"}, {"v": 1})


def test_aggregate_counts_relayable_authorization_before_our_transaction(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("paid_runner_budget", HERE.parent / "run_paid_cycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PRIVATE", tmp_path)
    runner = object.__new__(module.Runner)
    runner.journal_path = tmp_path / "independent.json"
    runner.target = {"amount_atomic": 2000}
    # Authorization-only attempts are at risk even without a transaction hash.
    prior = {"phase": "authorization_signed", "authorization_signature": "synthetic-test-only",
             "fee_bound_wei": str(10**12), "summary_before": {"principal_atomic": 12000}}
    (tmp_path / "factory.json").write_text(json.dumps(prior))
    with pytest.raises(Stop):
        runner.aggregate_budget({"fee_bound_wei": str(10**12)})
    prior["summary_before"]["principal_atomic"] = 11000
    (tmp_path / "factory.json").write_text(json.dumps(prior))
    runner.aggregate_budget({"fee_bound_wei": str(10**12)})
    # Rechecking the current signed record never counts its amount twice.
    runner.journal_path.write_text(json.dumps(prior))
    runner.aggregate_budget({"fee_bound_wei": str(10**12)})
    prior["fee_bound_wei"] = str(3 * 10**13)
    (tmp_path / "factory.json").write_text(json.dumps(prior))
    with pytest.raises(Stop):
        runner.aggregate_budget({"fee_bound_wei": str(10**12)})
