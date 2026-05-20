"""
Payment API
===========
Endpoints for real crypto payment processing with on-chain transaction verification.
Supports USDT/USDC/ETH on Base, Arbitrum, and Ethereum.

Recipient addresses are loaded from runtime config.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from core.paths import config_path, pending_payments_path
from core.config_merge import load_merged_config

from fastapi import APIRouter, Header, HTTPException, Query
from web3 import Web3
from web.backend.schemas.api_requests import ConfirmPaymentRequest, CreatePaymentRequest
from web3.exceptions import TransactionNotFound
from web.backend.services.commerce import CommerceService, TxHashAlreadyUsedError
from web.backend.services.storefront_pricing import checkout_usdt_from_sales_file

logger = logging.getLogger(__name__)

# Fallback when product has no usable price in sales_config (align with storefront default landing SKU).
DEFAULT_CHECKOUT_AMOUNT_USDT = 4.99

router = APIRouter(prefix="/api/payment", tags=["payment"])

# ── Wallet addresses (merged platform config; see docs/configuration.md) ──
_CONFIG_CACHE: dict | None = None
_CONFIG_PATH = config_path()

RECIPIENT_ADDRESS_EVM = "0x0000000000000000000000000000000000000000"
RECIPIENT_ADDRESS_SOLANA = "11111111111111111111111111111111"


def _load_crypto_config() -> dict:
    """Load crypto payment settings from merged YAML (with fallback to defaults)."""
    global _CONFIG_CACHE
    try:
        cfg = load_merged_config(_CONFIG_PATH)
        crypto = cfg.get("crypto", {})
        if isinstance(crypto, dict):
            _CONFIG_CACHE = crypto
            return crypto
        return _CONFIG_CACHE or {}
    except Exception:
        return _CONFIG_CACHE or {}


def _reload_addresses_from_config():
    """Reload wallet addresses from config.yaml into module-level constants."""
    global RECIPIENT_ADDRESS_EVM, RECIPIENT_ADDRESS_SOLANA
    crypto = _load_crypto_config()
    wallets = crypto.get("wallet_addresses", {})
    if wallets.get("evm"):
        RECIPIENT_ADDRESS_EVM = wallets["evm"]
    if wallets.get("solana"):
        RECIPIENT_ADDRESS_SOLANA = wallets["solana"]
    logger.info(
        f"Wallet addresses loaded from config: evm={RECIPIENT_ADDRESS_EVM}, "
        f"solana={RECIPIENT_ADDRESS_SOLANA[:8]}..."
    )


# Load addresses on module import
_reload_addresses_from_config()

# ── Payment tracking (memory + disk so metrics / restarts see pending state) ─
PENDING_PAYMENTS_FILE = pending_payments_path()
_pending_payments: dict[str, dict] = {}
commerce = CommerceService()


def _persist_pending_payments() -> None:
    PENDING_PAYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_PAYMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(_pending_payments, f, indent=2)


def _load_pending_payments_from_disk() -> None:
    """Hydrate pending map after API restart; drop expired pending rows."""
    global _pending_payments
    if not PENDING_PAYMENTS_FILE.is_file():
        return
    try:
        with open(PENDING_PAYMENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not load pending payments file: %s", e)
        return
    if not isinstance(data, dict):
        return
    now = time.time()
    cleaned: dict[str, dict] = {}
    for pid, pay in data.items():
        if not isinstance(pay, dict):
            continue
        if pay.get("status") == "pending" and float(pay.get("expires_at") or 0) <= now:
            continue
        cleaned[str(pid)] = pay
    _pending_payments = cleaned
    _persist_pending_payments()


_load_pending_payments_from_disk()

def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def payment_testnet_enabled() -> bool:
    return _env_truthy("AIFACTORY_PAYMENT_TESTNET")


def payment_verify_stub_enabled() -> bool:
    """Testnet-only stub for confirmation UX (browser/CI); never on mainnet."""
    return payment_testnet_enabled() and _env_truthy("AIFACTORY_PAYMENT_VERIFY_STUB")


# ── Public RPC endpoints for on-chain verification ──────────────────────────
RPC_ENDPOINTS = {
    "base": "https://mainnet.base.org",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "ethereum": "https://cloudflare-eth.com",
    "solana": "https://api.mainnet-beta.solana.com",
}

if payment_testnet_enabled():
    RPC_ENDPOINTS = {
        "base": os.environ.get("AIFACTORY_PAYMENT_RPC_BASE", "https://sepolia.base.org"),
        "arbitrum": os.environ.get(
            "AIFACTORY_PAYMENT_RPC_ARBITRUM", "https://sepolia-rollup.arbitrum.io/rpc"
        ),
        "ethereum": os.environ.get("AIFACTORY_PAYMENT_RPC_ETHEREUM", "https://rpc.sepolia.org"),
        "solana": os.environ.get(
            "AIFACTORY_PAYMENT_RPC_SOLANA", "https://api.devnet.solana.com"
        ),
    }

# ── ERC20 token contract addresses per chain ────────────────────────────────
TOKEN_ADDRESSES = {
    "base": {
        "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
    "arbitrum": {
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    },
}
if payment_testnet_enabled():
    TOKEN_ADDRESSES = {
        "base": {
            "USDC": "0x036CbD53842c6846639782599ee2Ba9d052Ce55f",
        },
        "arbitrum": {
            "USDC": "0x75faf114eafb1BDbe2F0316DF893FD858CE0AA96",
        },
    }

# ── Supported chains ────────────────────────────────────────────────────────
SUPPORTED_CHAINS = [
    {"id": "base", "name": "Base", "icon": "🔵", "tokens": ["USDT", "USDC"]},
    {"id": "arbitrum", "name": "Arbitrum", "icon": "🔴", "tokens": ["USDT", "USDC"]},
    {"id": "ethereum", "name": "Ethereum", "icon": "💎", "tokens": ["ETH", "USDT", "USDC"]},
    {"id": "solana", "name": "Solana", "icon": "🟣", "tokens": ["USDC", "SOL"]},
]
if payment_testnet_enabled():
    SUPPORTED_CHAINS = [
        {"id": "base", "name": "Base Sepolia", "icon": "🔵", "tokens": ["ETH", "USDC"]},
        {"id": "arbitrum", "name": "Arbitrum Sepolia", "icon": "🔴", "tokens": ["ETH", "USDC"]},
        {"id": "ethereum", "name": "Sepolia", "icon": "💎", "tokens": ["ETH", "USDC"]},
        {"id": "solana", "name": "Solana Devnet", "icon": "🟣", "tokens": ["USDC", "SOL"]},
    ]

MIN_CONFIRMATIONS = max(
    1,
    int(os.environ.get("AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "2") or "2"),
)

# Mainnet USDC mint (SPL) — used when checkout currency is USDC on Solana.
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Allow tiny float/rounding slack (0.1%) on token amounts.
_AMOUNT_TOLERANCE_RATIO = 0.001

# ── Token decimals (6 for USDC everywhere; USDT: 18 on Base, 6 on Arbitrum) ─
TOKEN_DECIMALS = {
    ("base", "USDT"): 18,
    ("base", "USDC"): 6,
    ("arbitrum", "USDT"): 6,
    ("arbitrum", "USDC"): 6,
    ("ethereum", "USDT"): 6,
    ("ethereum", "USDC"): 6,
}

# ERC20 Transfer event signature: keccak256("Transfer(address,address,uint256)")
TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()


# ═════════════════════════════════════════════════════════════════════════════
# On-chain verification helpers
# ═════════════════════════════════════════════════════════════════════════════

def _get_address_for_chain(chain: str) -> str:
    """Return the fixed recipient address for the given chain."""
    if chain == "solana":
        return RECIPIENT_ADDRESS_SOLANA
    return RECIPIENT_ADDRESS_EVM


def _minimum_paid_amount(expected_amount: float) -> float:
    if expected_amount <= 0:
        return 0.0
    return expected_amount * (1.0 - _AMOUNT_TOLERANCE_RATIO)


def _confirmations_sufficient(confirmations: int) -> bool:
    return int(confirmations) >= MIN_CONFIRMATIONS


def _stub_verify_result(confirmations: int) -> dict:
    """Synthetic on-chain result for testnet checkout drills (AIFACTORY_PAYMENT_VERIFY_STUB)."""
    conf = max(0, int(confirmations))
    if _confirmations_sufficient(conf):
        return {
            "verified": True,
            "confirmations": conf,
            "from": "0x" + "a" * 40,
            "block_number": 1000 + conf,
        }
    if conf > 0:
        return {
            "verified": False,
            "pending": True,
            "confirmations": conf,
            "error": f"Awaiting confirmations ({conf}/{MIN_CONFIRMATIONS})",
        }
    return {"verified": False, "error": "Transaction not found on chain"}


def _get_web3(chain: str) -> Web3:
    """Get a Web3 instance connected to the given chain's public RPC."""
    rpc = RPC_ENDPOINTS.get(chain)
    if not rpc:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    return Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))


