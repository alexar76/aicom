"""Offline exact-refund proof tests; no real keys, funds, RPC or provider calls."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("refund_factory_tested", ROOT / "refund_factory.py")
refund = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refund)


def topic(address):
    return "0x" + address[2:].lower().zfill(64)


@pytest.fixture
def bundle():
    raw = b"synthetic-proof-bytes-not-a-signed-transaction"
    tx_hash = "0x" + refund.keccak(raw).hex()
    block_hash = "0x" + "42" * 32
    state = {"original_tx": refund.ORIGINAL_TX, "original_operation": refund.ORIGINAL_OPERATION,
             "sender": refund.OPERATOR, "recipient": refund.PAYER, "token": refund.TOKEN,
             "amount_atomic": 2000, "chain_id": 8453, "transaction_hash": tx_hash,
             "signed_transaction": "0x" + raw.hex(), "transaction": {"nonce": 197},
             "fee_bound_wei": "10000000000000"}
    receipt = {"transactionHash": tx_hash, "status": "0x1", "blockNumber": "0x64", "blockHash": block_hash,
               "gasUsed": hex(45000), "effectiveGasPrice": hex(6000000), "l1Fee": hex(10000000),
               "logs": [{"address": refund.TOKEN, "topics": [refund.TRANSFER,
                         topic(refund.OPERATOR), topic(refund.PAYER)], "data": hex(2000)}]}
    transaction = {"hash": tx_hash, "from": refund.OPERATOR, "to": refund.TOKEN,
                   "chainId": hex(8453), "value": "0x0", "nonce": hex(197), "input": refund.transfer_data()}
    block = {"hash": block_hash, "number": "0x64"}
    return receipt, transaction, block, state


def test_exact_refund_to_original_buyer(bundle):
    result = refund.verify_refund_receipt(*bundle, head=102)
    assert result["refund_transfer_exact"] is True
    assert result["confirmations"] == 3


@pytest.mark.parametrize("tamper", ["recipient", "amount", "extra_spend", "chain", "ether_value",
                                    "transaction_nonce", "original_payment", "raw_bytes", "revert",
                                    "fee_cap", "unconfirmed"])
def test_refund_proof_fails_closed(bundle, tamper):
    receipt, transaction, block, state = deepcopy(bundle)
    head = 102
    if tamper == "recipient":
        receipt["logs"][0]["topics"][2] = topic(refund.OPERATOR)
    elif tamper == "amount":
        receipt["logs"][0]["data"] = hex(2001)
    elif tamper == "extra_spend":
        receipt["logs"].append(deepcopy(receipt["logs"][0]))
    elif tamper == "chain":
        transaction["chainId"] = hex(31337)
    elif tamper == "ether_value":
        transaction["value"] = "0x1"
    elif tamper == "transaction_nonce":
        transaction["nonce"] = hex(198)
    elif tamper == "original_payment":
        state["original_tx"] = "0x" + "99" * 32
    elif tamper == "raw_bytes":
        state["signed_transaction"] = "0x00"
    elif tamper == "revert":
        receipt["status"] = "0x0"
    elif tamper == "fee_cap":
        receipt["l1Fee"] = hex(10**13)
    else:
        head = 101
    with pytest.raises(refund.Stop):
        refund.verify_refund_receipt(receipt, transaction, block, state, head)


def test_transfer_calldata_is_fixed_recipient_and_exact_amount():
    from eth_abi import decode
    data = refund.transfer_data()
    assert data[:10] == "0xa9059cbb"
    address, amount = decode(["address", "uint256"], bytes.fromhex(data[10:]))
    assert address.lower() == refund.PAYER.lower() and amount == 2000


@pytest.mark.parametrize("change", [None, "busy", "completed", "receipt", "input"])
def test_current_signed_operation_must_stay_uncompleted_and_not_busy(change):
    runner = object.__new__(refund.Refund)
    runner.target = {"product_id": "weather-witness", "capability_id": "weather.witness@v1"}
    offer = {"operation_id": refund.ORIGINAL_OPERATION, "synthetic_test_only": True}
    state = {"prepared": {"offer": offer, "operation_token": "synthetic-token-not-a-real-secret"},
             "input_sha256": "synthetic-digest"}
    operation = {"operation_id": refund.ORIGINAL_OPERATION, "tx_hash": refund.ORIGINAL_TX,
        "wallet": refund.PAYER, "offer_digest": refund.digest(offer),
        "input_digest": state["input_sha256"], **runner.target,
        "status": "reconciliation_required", "success": False, "busy": False, "receipt": None}
    if change == "busy":
        operation["busy"] = True
    elif change == "completed":
        operation["status"] = "completed"
    elif change == "receipt":
        operation["receipt"] = {"success": True}
    elif change == "input":
        operation["input_digest"] = "changed"
    runner.request = lambda *args, **kwargs: (None, operation)
    runner.object_verified = lambda value: True  # cryptographic path reviewed separately
    if change:
        with pytest.raises(refund.Stop):
            runner.current_uncompleted_operation(state)
    else:
        assert runner.current_uncompleted_operation(state)["busy"] is False
