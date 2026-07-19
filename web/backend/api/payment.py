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

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from web.backend.services.customer_auth import require_customer
from web3 import Web3
from web.backend.schemas.api_requests import ConfirmPaymentRequest, CreatePaymentRequest
from web3.exceptions import TransactionNotFound

# Unified multi-chain network registry + health-checked RPC failover (EVM + Solana).
from aimarket_hub import chain_net
from web.backend.services.commerce import CommerceService, TxHashAlreadyUsedError
from web.backend.services.storefront_pricing import checkout_usdt_from_sales_file

logger = logging.getLogger(__name__)

# Fallback when product has no usable price in sales_config (align with storefront default landing SKU).
DEFAULT_CHECKOUT_AMOUNT_USDT = 4.99


def _catalog_checkout_usdt(product_id: str) -> float:
    """Authoritative checkout price — never trust a client-supplied amount."""
    price = checkout_usdt_from_sales_file(
        product_id, default_usdt=DEFAULT_CHECKOUT_AMOUNT_USDT
    )
    if price <= 0:
        raise HTTPException(status_code=400, detail="Product not purchasable")
    return float(price)

router = APIRouter(prefix="/api/payment", tags=["payment"])

# ── Wallet addresses (merged platform config; see docs/configuration.md) ──
_CONFIG_CACHE: dict | None = None
_CONFIG_PATH = config_path()

# No usable default: an unset recipient must FAIL at payment-creation time rather
# than silently settle to the zero address (EVM) or the system program (Solana),
# which would burn / misdirect customer funds. The empty string is the explicit
# "unconfigured" sentinel; _ensure_recipient_configured() rejects it at request time.
# (security/prod_startup_guard.py enforces the startup-time counterpart.)
RECIPIENT_ADDRESS_EVM = ""
RECIPIENT_ADDRESS_SOLANA = ""

# Addresses that are syntactically valid but are NOT real wallets — accepting any
# of these as a settlement recipient means funds are unrecoverable. The EVM zero
# address and the Solana system-program address are the canonical placeholders the
# old defaults used; reject them (and any all-zero EVM address) defensively.
_PLACEHOLDER_EVM_ADDRESSES = frozenset(
    {
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
    }
)
_PLACEHOLDER_SOLANA_ADDRESSES = frozenset(
    {
        "11111111111111111111111111111111",  # system program
    }
)


def _is_placeholder_recipient(chain: str, address: str) -> bool:
    """True when ``address`` is unset or a known burn/placeholder for ``chain``."""
    addr = (address or "").strip()
    if not addr:
        return True
    if chain == "solana":
        return addr in _PLACEHOLDER_SOLANA_ADDRESSES
    low = addr.lower()
    if low in _PLACEHOLDER_EVM_ADDRESSES:
        return True
    # Any all-zero EVM address (regardless of length quirks) is a burn address.
    return low.startswith("0x") and set(low[2:]) <= {"0"}


