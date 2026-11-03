"""Factory Wallet — the factory's own balance in the AI marketplace.

Monetary amounts use ``Decimal`` to avoid IEEE 754 float precision loss.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    from core.decimal_json import dumps as _json_dumps
except ImportError:
    import json as _json
    from decimal import Decimal as _Decimal

    def _json_dumps(obj: Any, **kw: Any) -> str:
        def _default(o: Any) -> Any:
            if isinstance(o, _Decimal):
                return float(o)
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        kw.setdefault("default", _default)
        return _json.dumps(obj, **kw)

logger = logging.getLogger(__name__)

_PAYMENTS_DISABLED = {"success": False, "error": "payments disabled (crypto off — AIFACTORY_CRYPTO_ENABLED=0)"}


def _crypto_enabled() -> bool:
    return os.environ.get("AIFACTORY_CRYPTO_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


@dataclass
class FactoryBalance:
    """The factory's financial position in the AI marketplace."""

    channel_id: str = ""
    balance_usd: Decimal = Decimal("0")
    total_earned_usd: Decimal = Decimal("0")
    total_spent_usd: Decimal = Decimal("0")
    # Channel remainders the hub has acknowledged owing us but has NOT paid (ACCT-001).
    # A receivable, deliberately kept out of balance_usd: it is not spendable.
    refund_owed_usd: Decimal = Decimal("0")
    capabilities_listed: int = 0
    capabilities_sold: int = 0
    data_purchases: int = 0
    last_settled_at: str = ""
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    wallet_address: str = ""
    chain: str = "base"
    token: str = "USDT"

    @property
    def net_position_usd(self) -> Decimal:
        return self.total_earned_usd - self.total_spent_usd

    @property
    def is_profitable(self) -> bool:
        return self.net_position_usd > 0

    def wallet_display(self) -> str:
        return f"{self.wallet_address[:10]}...{self.wallet_address[-6:]}"