def _verify_evm_transaction(
    chain: str,
    tx_hash: str,
    expected_recipient: str,
    expected_amount: float,
    expected_token: str,
) -> dict:
    """
    Verify an EVM transaction on-chain by querying the public RPC.

    Checks performed:
    1. Transaction exists and has a receipt
    2. Receipt status == 1 (success)
    3. For native ETH: ``tx.to`` matches recipient and ``tx.value >= amount``
    4. For ERC20 tokens: logs contain a Transfer event where ``to`` matches
       the recipient and the transferred value >= expected amount
    5. Confirmations must be >= MIN_CONFIRMATIONS before settlement
    """
    w3 = _get_web3(chain)

    # ── Fetch transaction & receipt ──────────────────────────────────────
    try:
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        return {"verified": False, "error": "Transaction not found on chain"}
    except Exception as exc:
        return {"verified": False, "error": f"Failed to query blockchain: {exc}"}

    # ── Receipt status ───────────────────────────────────────────────────
    if receipt.get("status") != 1:
        return {"verified": False, "error": "Transaction failed (receipt status != 1)"}

    # ── Confirmations ────────────────────────────────────────────────────
    current_block = w3.eth.block_number
    confirmations = current_block - receipt.get("blockNumber", current_block)
    if confirmations < 0:
        confirmations = 0

    recipient_checksum = Web3.to_checksum_address(expected_recipient)

    # ── Native ETH transfer ──────────────────────────────────────────────
    if expected_token == "ETH":
        tx_to = tx.get("to")
        if not tx_to:
            return {"verified": False, "error": "Contract creation transactions are not accepted"}

        try:
            tx_to_checksum = Web3.to_checksum_address(tx_to)
        except Exception:
            return {"verified": False, "error": f"Invalid 'to' address in transaction: {tx_to}"}

        if tx_to_checksum != recipient_checksum:
            return {
                "verified": False,
                "error": f"Transaction recipient mismatch. Expected {recipient_checksum}, got {tx_to}",
            }

        value_eth = float(w3.from_wei(tx.get("value", 0), "ether"))
        min_amount = _minimum_paid_amount(expected_amount)
        if value_eth < min_amount:
            return {
                "verified": False,
                "error": f"Insufficient amount. Expected ≥{expected_amount} ETH, got {value_eth} ETH",
            }

        if not _confirmations_sufficient(confirmations):
            return {
                "verified": False,
                "pending": True,
                "confirmations": confirmations,
                "error": f"Awaiting confirmations ({confirmations}/{MIN_CONFIRMATIONS})",
            }

        return {
            "verified": True,
            "confirmations": confirmations,
            "from": tx.get("from"),
            "to": tx_to,
            "amount": value_eth,
            "block_number": receipt.get("blockNumber"),
        }

    # ── ERC20 token transfer (USDT / USDC) ───────────────────────────────
    token_addresses = TOKEN_ADDRESSES.get(chain, {})
    token_addr = token_addresses.get(expected_token)
    if not token_addr:
        return {"verified": False, "error": f"Token {expected_token} is not supported on {chain}"}

    token_addr_checksum = Web3.to_checksum_address(token_addr)
    decimals = TOKEN_DECIMALS.get((chain, expected_token), 6)

    for log in receipt.get("logs", []):
        log_addr = log.get("address")
        if not log_addr:
            continue

        try:
            log_addr_checksum = Web3.to_checksum_address(log_addr)
        except Exception:
            continue

        if log_addr_checksum != token_addr_checksum:
            continue

        topics = log.get("topics", [])
        if len(topics) < 3:
            continue

        if topics[0].hex() != TRANSFER_EVENT_SIG:
            continue

        try:
            # topics[1] = from, topics[2] = to (both padded to 32 bytes)
            from_addr = Web3.to_checksum_address("0x" + topics[1].hex()[-40:])
            to_addr = Web3.to_checksum_address("0x" + topics[2].hex()[-40:])

            if to_addr != recipient_checksum:
                continue

            # Decode value from log data
            data_hex = log.get("data", "0x0")
            if data_hex.startswith("0x"):
                data_hex = data_hex[2:]
            value_raw = int.from_bytes(bytes.fromhex(data_hex.zfill(64)), "big")
            value_transferred = value_raw / (10 ** decimals)

            min_amount = _minimum_paid_amount(expected_amount)
            if value_transferred < min_amount:
                continue  # Transfer exists but amount is too low

            if not _confirmations_sufficient(confirmations):
                return {
                    "verified": False,
                    "pending": True,
                    "confirmations": confirmations,
                    "error": f"Awaiting confirmations ({confirmations}/{MIN_CONFIRMATIONS})",
                }

            return {
                "verified": True,
                "confirmations": confirmations,
                "from": from_addr,
                "to": to_addr,
                "amount": value_transferred,
                "token": expected_token,
                "block_number": receipt.get("blockNumber"),
            }
        except Exception:
            continue

    return {
        "verified": False,
        "error": (
            f"No valid {expected_token} transfer to {recipient_checksum} "
            f"found in transaction logs"
        ),
    }


