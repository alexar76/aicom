"""Offline-only guards for a separately authorized, exact direct EIP-3009 payment.

No networking, key loading, signing, broadcasting, quote creation or invocation.
The executor must independently verify the pinned Hub signature before calling
validate_offer. This deliberately refuses splitter/fee offers and escrow rails.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTHORIZATION_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"


class Stop(ValueError):
    """Stop execution; never compensate by purchasing a replacement invoice."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Approval:
    hub_origin: str
    product_id: str
    capability_id: str
    payer: str
    chain_id: int
    token: str
    payee: str
    amount_atomic: int
    max_gas: int
    max_fee_per_gas_wei: int
    max_l1_fee_wei: int
    min_confirmations: int = 3
    min_quote_remaining_s: int = 60

    def __post_init__(self) -> None:
        hub = urlsplit(self.hub_origin)
        require(hub.scheme == "https" and bool(hub.hostname) and not hub.username and
                not hub.password and not hub.query and not hub.fragment and
                not self.hub_origin.endswith("/"), "Hub must be one exact HTTPS base URL")
        for value in (self.payer, self.token, self.payee):
            require(bool(ADDRESS.fullmatch(value)), "Malformed approved address")
        require(self.chain_id == 8453, "This scaffold approves Base mainnet only")
        require(self.amount_atomic > 0 and self.max_gas > 0 and
                self.max_fee_per_gas_wei > 0 and self.max_l1_fee_wei >= 0,
                "Nonpositive amount or unbounded gas approval")


def validate_offer(offer: dict, approval: Approval, *, signature_verified: bool,
                   server_now: float, chain_now: float) -> dict:
    require(signature_verified is True, "Pinned whole-offer signature not verified")
    require(math.isfinite(server_now) and math.isfinite(chain_now) and
            abs(server_now - chain_now) <= 30, "Server/chain clocks disagree")
    require(offer.get("protocol") == "SELLER-OP/1", "Durable seller operation required")
    require(offer.get("product_id") == approval.product_id and
            offer.get("capability_id") == approval.capability_id, "Listing changed")
    require(offer.get("wallet", "").lower() == approval.payer.lower(), "Buyer changed")
    require(bool(re.fullmatch(r"op_[0-9a-f]{32}", offer.get("operation_id", ""))),
            "Invalid operation identifier")
    terms = offer.get("terms") or {}
    require(terms.get("chain_id") == approval.chain_id and terms.get("decimals") == 6,
            "Chain or token decimals changed")
    require(isinstance(terms.get("min_confirmations"), int) and
            1 <= terms["min_confirmations"] <= 100,
            "Unexpected confirmation policy")
    require(str(terms.get("token_contract", "")).lower() == approval.token.lower() and
            str(terms.get("pay_to", "")).lower() == approval.payee.lower(),
            "Asset or recipient changed")
    require(int(terms.get("amount_units", 0)) == approval.amount_atomic and
            Decimal(str(terms.get("amount_usd"))) == Decimal(approval.amount_atomic) / 10**6,
            "Exact price changed")
    require(int(terms.get("fee_units", 0)) == 0 and
            str(terms.get("offer_to") or approval.payee).lower() == approval.payee.lower(),
            "Splitter/fee route needs a separate approval")
    require(terms.get("eip712_name") == "USD Coin" and
            str(terms.get("eip712_version")) == "2", "Unexpected token signing domain")
    invoice = offer.get("invoice") or {}
    require(bool(HASH.fullmatch(invoice.get("nonce", ""))), "Invalid invoice nonce")
    expiry = float(invoice.get("expires_at", 0))
    require(math.isfinite(expiry) and expiry == float(offer.get("expires_at", 0)) and
            expiry - server_now >= approval.min_quote_remaining_s,
            "Invoice expired or too close to expiry")
    # A safety margin remains for mining; never extend validity beyond this invoice.
    valid_before = min(int(server_now) + 240, math.floor(expiry) - 15)
    require(valid_before - max(server_now, chain_now) >= 30,
            "Insufficient authorization lifetime")
    return {"operation_id": offer["operation_id"], "nonce": invoice["nonce"],
            "valid_after": 0, "valid_before": valid_before,
            "offer_sha256": digest(offer)}