def _ensure_recipient_configured(chain: str, address: str) -> str:
    """Fail loudly if no real recipient is configured for ``chain``.

    Raises HTTP 503 (operator misconfiguration, not a client error) so a payment
    is never created pointing at a zero/placeholder address that would burn funds.
    """
    if _is_placeholder_recipient(chain, address):
        logger.error(
            "Refusing to create payment: recipient address for chain '%s' is unset or a "
            "placeholder (%r). Set crypto.wallet_addresses.%s in config or AIMARKET_PAYMENT_RECIPIENT.",
            chain,
            address,
            "solana" if chain == "solana" else "evm",
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Payment processing is not configured: no settlement wallet is set for "
                f"chain '{chain}'. Contact the operator."
            ),
        )
    return address


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
    """Reload wallet addresses from config (authoritative) with a shared env fallback.

    The factory's recipient is the merged config ``crypto.wallet_addresses.evm``.
    Config wins when set — we never let a possibly-stale env var silently redirect
    funds. When config is empty (its default), fall back to ``AIMARKET_PAYMENT_RECIPIENT``,
    the same env var the alien-monitor reads, so the factory and the monitor resolve
    the same recipient in env-only deployments. Divergence is logged loudly.
    """
    global RECIPIENT_ADDRESS_EVM, RECIPIENT_ADDRESS_SOLANA
    crypto = _load_crypto_config()
    wallets = crypto.get("wallet_addresses", {})
    cfg_evm = str(wallets.get("evm") or "").strip()
    env_evm = (os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "").strip()
    if cfg_evm:
        RECIPIENT_ADDRESS_EVM = cfg_evm
        if env_evm and env_evm.lower() != cfg_evm.lower():
            logger.warning(
                "Payment recipient mismatch: config crypto.wallet_addresses.evm=%s wins over "
                "AIMARKET_PAYMENT_RECIPIENT=%s (alien-monitor reads the env). Set both to the "
                "same address to keep the monitor and the factory in sync.",
                cfg_evm,
                env_evm,
            )
    elif env_evm:
        RECIPIENT_ADDRESS_EVM = env_evm
        logger.info("Payment recipient (EVM) taken from AIMARKET_PAYMENT_RECIPIENT env (config empty)")
    if wallets.get("solana"):
        RECIPIENT_ADDRESS_SOLANA = wallets["solana"]
    logger.info(
        f"Wallet addresses loaded: evm={RECIPIENT_ADDRESS_EVM}, "
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
    """Testnet-only stub for confirmation UX (browser/CI); never on mainnet.

    Fail-closed in production: even if an operator accidentally leaves
    ``AIFACTORY_PAYMENT_VERIFY_STUB=1`` (and somehow ``AIFACTORY_PAYMENT_TESTNET``)
    set, the stub is hard-disabled whenever the deployment self-identifies as
    production (``AIFACTORY_ENV``/``AIFACTORY_PROD``/``AIFACTORY_PRODUCTION``).
    Acceptance requires the explicit, non-default opt-in below (S2).
    """
    from web.backend.services.ai_market_protocol.config import _is_production_env

    if _is_production_env():
        return False
    return payment_testnet_enabled() and _env_truthy("AIFACTORY_PAYMENT_VERIFY_STUB")


# ── Multi-chain RPC: health-checked failover pools (EVM + Solana) ───────────
# URLs, chain-ids and failover live in the shared chain_net registry (default Base + our
# demo contracts; testnet variants when AIFACTORY/AIMARKET testnet is enabled). Each chain
# gets one RpcPool that prefers the highest-priority *healthy* endpoint, fails over on error,
# and returns to the preferred default once it recovers. Legacy AIFACTORY_PAYMENT_RPC_* /
# *_RPC_URL env vars are still honoured (folded in by chain_net), so existing config keeps
# working and simply gains failover.
_PAYMENT_CHAINS = ("base", "arbitrum", "ethereum", "solana")

# Per-call RPC timeout (s) — short enough to fail over briskly, not hang a checkout.
_RPC_TIMEOUT = float(os.environ.get("AIFACTORY_PAYMENT_RPC_TIMEOUT", "15") or "15")

# Kept as the supported-chain membership map + a representative URL, sourced from chain_net
# so there is a single source of truth for endpoints.
RPC_ENDPOINTS = {
    nid: chain_net.network(nid, testnet=payment_testnet_enabled()).rpc_urls[0]
    for nid in _PAYMENT_CHAINS
}

_RPC_POOLS: dict[str, chain_net.RpcPool] = {}


def _pool_for_chain(chain: str) -> Optional[chain_net.RpcPool]:
    """Cached health-checked RPC pool for a payment chain (None if unsupported/unconfigured)."""
    testnet = payment_testnet_enabled()
    key = f"{chain}:{int(testnet)}"
    pool = _RPC_POOLS.get(key)
    if pool is None:
        try:
            spec = chain_net.network(chain, testnet=testnet)
            pool = chain_net.RpcPool(spec, timeout=_RPC_TIMEOUT)
        except chain_net.ChainNetError:
            return None
        _RPC_POOLS[key] = pool
    return pool

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
# Only stablecoin settlement is offered: native ETH/SOL have no USD→native conversion.
SUPPORTED_CHAINS = [
    {"id": "base", "name": "Base", "icon": "🔵", "tokens": ["USDT", "USDC"]},
    {"id": "arbitrum", "name": "Arbitrum", "icon": "🔴", "tokens": ["USDT", "USDC"]},
    {"id": "ethereum", "name": "Ethereum", "icon": "💎", "tokens": ["USDT", "USDC"]},
    {"id": "solana", "name": "Solana", "icon": "🟣", "tokens": ["USDC"]},
]
if payment_testnet_enabled():
    SUPPORTED_CHAINS = [
        {"id": "base", "name": "Base Sepolia", "icon": "🔵", "tokens": ["USDC"]},
        {"id": "arbitrum", "name": "Arbitrum Sepolia", "icon": "🔴", "tokens": ["USDC"]},
        {"id": "ethereum", "name": "Sepolia", "icon": "💎", "tokens": ["USDC"]},
        {"id": "solana", "name": "Solana Devnet", "icon": "🟣", "tokens": ["USDC"]},
    ]

MIN_CONFIRMATIONS = max(
    1,
    int(os.environ.get("AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "2") or "2"),
)

# Mainnet USDC mint (SPL) — used when checkout currency is USDC on Solana.
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Allow tiny float/rounding slack (0.1%) on token amounts.
_AMOUNT_TOLERANCE_RATIO = 0.001

# Settlement currencies. The catalog price is denominated in USD (USDT), and there is
# NO price oracle to convert that USD amount into a native-token quantity. Stablecoins
# (USDT/USDC ≈ $1) settle 1:1 against the catalog price; native tokens (ETH/SOL) cannot
# be compared to a USD amount directly, so they are not accepted until conversion exists.
STABLECOINS = frozenset({"USDT", "USDC"})

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
    pool = _pool_for_chain(chain)
    if pool is None:
        return {"verified": False, "error": f"Unsupported chain: {chain}"}

    # ── Fetch transaction & receipt (with RPC failover) ──────────────────
    # `_fetch` raises only on transport failure (→ chain_net fails over to the next
    # endpoint); a definitive "not found" is returned as a sentinel so it is NOT retried.
    _NOT_FOUND = {"__not_found__": True}

    def _fetch(url: str):
        w3 = Web3(Web3.HTTPProvider(
            url,
            request_kwargs={"timeout": _RPC_TIMEOUT, "headers": {"User-Agent": chain_net.user_agent()}},
        ))
        try:
            tx = w3.eth.get_transaction(tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return _NOT_FOUND
        return tx, receipt, w3.eth.block_number

    try:
        fetched = pool.run(_fetch)
    except chain_net.AllEndpointsDown as exc:
        # Don't leak endpoint URLs (which may carry API keys) to the client; log server-side.
        logger.warning("EVM RPC unavailable for %s: %s", chain, exc)
        return {"verified": False, "error": "Could not reach the blockchain RPC (all endpoints unavailable)"}
    if fetched is _NOT_FOUND:
        return {"verified": False, "error": "Transaction not found on chain"}
    tx, receipt, current_block = fetched

    # ── Receipt status ───────────────────────────────────────────────────
    if receipt.get("status") != 1:
        return {"verified": False, "error": "Transaction failed (receipt status != 1)"}

    # ── Confirmations ────────────────────────────────────────────────────
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

        value_eth = float(Web3.from_wei(tx.get("value", 0), "ether"))
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
    pool = _pool_for_chain("solana")
    if pool is None:
        return {"verified": False, "error": "Solana RPC endpoint not configured"}

    token = (expected_token or "SOL").upper()
    min_amount = _minimum_paid_amount(expected_amount)

    try:
        # getTransaction over the health-checked Solana RPC pool (fails over on transport error;
        # AllEndpointsDown / RpcError fall through to the except below → fail closed).
        result = pool.call(
            "getTransaction",
            [tx_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )

        if result is None:
            return {"verified": False, "error": "Transaction not found on Solana"}

        tx_data = result
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
        # Generic client-facing message; the exception (which may carry RPC URLs) is logged only.
        logger.warning("Solana verification error: %s", exc)
        return {"verified": False, "error": "Solana verification failed (RPC error)"}


# ═════════════════════════════════════════════════════════════════════════════
# API endpoints
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/create")
async def create_payment(body: CreatePaymentRequest, authorization: Optional[str] = Header(default=None)):
    """Create a payment for a product.

    Returns the fixed wallet address the user must send funds to,
    along with the expected amount and token.
    """
    from core.crypto_config import crypto_enabled

    # Real on-chain crypto payments are an external-blockchain feature. With crypto
    # OFF (the default) we never create one — products are delivered free / via the
    # internal UNI ledger. No recipient is required when off (no false 503).
    if not crypto_enabled():
        raise HTTPException(
            status_code=503,
            detail="Crypto payments are disabled (AIFACTORY_CRYPTO_ENABLED=0). "
                   "Set it to 1 to accept on-chain payments.",
        )
    payment_id = f"pay-{uuid.uuid4().hex}"
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

    # Settlement currency must be a stablecoin: the catalog price is USD-denominated
    # and there is no oracle to convert it into a native-token (ETH/SOL) amount.
    currency = (body.token or ("USDC" if body.chain == "solana" else "USDT")).upper()
    if currency not in STABLECOINS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported settlement currency '{currency}'. "
                f"Only stablecoins are accepted: {', '.join(sorted(STABLECOINS))}."
            ),
        )

    # Authoritative catalog price — ignore any client-supplied amount.
    price = _catalog_checkout_usdt(body.product_id)

    # Fail loudly when the settlement wallet is unset / a placeholder, so we never
    # hand the customer a burn address to send funds to (F1).
    wallet_address = _ensure_recipient_configured(
        body.chain, _get_address_for_chain(body.chain)
    )

    ref = (body.referral_source or "").strip()[:128] or None

    payment = {
        "payment_id": payment_id,
        "product_id": body.product_id,
        "amount": price,
        "currency": currency,
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
async def payment_status(payment_id: str, customer: dict = Depends(require_customer)):
    """Check the current status of a payment (customer must own the payment)."""
    payment = _pending_payments.get(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    owner = str(payment.get("customer_id") or "").strip()
    caller = str(customer.get("sub") or "").strip()
    if not owner or owner != caller:
        raise HTTPException(status_code=403, detail="Payment does not belong to this customer")
    return {
        "payment_id": payment_id,
        "status": payment.get("status"),
        "product_id": payment.get("product_id"),
        "amount": payment.get("amount"),
        "currency": payment.get("currency"),
        "chain": payment.get("chain"),
        "expires_at": payment.get("expires_at"),
        "tx_hash": payment.get("tx_hash"),
        "confirmed_at": payment.get("confirmed_at"),
        "confirmations": payment.get("confirmations"),
        "order_id": payment.get("order_id"),
        "license_key": payment.get("license_key") if payment.get("status") == "confirmed" else None,
    }


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
    from core.crypto_config import crypto_enabled

    if not crypto_enabled():
        raise HTTPException(
            status_code=503,
            detail="Crypto payments are disabled (AIFACTORY_CRYPTO_ENABLED=0).",
        )
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
    # Use the price quoted to the customer at creation time — never recompute from
    # the live catalog, or a mid-flight price change would let us charge a different
    # amount than was quoted (F6). Fall back to a recompute only for legacy rows that
    # predate persisting the amount.
    amount = payment.get("amount")
    if amount is None:
        amount = _catalog_checkout_usdt(payment["product_id"])
        payment["amount"] = amount
    amount = float(amount)
    # Defense-in-depth (F6 hardening): the on-chain verification threshold must reflect
    # the authoritative catalog price, not a stored value that could have drifted (a
    # tampered pending record, or a mid-flight catalog price change). We never silently
    # charge a *different* amount than was quoted — on mismatch we reject and the customer
    # re-creates the payment at the current price. A catalog lookup error is non-fatal
    # (fall back to the quoted amount) so confirmation never breaks on a transient read.
    try:
        catalog_amount = float(_catalog_checkout_usdt(payment["product_id"]))
    except Exception:
        catalog_amount = None
    if catalog_amount is not None and abs(catalog_amount - amount) > 0.01:
        logger.warning(
            "Payment %s amount mismatch at confirm: stored %.4f vs catalog %.4f — rejecting",
            payment_id,
            amount,
            catalog_amount,
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Payment amount no longer matches the catalog price; "
                "please create a new payment at the current price."
            ),
        )
    # The recipient must be a real, configured wallet even on the verify path (F1).
    expected_recipient = _ensure_recipient_configured(chain, _get_address_for_chain(chain))

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

    from web.backend.services.uni_bridge import credit_payment_confirm

    credit_payment_confirm(
        customer_id=payment["customer_id"],
        product_id=payment["product_id"],
        usd_amount=amount,
        tx_hash=tx_hash_clean,
        chain=chain,
        token=token,
    )

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