# ── Solana verification ──────────────────────────────────────────────────────


def _solana_confirmations(tx_data: dict) -> int:
    conf = tx_data.get("confirmations")
    if conf is not None:
        try:
            return max(0, int(conf))
        except (TypeError, ValueError):
            pass
    return 1 if tx_data.get("slot") else 0


def _solana_token_balance_delta(meta: dict, owner: str, mint: str) -> Optional[float]:
    """Net SPL token UI amount received by ``owner`` for ``mint`` in this transaction."""

    def _index(balances: list) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        for entry in balances or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("owner") != owner or entry.get("mint") != mint:
                continue
            ui = entry.get("uiTokenAmount") or {}
            try:
                out[(owner, mint)] = float(ui.get("uiAmount") or 0)
            except (TypeError, ValueError):
                out[(owner, mint)] = 0.0
        return out

    pre = _index(meta.get("preTokenBalances") or [])
    post = _index(meta.get("postTokenBalances") or [])
    key = (owner, mint)
    return post.get(key, 0.0) - pre.get(key, 0.0)


def _verify_solana_transaction(
    tx_hash: str,
    expected_recipient: str,
    expected_amount: float,
    expected_token: str = "SOL",
) -> dict:
    """
    Verify a Solana transaction on-chain (native SOL or SPL USDC).

    Never marks verified when amount is below expectation or confirmations are insufficient.
    """
    import httpx

    rpc_url = RPC_ENDPOINTS.get("solana")
    if not rpc_url:
        return {"verified": False, "error": "Solana RPC endpoint not configured"}

    token = (expected_token or "SOL").upper()
    min_amount = _minimum_paid_amount(expected_amount)

    try:
        with httpx.Client(timeout=30) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    tx_hash,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                ],
            }
            resp = client.post(rpc_url, json=payload)
            data = resp.json()

        if "result" not in data or data["result"] is None:
            return {"verified": False, "error": "Transaction not found on Solana"}

        tx_data = data["result"]
        meta = tx_data.get("meta") or {}
        if meta.get("err") is not None:
            return {"verified": False, "error": f"Transaction failed on Solana: {meta['err']}"}

        tx_obj = tx_data.get("transaction") or {}
        message = tx_obj.get("message") or {}
        account_keys = message.get("accountKeys") or []
        confirmations = _solana_confirmations(tx_data)
        slot = tx_data.get("slot", 0)
        from_addr = ""
        if account_keys:
            first = account_keys[0]
            from_addr = first.get("pubkey", "") if isinstance(first, dict) else str(first)

        if token in ("USDC", "USDT"):
            mint = SOLANA_USDC_MINT if token == "USDC" else ""
            if not mint:
                return {"verified": False, "error": f"Solana SPL verification not configured for {token}"}
            amount_received = _solana_token_balance_delta(meta, expected_recipient, mint)
            if amount_received is None or amount_received < min_amount:
                return {
                    "verified": False,
                    "error": (
                        f"Insufficient {token} transfer to {expected_recipient}. "
                        f"Expected ≥{expected_amount}, got {amount_received}"
                    ),
                }
            if not _confirmations_sufficient(confirmations):
                return {
                    "verified": False,
                    "pending": True,
                    "confirmations": confirmations,
                    "error": f"Awaiting confirmations ({confirmations}/{MIN_CONFIRMATIONS})",
                }
            return {
                "verified": True,
                "confirmations": confirmations,
                "from": from_addr,
                "to": expected_recipient,
                "amount": amount_received,
                "token": token,
                "block_number": slot,
            }

        # Native SOL
        post_balances = meta.get("postBalances") or []
        pre_balances = meta.get("preBalances") or []
        recipient_idx = -1
        for i, acct in enumerate(account_keys):
            pubkey = acct.get("pubkey", "") if isinstance(acct, dict) else str(acct)
            if pubkey == expected_recipient:
                recipient_idx = i
                break

        if recipient_idx < 0:
            return {
                "verified": False,
                "error": f"Recipient {expected_recipient} not found in transaction accounts",
            }

        if recipient_idx >= len(post_balances) or recipient_idx >= len(pre_balances):
            return {
                "verified": False,
                "error": "Could not read recipient balance change for this transaction",
            }

        amount_lamports = int(post_balances[recipient_idx]) - int(pre_balances[recipient_idx])
        if amount_lamports <= 0:
            return {
                "verified": False,
                "error": f"No SOL credited to {expected_recipient}",
            }

        amount_sol = amount_lamports / 1_000_000_000
        if amount_sol < min_amount:
            return {
                "verified": False,
                "error": (
                    f"Insufficient SOL. Expected ≥{expected_amount}, got {amount_sol} SOL"
                ),
            }

        if not _confirmations_sufficient(confirmations):
            return {
                "verified": False,
                "pending": True,
                "confirmations": confirmations,
                "error": f"Awaiting confirmations ({confirmations}/{MIN_CONFIRMATIONS})",
            }

        return {
            "verified": True,
            "confirmations": confirmations,
            "from": from_addr,
            "to": expected_recipient,
            "amount": amount_sol,
            "token": "SOL",
            "block_number": slot,
        }

    except Exception as exc:
        return {"verified": False, "error": f"Solana verification failed: {exc}"}


