"""Exact buyer-authorized payments for pipeline.run.

The buyer signs EIP-3009. The containing type-2 transaction is signed either by
the buyer or an explicitly validated gas sponsor, immediately before its step.
"""
from __future__ import annotations

import asyncio
import math
import re

from aimarket_hub import settle


def authorization_data(step: dict, wallet: str) -> dict:
    t, invoice = step["terms"], step["invoice"]
    primary = "ReceiveWithAuthorization" if int(t["fee_units"]) else "TransferWithAuthorization"
    return {
        "types": {
            "EIP712Domain": [{"name": n, "type": k} for n, k in (
                ("name", "string"), ("version", "string"), ("chainId", "uint256"), ("verifyingContract", "address"))],
            primary: [{"name": n, "type": k} for n, k in (
                ("from", "address"), ("to", "address"), ("value", "uint256"),
                ("validAfter", "uint256"), ("validBefore", "uint256"), ("nonce", "bytes32"))],
        },
        "primaryType": primary,
        "domain": {"name": t["eip712_name"], "version": t["eip712_version"],
                   "chainId": t["chain_id"], "verifyingContract": t["token_contract"]},
        "message": {"from": wallet, "to": t["offer_to"], "value": str(t["amount_units"]),
                    "validAfter": "0", "validBefore": str(math.floor(invoice["expires_at"])),
                    "nonce": invoice["nonce"]},
    }


def payment_transaction(step: dict, wallet: str, signature: str) -> dict:
    if not re.fullmatch(r"0x[0-9a-fA-F]{130}", signature):
        raise ValueError("invalid authorization signature")
    t = step["terms"]
    v = int(signature[-2:], 16)
    if v not in (27, 28):
        raise ValueError("invalid authorization recovery id")
    def word(s):
        return str(s).removeprefix("0x").lower().zfill(64)
    def number(n):
        return format(int(n), "064x")
    split = int(t["fee_units"]) > 0
    args = [word(t["token_contract"] if split else wallet), word(t["pay_to"]),
            number(t["amount_units"]), number(0), number(math.floor(step["invoice"]["expires_at"])),
            word(step["invoice"]["nonce"]), number(v), signature[2:66].lower(), signature[66:130].lower()]
    if split:
        args.append("0" * 64)
    return {"from": wallet, "to": t["offer_to"] if split else t["token_contract"],
            "data": ("0x6e92be7a" if split else "0xe3ee160e") + "".join(args), "value": 0}


def validate_authorization(step: dict, wallet: str, signature: str) -> None:
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    payment_transaction(step, wallet, signature)  # Validate the fixed ABI signature format.
    recovered = Account.recover_message(encode_typed_data(full_message=authorization_data(step, wallet)),
                                        signature=signature)
    if recovered.lower() != wallet.lower():
        raise ValueError("authorization signer differs from the prepared wallet")


def validate_transaction(step: dict, wallet: str, raw: str, *, gas_payer: str | None = None) -> dict:
    """Validate before ANY transfer: recipient, calldata, both signatures, chain, nonce.

    Type-2 only: no contract creation, access lists or EIP-7702 delegations. The
    optional escrow dependencies are imported only for wallet-funded execution.
    """
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_account.typed_transactions import TypedTransaction
    from eth_utils import keccak
    from hexbytes import HexBytes

    try:
        encoded = HexBytes(raw)
        if not encoded or encoded[0] != 2 or len(encoded) > 2048:
            raise ValueError("only bounded EIP-1559 payment transactions are supported")
        tx = TypedTransaction.from_bytes(encoded).as_dict()
        if gas_payer and gas_payer.lower() != wallet.lower() and int(step["terms"]["fee_units"]):
            raise ValueError("the existing splitter requires a buyer-sent transaction")
        if Account.recover_transaction(encoded).lower() != (gas_payer or wallet).lower():
            raise ValueError("transaction signer differs from the prepared wallet")
        data = "0x" + bytes(tx["data"]).hex()
        # v,r,s occupy the same slots in the direct and splitter ABIs.
        v = int(data[10 + 6 * 64:10 + 7 * 64], 16)
        signature = "0x" + data[10 + 7 * 64:10 + 9 * 64] + format(v, "02x")
        expected = payment_transaction(step, wallet, signature)
        if (data.lower() != expected["data"].lower()
                or "0x" + bytes(tx["to"]).hex() != expected["to"].lower()
                or int(tx["value"]) != 0 or int(tx["chainId"]) != step["terms"]["chain_id"]
                or tx.get("accessList") or not 0 < int(tx["gas"]) <= 1_000_000):
            raise ValueError("transaction differs from the prepared step payment")
        recovered = Account.recover_message(encode_typed_data(full_message=authorization_data(step, wallet)),
                                            signature=signature)
        if recovered.lower() != wallet.lower():
            raise ValueError("authorization signer differs from the prepared wallet")
        return {"raw": "0x" + bytes(encoded).hex(), "tx_hash": "0x" + keccak(encoded).hex(),
                "nonce": int(tx["nonce"])}
    except Exception as exc:
        # RLP and signature libraries have their own exception hierarchies. Malformed
        # caller bytes are a refused offer, never a server-side execution failure.
        raise ValueError(f"invalid signed payment: {exc}") from exc


async def broadcast(raw: str, expected_hash: str) -> None:
    # Identical bytes imply the same chain hash and nonce. A retry can never create
    # a second transfer. A timeout remains ambiguous until verification succeeds.
    from eth_account.typed_transactions import TypedTransaction
    from hexbytes import HexBytes
    chain_id = int(TypedTransaction.from_bytes(HexBytes(raw)).as_dict()["chainId"])
    urls = settle.rpc_urls(chain_id)
    if not urls:
        raise settle.PaymentError("no settlement RPC configured")
    observed = await asyncio.to_thread(settle._rpc, urls[0], "eth_chainId", [], 10.0)
    if int(observed,16) != chain_id: raise settle.PaymentError("broadcast RPC differs from the signed chain")
    returned = await asyncio.to_thread(settle._rpc, urls[0], "eth_sendRawTransaction", [raw], 10.0)
    if str(returned).lower() != expected_hash.lower():
        raise settle.PaymentError("RPC returned a different transaction hash")
