"""Factory Wallet — the factory's own balance in the AI marketplace.

The factory is both BUYER and SELLER:
- BUYER: purchases data, market signals, specialized LLMs from other hubs
- SELLER: lists its own products as capabilities, earns from invocations

This module tracks:
- Factory's channel balance (how much USDT it has to spend)
- Earnings from its own listed capabilities
- Spending on external data/services
- Net position (earned - spent)

Integrates with auction plugin for bid/ask and channel plugin for payment.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FactoryBalance:
    """The factory's financial position in the AI marketplace."""

    channel_id: str = ""
    balance_usd: float = 0.0
    total_earned_usd: float = 0.0
    total_spent_usd: float = 0.0
    capabilities_listed: int = 0
    capabilities_sold: int = 0
    data_purchases: int = 0
    last_settled_at: str = ""
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # Wallet configured via env — see .env.example
    wallet_address: str = ""
    chain: str = "base"
    token: str = "USDT"

    @property
    def net_position_usd(self) -> float:
        return self.total_earned_usd - self.total_spent_usd

    @property
    def is_profitable(self) -> bool:
        return self.net_position_usd > 0

    def wallet_display(self) -> str:
        return f"{self.wallet_address[:10]}...{self.wallet_address[-6:]}"


class FactoryWallet:
    """Manages the factory's balance on Base mainnet.

    Wallet: 0x029B5e4c5E326b9a9C2e8A1F09c885908EA8eb35
    Chain:  Base
    Token:  USDT
    Balance: $20.00 (pre-funded)

    Every purchase and sale flows through this wallet via the hub's
    payment channel system. The hub verifies on-chain transactions
    before crediting the channel.
    """

    def __init__(self, ledger_path: str | Path = "data/factory_wallet.json"):
        self.ledger_path = Path(ledger_path)
        self._transactions: list[dict[str, Any]] = []
        self._balance = FactoryBalance()
        self._apply_env_config()
        self._load()

    def _apply_env_config(self) -> None:
        """Apply environment variable overrides to balance config."""
        addr = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
        if addr:
            self._balance.wallet_address = addr
        chain = os.getenv("AIMARKET_PAYMENT_CHAIN", "")
        if chain:
            self._balance.chain = chain
        token = os.getenv("AIMARKET_PAYMENT_TOKEN", "")
        if token:
            self._balance.token = token
        # Seed balance from env (demo mode default: $20)
        seed = os.getenv("AIMARKET_FACTORY_SEED_USD", os.getenv("AIFACTORY_PAYMENT_TESTNET", "1") == "1" and "20" or "0")
        if seed and float(seed) > 0 and self._balance.balance_usd == 0:
            self._balance.balance_usd = float(seed)
            self._record("initial_deposit", float(seed),
                         f"Seeded ${seed} on {self._balance.chain}")

    # ── Balance management ─────────────────────────────────────

    def top_up(self, amount_usd: float, tx_hash: str, hub_url: str = "https://modelmarket.dev") -> dict[str, Any]:
        """Deposit USDT into the factory's channel.

        Caller MUST provide a real on-chain tx_hash. Previously this method
        fabricated `factory-<timestamp>` when tx_hash was empty, allowing
        free channel funding when the hub had verify_stub enabled (EXP-63).
        """
        import httpx

        if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) < 10:
            return {"success": False, "error": "tx_hash is required and must be a real on-chain hash (0x...)"}
        if not self._balance.wallet_address:
            return {"success": False, "error": "wallet_address must be set before top_up"}

        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/channel/open",
                json={
                    "deposit_usd": amount_usd,
                    "tx_hash": tx_hash,
                    "wallet": self._balance.wallet_address,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            channel = data.get("channel", {})
            self._balance.channel_id = channel.get("channel_id", "")
            self._balance.balance_usd = channel.get("balance_usd", amount_usd)
        except Exception as exc:
            logger.error("Top-up failed: %s", exc)
            return {"success": False, "error": str(exc)}

        self._record("top_up", amount_usd, f"Channel {self._balance.channel_id} tx={tx_hash[:10]}")
        self._save()
        return {"success": True, "channel_id": self._balance.channel_id, "balance_usd": self._balance.balance_usd}

    def get_balance(self) -> FactoryBalance:
        return self._balance

    # ── Spending (factory as BUYER) ─────────────────────────────

    def purchase_data(
        self,
        product_id: str,
        capability_id: str,
        query: dict[str, Any],
        price_usd: float,
        hub_url: str = "https://modelmarket.dev",
    ) -> dict[str, Any]:
        """Purchase data from a data-as-capability on the hub.

        Performs a real /invoke against the hub (EXP-64: previously this was
        purely an accounting fiction that decremented the local counter
        without doing any HTTP call).

        Returns the invocation result on success. Local balance is only
        debited if the hub call succeeds and reports a charge.
        """
        if not self._balance.channel_id:
            return {"success": False, "error": "No active channel — call top_up() first"}
        if self._balance.balance_usd < price_usd:
            return {"success": False, "error": f"Insufficient balance: ${self._balance.balance_usd:.2f} < ${price_usd:.2f}"}

        import httpx
        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/invoke",
                json={
                    "source_hub": "local",
                    "product_id": product_id,
                    "capability_id": capability_id,
                    "input": query,
                },
                headers={"X-Payment-Channel": self._balance.channel_id},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("purchase_data invoke failed: %s", exc)
            return {"success": False, "error": str(exc)}

        if not data.get("success"):
            return {"success": False, "error": data.get("error", "invocation failed"), "detail": data}

        actual_price = float(data.get("price_usd", price_usd))
        # Update local balance to reflect server-side debit
        remaining = data.get("remaining_balance")
        if remaining is not None:
            self._balance.balance_usd = float(remaining)
        else:
            self._balance.balance_usd -= actual_price
        self._balance.total_spent_usd += actual_price
        self._balance.data_purchases += 1

        self._record("purchase_data", actual_price,
                     f"{product_id}/{capability_id} → receipt={data.get('receipt', {}).get('value', '')[:16]}")
        self._save()

        return {
            "success": True,
            "capability_id": capability_id,
            "product_id": product_id,
            "spent_usd": actual_price,
            "remaining_balance_usd": self._balance.balance_usd,
            "result": data.get("result"),
            "receipt": data.get("receipt"),
        }

    # ── Earnings (factory as SELLER) ─────────────────────────────

    def record_sale(
        self,
        capability_id: str,
        price_usd: float,
        consumer_hub: str = "external",
    ) -> None:
        """Record revenue from a capability invocation.

        Called when someone invokes a factory-produced capability.
        """
        self._balance.total_earned_usd += price_usd
        self._balance.capabilities_sold += 1
        self._balance.balance_usd += price_usd  # Revenue goes back to channel

        self._record("sale", price_usd, f"{capability_id} → {consumer_hub}")
        self._save()

        logger.info("Sale: %s for $%.2f (total earned: $%.2f)",
                     capability_id, price_usd, self._balance.total_earned_usd)

    def record_listing(self, capability_id: str) -> None:
        """Record that a new capability was listed on the hub."""
        self._balance.capabilities_listed += 1
        self._record("listing", 0, f"Listed {capability_id}")
        self._save()

    # ── Settlement ──────────────────────────────────────────────

    def settle_channel(self, hub_url: str = "https://modelmarket.dev") -> dict[str, Any]:
        """Close the factory's channel and settle all transactions.

        Returns unused balance to the factory wallet.
        Passes wallet for ownership verification (EXP-65: prevents
        anonymous close from stealing factory funds).
        """
        if not self._balance.channel_id:
            return {"success": False, "error": "No active channel"}
        if not self._balance.wallet_address:
            return {"success": False, "error": "wallet_address required to close channel"}

        import httpx

        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/channel/close",
                json={
                    "channel_id": self._balance.channel_id,
                    "wallet": self._balance.wallet_address,
                },
                timeout=15,
            )
            resp.raise_for_status()
            settlement = resp.json().get("settlement", {})
            self._balance.balance_usd = settlement.get("refund_usd", 0)
            self._balance.last_settled_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        self._record("settle", 0, f"Refund: ${self._balance.balance_usd:.2f}")
        self._save()

        return {
            "success": True,
            "refund_usd": self._balance.balance_usd,
            "total_earned": self._balance.total_earned_usd,
            "total_spent": self._balance.total_spent_usd,
            "net_position": self._balance.net_position_usd,
        }

    # ── Report ──────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        """Generate a financial report for the factory."""
        return {
            "wallet": {
                "address": self._balance.wallet_address,
                "chain": self._balance.chain,
                "token": self._balance.token,
                "explorer": f"https://basescan.org/address/{self._balance.wallet_address}",
            },
            "balance_usd": round(self._balance.balance_usd, 4),
            "total_earned_usd": round(self._balance.total_earned_usd, 4),
            "total_spent_usd": round(self._balance.total_spent_usd, 4),
            "net_position_usd": round(self._balance.net_position_usd, 4),
            "is_profitable": self._balance.is_profitable,
            "capabilities_listed": self._balance.capabilities_listed,
            "capabilities_sold": self._balance.capabilities_sold,
            "data_purchases": self._balance.data_purchases,
            "channel_id": self._balance.channel_id,
            "recent_transactions": self._transactions[-10:],
        }

    # ── Internal ────────────────────────────────────────────────

    def _record(self, tx_type: str, amount_usd: float, description: str) -> None:
        self._transactions.append({
            "type": tx_type,
            "amount_usd": round(amount_usd, 4),
            "description": description,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def _save(self) -> None:
        """Atomic JSON write — write to .tmp then os.replace().

        Previous direct write_text could leave a corrupt half-written file
        if the process crashed mid-write, which _load silently swallowed
        and lost all transaction history (EXP-66).
        """
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "balance": {
                "channel_id": self._balance.channel_id,
                "balance_usd": self._balance.balance_usd,
                "total_earned_usd": self._balance.total_earned_usd,
                "total_spent_usd": self._balance.total_spent_usd,
                "capabilities_listed": self._balance.capabilities_listed,
                "capabilities_sold": self._balance.capabilities_sold,
                "data_purchases": self._balance.data_purchases,
                "wallet_address": self._balance.wallet_address,
                "chain": self._balance.chain,
                "token": self._balance.token,
                "updated_at": self._balance.updated_at,
            },
            "transactions": self._transactions[-1000:],  # Keep last 1000
        }
        tmp_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.ledger_path)

    def _load(self) -> None:
        if not self.ledger_path.exists():
            addr = self._balance.wallet_address or "NOT_CONFIGURED"
            seed = self._balance.balance_usd
            if seed > 0:
                self._record("initial_deposit", seed,
                             f"Wallet {addr[:10]}...{addr[-6:]} seeded with ${seed:.2f} on {self._balance.chain}")
                logger.info("Factory wallet initialized: %s — $%.2f %s on %s",
                            addr, seed, self._balance.token, self._balance.chain)
            else:
                logger.warning("Factory wallet: no seed amount and no AIMARKET_PAYMENT_RECIPIENT set."
                             " Set env vars to enable marketplace payments.")
            self._save()
            return
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            bal = data.get("balance", {})
            env_addr = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
            wallet_addr = self._balance.wallet_address or bal.get("wallet_address", "") or env_addr
            self._balance = FactoryBalance(
                channel_id=bal.get("channel_id", ""),
                balance_usd=bal.get("balance_usd", self._balance.balance_usd),
                total_earned_usd=bal.get("total_earned_usd", 0),
                total_spent_usd=bal.get("total_spent_usd", 0),
                capabilities_listed=bal.get("capabilities_listed", 0),
                capabilities_sold=bal.get("capabilities_sold", 0),
                data_purchases=bal.get("data_purchases", 0),
                last_settled_at=bal.get("last_settled_at", ""),
                wallet_address=wallet_addr,
                chain=bal.get("chain", self._balance.chain),
                token=bal.get("token", self._balance.token),
            )
            self._transactions = data.get("transactions", [])
        except (json.JSONDecodeError, KeyError):
            pass