def fee_budget(approval: Approval, *, gas: int, max_fee_per_gas: int,
               l1_fee_bound: int, raw_transaction_bytes: int) -> dict:
    require(0 < gas <= approval.max_gas and
            0 < max_fee_per_gas <= approval.max_fee_per_gas_wei and
            0 <= l1_fee_bound <= approval.max_l1_fee_wei and
            0 < raw_transaction_bytes <= 1024, "Transaction exceeds approved fee/size limits")
    wei = gas * max_fee_per_gas + l1_fee_bound
    return {"fee_bound_wei": str(wei)}


def verify_exact_direct_receipt(receipt: dict, approval: Approval, *, tx_hash: str,
                                nonce: str, head_number: int,
                                mined_block: dict, invoice_expires_at: float) -> dict:
    require(bool(HASH.fullmatch(tx_hash)) and bool(HASH.fullmatch(nonce)), "Invalid reference")
    require(str(receipt.get("transactionHash", "")).lower() == tx_hash.lower() and
            int(receipt.get("status", "0x0"), 16) == 1, "Missing/reverted transaction")
    block_number = int(receipt["blockNumber"], 16)
    require(head_number - block_number + 1 >= approval.min_confirmations,
            "Confirmations pending; retain same transaction")
    require(mined_block.get("hash", "").lower() == receipt.get("blockHash", "").lower() and
            int(mined_block["number"], 16) == block_number and
            int(mined_block["timestamp"], 16) < invoice_expires_at,
            "Block mismatch or payment mined after invoice expiry")
    logs = [log for log in receipt.get("logs", [])
            if log.get("address", "").lower() == approval.token.lower()]
    wanted_payer = approval.payer.lower()
    wanted_payee = approval.payee.lower()
    matches = 0
    payer_out = 0
    for index, log in enumerate(logs):
        topics = [str(t).lower() for t in log.get("topics", [])]
        if len(topics) >= 3 and topics[0] == TRANSFER:
            if "0x" + topics[1][-40:] == wanted_payer:
                payer_out += int(log.get("data", "0x0"), 16)
        if (len(topics) >= 3 and topics[0] == AUTHORIZATION_USED and
                "0x" + topics[1][-40:] == wanted_payer and topics[2] == nonce.lower()):
            require(index + 1 < len(logs), "Authorization has no adjacent Transfer")
            moved = logs[index + 1]
            mt = [str(t).lower() for t in moved.get("topics", [])]
            require(len(mt) >= 3 and mt[0] == TRANSFER and
                    "0x" + mt[1][-40:] == wanted_payer and
                    "0x" + mt[2][-40:] == wanted_payee and
                    int(moved.get("data", "0x0"), 16) == approval.amount_atomic,
                    "Authorization did not move the exact approved payment")
            matches += 1
    require(matches == 1 and payer_out == approval.amount_atomic,
            "Missing/ambiguous authorization or extra payer token spend")
    return {"chain_receipt_exact": True, "confirmations": head_number - block_number + 1,
            "amount_atomic": approval.amount_atomic, "transaction_hash": tx_hash.lower()}


def exclusive_private_checkpoint(path: Path, payload: dict) -> None:
    """Durable BEFORE-broadcast checkpoint. Existing records are never replaced.

    Pass only a private path outside public evidence. A known tx hash is the
    recovery key; an unknown send result must never produce a new authorization.
    No financial action is performed by writing this record.
    """
    parent = path.parent.resolve(strict=True)
    mode = stat.S_IMODE(parent.stat().st_mode)
    require(parent.stat().st_uid == os.getuid() and mode & 0o077 == 0,
            "Checkpoint directory must be owned and private (0700)")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(parent / path.name, flags, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(canonical(payload) + b"\n")
        file.flush()
        os.fsync(file.fileno())
    directory = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