# ═════════════════════════════════════════════════════════════════════════════
# API endpoints
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/create")
async def create_payment(body: CreatePaymentRequest, authorization: Optional[str] = Header(default=None)):
    """Create a payment for a product.

    Returns the fixed wallet address the user must send funds to,
    along with the expected amount and token.
    """
    payment_id = f"pay-{uuid.uuid4().hex[:12]}"
    customer_id = None
    customer_email = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = commerce.decode_token(token)
        if payload:
            customer_id = payload.get("sub")
            customer_email = payload.get("email")
    if not customer_id or not customer_email:
        raise HTTPException(status_code=401, detail="Customer authentication required")

    # Load product pricing from sales config (admin override wins; see storefront_pricing).
    price = body.amount or checkout_usdt_from_sales_file(
        body.product_id, default_usdt=DEFAULT_CHECKOUT_AMOUNT_USDT
    )

    wallet_address = _get_address_for_chain(body.chain)

    ref = (body.referral_source or "").strip()[:128] or None

    payment = {
        "payment_id": payment_id,
        "product_id": body.product_id,
        "amount": price,
        "currency": body.token or ("SOL" if body.chain == "solana" else "USDT"),
        "chain": body.chain,
        "wallet_address": wallet_address,
        "status": "pending",
        "customer_id": customer_id,
        "customer_email": customer_email,
        "created_at": time.time(),
        "expires_at": time.time() + 3600,  # 1 hour
        "referral_source": ref,
    }

    _pending_payments[payment_id] = payment
    _persist_pending_payments()
    logger.info(f"Created payment {payment_id}: {price} {payment['currency']} on {body.chain}")

    return payment


