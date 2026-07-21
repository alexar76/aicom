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
    from core.crypto_config import crypto_enabled

    # Crypto OFF (default): there is no external chain to verify against — never
    # contact an RPC. Callers must not rely on on-chain payment when crypto is off
    # (the invoke path settles via UNI instead); a verification request here fails.
    if not crypto_enabled():
        return False
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


def verify_tx_payment_details(
    *, tx_hash: str, amount_usd: float, chain: str, token: str
) -> tuple[bool, str | None]:
    """Like :func:`verify_tx_payment` but also returns the on-chain SENDER address.

    Callers that credit value to an account (UNI top-up) must bind the credited
    account to the wallet that actually paid — verifying only recipient/amount
    lets anyone claim any inbound transfer to the shared settlement wallet.
    Returns ``(verified, from_address)``; ``from_address`` is ``None`` in the
    demo-bypass path (no real chain) so callers fail closed on the real path.
    """
    from core.crypto_config import crypto_enabled

    if not crypto_enabled():
        return False, None
    if demo_payment_bypass() and (tx_hash.startswith("demo-") or tx_hash.startswith("0xdemo")):
        return True, None
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
    if not verify.get("verified"):
        return False, None
    return True, verify.get("from")
