"""On-chain payment verification helpers for AI Market Protocol."""

from __future__ import annotations

from web.backend.api import payment as payment_api
from web.backend.services.ai_market_protocol.config import demo_payment_bypass


def normalize_tx_hash(tx_hash: str, *, chain: str) -> str:
    tx = (tx_hash or "").strip()
    if chain == "solana":
        return tx
    return tx if tx.startswith("0x") else f"0x{tx}"


def verify_tx_payment(*, tx_hash: str, amount_usd: float, chain: str, token: str) -> bool:
    if demo_payment_bypass() and (tx_hash.startswith("demo-") or tx_hash.startswith("0xdemo")):
        return True
    recipient = payment_api._get_address_for_chain(chain)
    if chain == "solana":
        verify = payment_api._verify_solana_transaction(
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount_usd,
            expected_token=token,
        )
    else:
        verify = payment_api._verify_evm_transaction(
            chain=chain,
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount_usd,
            expected_token=token,
        )
    return bool(verify.get("verified"))
