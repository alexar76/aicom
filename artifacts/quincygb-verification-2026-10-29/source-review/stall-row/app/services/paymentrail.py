"""Human payment rail: verify a direct on-chain USDC payment.

Buyers who cannot pay via x402 can send exactly $5.00 USDC on Base
directly to the fleet payTo wallet. This module verifies such a
payment from the transaction receipt alone — the same USDC Transfer
log parsing Receipt Verifier uses (app/services/receipts.py):

  * the transaction must exist and be confirmed (receipt present);
  * the receipt status must be successful (0x1);
  * a USDC Transfer log must pay the fleet payTo;
  * that transfer's sender must be the claimed buyer wallet;
  * its amount must be exactly 5_000_000 units ($5.00).

Anything else is a clean refusal (PaymentRailError) — no pack is
minted for a wrong amount, a wrong recipient, a different sender,
or an unconfirmed/failed transaction. Replay protection (one mint
per tx, ever) lives in the WatchStore's consumed-tx table
(app/services/recheck.py); this module only verifies.
"""

from __future__ import annotations

from ..discovery import USDC_ASSET
from ..rpc import Rpc, UpstreamError
from . import receipts as receipts_svc

EXPECTED_AMOUNT_UNITS = 5_000_000  # $5.00 — the Fleet Check pack price


class PaymentRailError(ValueError):
    """A payment that must be refused with a clean 4xx."""

    def __init__(self, message: str, http_status: int = 422, code: str = "payment_invalid"):
        super().__init__(message)
        self.http_status = http_status
        self.code = code


async def verify_usdc_payment(
    rpc: Rpc,
    *,
    tx_hash: str,
    buyer_wallet: str,
    pay_to: str,
    amount_units: int = EXPECTED_AMOUNT_UNITS,
) -> dict:
    """Verify one claimed $5.00 USDC payment. Returns the matched
    transfer {"from", "to", "amount_units"} on success; raises
    PaymentRailError on any verification failure and UpstreamError
    when the chain read itself fails (unknown/unconfirmed tx)."""
    receipt = await rpc.eth_receipt(tx_hash)
    if receipt is None:
        raise UpstreamError(
            f"transaction {tx_hash} has no receipt yet (unconfirmed or unknown)"
        )
    if receipt.get("status") != "0x1":
        raise PaymentRailError(
            "transaction did not succeed on-chain", code="tx_failed"
        )
    transfers = receipts_svc._usdc_transfers(receipt)
    to_payto = [
        t for t in transfers if (t.get("to") or "").lower() == pay_to.lower()
    ]
    if not to_payto:
        raise PaymentRailError(
            "no USDC transfer to the fleet payTo wallet in this transaction",
            code="wrong_recipient",
        )
    from_buyer = [
        t for t in to_payto if (t.get("from") or "").lower() == buyer_wallet.lower()
    ]
    if not from_buyer:
        raise PaymentRailError(
            "the USDC transfer to payTo was not sent by buyer_wallet",
            code="wrong_sender",
        )
    for transfer in from_buyer:
        if transfer["amount_units"] == amount_units:
            return transfer
    raise PaymentRailError(
        f"USDC transfer amount must be exactly {amount_units} units "
        f"($5.00); got {from_buyer[0]['amount_units']}",
        code="wrong_amount",
    )