@router.get("/status/{payment_id}")
async def payment_status(payment_id: str):
    """Check the current status of a payment."""
    payment = _pending_payments.get(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("/confirm/{payment_id}")
async def confirm_payment(
    payment_id: str,
    body: ConfirmPaymentRequest,
    test_confirmations: Optional[int] = Query(None, ge=0, le=128),
):
    """Confirm a payment by verifying the transaction on-chain.

    The backend queries the respective blockchain's public RPC to:
    - Fetch the transaction by hash
    - Verify the recipient address matches the fixed address
    - Verify the transferred amount meets or exceeds the expected amount
    - Verify the transaction receipt status is 1 (success)
    """
    tx_hash = body.tx_hash.strip()
    if not tx_hash:
        raise HTTPException(status_code=400, detail="Transaction hash is required")

    payment = _pending_payments.get(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment["status"] == "confirmed":
        return {
            "status": "confirmed",
            "payment_id": payment_id,
            "tx_hash": payment.get("tx_hash", tx_hash),
            "message": "Payment was already confirmed.",
        }

    chain = payment["chain"]
    token = payment["currency"]
    amount = payment["amount"]
    expected_recipient = _get_address_for_chain(chain)

    # Normalise tx hash (EVM chains use 0x prefix, Solana uses base58)
    if chain == "solana":
        tx_hash_clean = tx_hash
    else:
        tx_hash_clean = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"

    existing_order = commerce.get_order_by_tx_hash(tx_hash_clean)
    if existing_order:
        if existing_order.get("payment_id") == payment_id:
            return {
                "status": "confirmed",
                "payment_id": payment_id,
                "tx_hash": tx_hash_clean,
                "order_id": existing_order["id"],
                "license_key": existing_order["license_key"],
                "message": "Payment was already confirmed.",
            }
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Transaction hash already used for another order",
                "existing_payment_id": existing_order.get("payment_id"),
            },
        )

    if payment.get("status") == "pending_confirmation":
        if payment.get("tx_hash") and payment.get("tx_hash") != tx_hash_clean:
            raise HTTPException(
                status_code=400,
                detail="This payment is awaiting confirmations for a different transaction hash",
            )
    elif payment.get("tx_hash"):
        if payment.get("tx_hash") != tx_hash_clean:
            raise HTTPException(
                status_code=400,
                detail="Transaction hash does not match the one submitted earlier",
            )

    # ── On-chain verification ────────────────────────────────────────────
    if test_confirmations is not None and payment_verify_stub_enabled():
        result = _stub_verify_result(test_confirmations)
    elif chain == "solana":
        result = _verify_solana_transaction(
            tx_hash=tx_hash_clean,
            expected_recipient=expected_recipient,
            expected_amount=amount,
            expected_token=token,
        )
    elif chain in RPC_ENDPOINTS:
        result = _verify_evm_transaction(
            chain=chain,
            tx_hash=tx_hash_clean,
            expected_recipient=expected_recipient,
            expected_amount=amount,
            expected_token=token,
        )
    else:
        result = {
            "verified": False,
            "error": f"Chain '{chain}' does not support on-chain verification yet",
        }

    if not result.get("verified"):
        if result.get("pending"):
            payment["status"] = "pending_confirmation"
            payment["tx_hash"] = tx_hash_clean
            payment["pending_since"] = payment.get("pending_since") or time.time()
            payment["last_verification"] = {
                "confirmations": result.get("confirmations", 0),
                "required_confirmations": MIN_CONFIRMATIONS,
            }
            _pending_payments[payment_id] = payment
            _persist_pending_payments()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Payment verified but awaiting block confirmations",
                    "status": "pending_confirmation",
                    "confirmations": result.get("confirmations", 0),
                    "required_confirmations": MIN_CONFIRMATIONS,
                    "error": result.get("error"),
                },
            )
        payment["status"] = "failed"
        payment["failed_at"] = time.time()
        payment["failure_reason"] = result.get("error", "verification_failed")
        _pending_payments[payment_id] = payment
        _persist_pending_payments()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "On-chain verification failed",
                "error": result.get("error", "Unknown verification error"),
            },
        )

    # ── Mark confirmed ───────────────────────────────────────────────────
    payment["status"] = "confirmed"
    payment["tx_hash"] = tx_hash_clean
    payment["confirmed_at"] = time.time()
    payment["verification"] = {
        "confirmations": result.get("confirmations", 0),
        "from": result.get("from", ""),
        "block_number": result.get("block_number", 0),
    }

    try:
        order = commerce.create_order_and_license(
            customer_id=payment["customer_id"],
            customer_email=payment["customer_email"],
            payment_id=payment_id,
            product_id=payment["product_id"],
            amount=payment["amount"],
            currency=payment["currency"],
            tx_hash=tx_hash_clean,
            referral_source=payment.get("referral_source"),
        )
    except TxHashAlreadyUsedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Transaction hash already used for another order",
                "existing_payment_id": exc.existing_payment_id,
            },
        ) from exc

    _pending_payments.pop(payment_id, None)
    _persist_pending_payments()

    logger.info(
        f"Payment {payment_id} confirmed via on-chain: "
        f"tx={tx_hash_clean}, confirmations={result.get('confirmations', 0)}"
    )

    return {
        "status": "confirmed",
        "payment_id": payment_id,
        "tx_hash": tx_hash_clean,
        "confirmations": result.get("confirmations", 0),
        "order_id": order["id"],
        "license_key": order["license_key"],
        "message": "Payment verified on-chain! Your license is now active.",
    }


@router.get("/chains")
async def get_supported_chains():
    """Return the list of supported blockchain networks and tokens."""
    return {
        "chains": SUPPORTED_CHAINS,
        "testnet": payment_testnet_enabled(),
        "verify_stub": payment_verify_stub_enabled(),
        "min_confirmations": MIN_CONFIRMATIONS,
    }