class FactoryWallet:
    """Manages the factory's balance on Base mainnet."""

    def __init__(self, ledger_path: str | Path = "data/factory_wallet.json"):
        self.ledger_path = Path(ledger_path)
        self._transactions: list[dict[str, Any]] = []
        self._balance = FactoryBalance()
        self._apply_env_config()
        self._load()

    def _apply_env_config(self) -> None:
        addr = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
        if addr:
            self._balance.wallet_address = addr
        chain = os.getenv("AIMARKET_PAYMENT_CHAIN", "")
        if chain:
            self._balance.chain = chain
        token = os.getenv("AIMARKET_PAYMENT_TOKEN", "")
        if token:
            self._balance.token = token
        seed = os.getenv("AIMARKET_FACTORY_SEED_USD", os.getenv("AIFACTORY_PAYMENT_TESTNET", "1") == "1" and "20" or "0")
        seed_d = _to_decimal(seed)
        if seed_d > 0 and self._balance.balance_usd == 0:
            self._balance.balance_usd = seed_d
            self._record("initial_deposit", seed_d,
                         f"Seeded ${seed} on {self._balance.chain}")

    # ── Balance management ─────────────────────────────────────

    def top_up(self, amount_usd: float, tx_hash: str, hub_url: str = "https://modelmarket.dev") -> dict[str, Any]:
        if not _crypto_enabled():
            return dict(_PAYMENTS_DISABLED)
        import httpx

        if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) < 10:
            return {"success": False, "error": "tx_hash is required and must be a real on-chain hash (0x...)"}
        if not self._balance.wallet_address:
            return {"success": False, "error": "wallet_address must be set before top_up"}

        amt_d = _to_decimal(amount_usd)
        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/channel/open",
                json={"deposit_usd": amount_usd, "tx_hash": tx_hash, "wallet": self._balance.wallet_address},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            channel = data.get("channel", {})
            self._balance.channel_id = channel.get("channel_id", "")
            self._balance.balance_usd = _to_decimal(channel.get("balance_usd", amount_usd))
        except Exception as exc:
            logger.error("Top-up failed: %s", exc)
            return {"success": False, "error": str(exc)}

        self._record("top_up", amt_d, f"Channel {self._balance.channel_id} tx={tx_hash[:10]}")
        self._save()
        return {"success": True, "channel_id": self._balance.channel_id, "balance_usd": float(self._balance.balance_usd)}

    def get_balance(self) -> FactoryBalance:
        return self._balance

    # ── Spending (factory as BUYER) ─────────────────────────────

    def purchase_data(
        self, product_id: str, capability_id: str, query: dict[str, Any],
        price_usd: float, hub_url: str = "https://modelmarket.dev",
    ) -> dict[str, Any]:
        if not _crypto_enabled():
            return dict(_PAYMENTS_DISABLED)
        if not self._balance.channel_id:
            return {"success": False, "error": "No active channel — call top_up() first"}
        price_d = _to_decimal(price_usd)
        if self._balance.balance_usd < price_d:
            return {"success": False, "error": f"Insufficient balance: ${self._balance.balance_usd:.2f} < ${price_d:.2f}"}

        import httpx
        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/invoke",
                json={"source_hub": "local", "product_id": product_id, "capability_id": capability_id, "input": query},
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

        actual_price = _to_decimal(data.get("price_usd", price_usd))
        remaining = data.get("remaining_balance")
        if remaining is not None:
            self._balance.balance_usd = _to_decimal(remaining)
        else:
            self._balance.balance_usd -= actual_price
        self._balance.total_spent_usd += actual_price
        self._balance.data_purchases += 1

        self._record("purchase_data", actual_price,
                     f"{product_id}/{capability_id} → receipt={data.get('receipt', {}).get('value', '')[:16]}")
        self._save()
        return {
            "success": True, "capability_id": capability_id, "product_id": product_id,
            "spent_usd": float(actual_price), "remaining_balance_usd": float(self._balance.balance_usd),
            "result": data.get("result"), "receipt": data.get("receipt"),
        }

    # ── Earnings (factory as SELLER) ─────────────────────────────

    def _ensure_decimal_fields(self) -> None:
        b = self._balance
        b.balance_usd = _to_decimal(b.balance_usd)
        b.total_earned_usd = _to_decimal(b.total_earned_usd)
        b.total_spent_usd = _to_decimal(b.total_spent_usd)
        b.refund_owed_usd = _to_decimal(b.refund_owed_usd)

    def record_sale(self, capability_id: str, price_usd: float, consumer_hub: str = "external") -> None:
        self._ensure_decimal_fields()
        price_d = _to_decimal(price_usd)
        self._balance.total_earned_usd += price_d
        self._balance.capabilities_sold += 1
        self._balance.balance_usd += price_d
        self._record("sale", price_d, f"{capability_id} → {consumer_hub}")
        self._save()
        logger.info("Sale: %s for $%.2f (total earned: $%.2f)", capability_id, price_d, self._balance.total_earned_usd)

    def record_listing(self, capability_id: str) -> None:
        self._balance.capabilities_listed += 1
        self._record("listing", Decimal("0"), f"Listed {capability_id}")
        self._save()

    # ── Settlement ──────────────────────────────────────────────

    def settle_channel(self, hub_url: str = "https://modelmarket.dev") -> dict[str, Any]:
        if not _crypto_enabled():
            return dict(_PAYMENTS_DISABLED)
        if not self._balance.channel_id:
            return {"success": False, "error": "No active channel"}
        if not self._balance.wallet_address:
            return {"success": False, "error": "wallet_address required to close channel"}

        import httpx
        try:
            resp = httpx.post(
                f"{hub_url}/ai-market/v2/channel/close",
                json={"channel_id": self._balance.channel_id, "wallet": self._balance.wallet_address},
                timeout=15,
            )
            resp.raise_for_status()
            settlement = resp.json().get("settlement", {})
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        # ACCT-001: closing a channel moves NO funds. The hub reports the unspent
        # remainder three ways — `refund_usd` (the remainder, kept for back-compat),
        # `refund_executed_usd` (what actually came back: always 0.0 there) and
        # `refund_owed_usd` (the debt it recorded). Reading `refund_usd` into
        # balance_usd booked the whole remainder as money the factory has in hand and
        # logged "Refund: $X" for a transfer nobody made. Only what was executed can
        # be spendable; the rest is a receivable until the operator pays it out.
        remainder = _to_decimal(settlement.get("refund_usd", 0))
        executed = _to_decimal(settlement.get("refund_executed_usd", 0))
        owed = _to_decimal(settlement.get("refund_owed_usd", remainder - executed))
        self._ensure_decimal_fields()
        # balance_usd is a RUNNING pool, not a mirror of the channel alone: top_up
        # seeds it from the channel, purchase_data spends it, and record_sale credits
        # every sale into it. Assigning the settlement figure straight into it wrote
        # all of those earnings to zero on the next close (the old code did the same
        # with `refund_usd`). Only the channel's own remainder leaves the pool — it is
        # closed and nothing came back — and only what the hub actually EXECUTED
        # re-enters it. Clamped at zero because the hub is authoritative about the
        # remainder and a stale local mirror must not mint a negative balance.
        drained = self._balance.balance_usd - remainder
        if drained < 0:
            logger.warning(
                "Channel %s reported a $%.2f remainder but the local pool held only "
                "$%.2f — clamping to zero (local balance was stale)",
                self._balance.channel_id, remainder, self._balance.balance_usd,
            )
            drained = Decimal("0")
        self._balance.balance_usd = drained + executed
        self._balance.refund_owed_usd += owed
        self._balance.last_settled_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # The channel is settled — keeping its id would let purchase_data try to spend
        # a closed channel.
        settled_channel_id = self._balance.channel_id
        self._balance.channel_id = ""

        self._record(
            "settle", Decimal("0"),
            f"Channel {settled_channel_id} settled — received ${executed:.2f}, "
            f"owed ${owed:.2f} (obligation recorded by hub, no funds moved)",
        )
        if owed > 0:
            logger.warning(
                "Channel %s closed owing $%.2f to %s — recorded as a receivable, "
                "not as balance (hub cannot send value)",
                settled_channel_id, owed, self._balance.wallet_address or "?",
            )
        self._save()
        return {
            "success": True,
            # Back-compat key = the remainder, exactly as the hub reports it. Read
            # refund_executed_usd / refund_owed_usd to know whether it was PAID.
            "refund_usd": float(remainder),
            "refund_executed_usd": float(executed),
            "refund_owed_usd": float(owed),
            "refund_outstanding_usd": float(self._balance.refund_owed_usd),
            "balance_usd": float(self._balance.balance_usd),
            "total_earned": float(self._balance.total_earned_usd),
            "total_spent": float(self._balance.total_spent_usd),
            "net_position": float(self._balance.net_position_usd),
        }

    # ── Report ──────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        return {
            "wallet": {"address": self._balance.wallet_address, "chain": self._balance.chain,
                       "token": self._balance.token,
                       "explorer": f"https://basescan.org/address/{self._balance.wallet_address}"},
            "balance_usd": float(round(self._balance.balance_usd, 4)),
            "total_earned_usd": float(round(self._balance.total_earned_usd, 4)),
            "total_spent_usd": float(round(self._balance.total_spent_usd, 4)),
            # Owed to us but not received — a receivable, never folded into balance.
            "refund_owed_usd": float(round(self._balance.refund_owed_usd, 4)),
            "net_position_usd": float(round(self._balance.net_position_usd, 4)),
            "is_profitable": self._balance.is_profitable,
            "capabilities_listed": self._balance.capabilities_listed,
            "capabilities_sold": self._balance.capabilities_sold,
            "data_purchases": self._balance.data_purchases,
            "channel_id": self._balance.channel_id,
            "recent_transactions": self._transactions[-10:],
        }

    # ── Internal ────────────────────────────────────────────────

    def _record(self, tx_type: str, amount_usd: Decimal, description: str) -> None:
        self._transactions.append({
            "type": tx_type,
            "amount_usd": float(round(amount_usd, 4)),
            "description": description,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def _save(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "balance": {
                "channel_id": self._balance.channel_id,
                "balance_usd": float(self._balance.balance_usd),
                "total_earned_usd": float(self._balance.total_earned_usd),
                "total_spent_usd": float(self._balance.total_spent_usd),
                "refund_owed_usd": float(self._balance.refund_owed_usd),
                "last_settled_at": self._balance.last_settled_at,
                "capabilities_listed": self._balance.capabilities_listed,
                "capabilities_sold": self._balance.capabilities_sold,
                "data_purchases": self._balance.data_purchases,
                "wallet_address": self._balance.wallet_address,
                "chain": self._balance.chain, "token": self._balance.token,
                "updated_at": self._balance.updated_at,
            },
            "transactions": self._transactions[-1000:],
        }
        tmp_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".tmp")
        tmp_path.write_text(_json_dumps(data, indent=2), encoding="utf-8")
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
                logger.warning("Factory wallet: no seed amount and no AIMARKET_PAYMENT_RECIPIENT set.")
            self._save()
            return
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            bal = data.get("balance", {})
            env_addr = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
            wallet_addr = self._balance.wallet_address or bal.get("wallet_address", "") or env_addr
            self._balance = FactoryBalance(
                channel_id=bal.get("channel_id", ""),
                balance_usd=_to_decimal(bal.get("balance_usd", 0)),
                total_earned_usd=_to_decimal(bal.get("total_earned_usd", 0)),
                total_spent_usd=_to_decimal(bal.get("total_spent_usd", 0)),
                refund_owed_usd=_to_decimal(bal.get("refund_owed_usd", 0)),
                capabilities_listed=bal.get("capabilities_listed", 0),
                capabilities_sold=bal.get("capabilities_sold", 0),
                data_purchases=bal.get("data_purchases", 0),
                last_settled_at=bal.get("last_settled_at", ""),
                wallet_address=wallet_addr,
                chain=bal.get("chain", "base"), token=bal.get("token", "USDT"),
            )
            self._transactions = data.get("transactions", [])
        except (json.JSONDecodeError, KeyError):
            pass
