"""Non-custodial exact-amount USDC checkout for paid Memory Units.

The recipient wallet is configured through the environment. The service never holds its
private key: it watches canonical ERC-20 Transfer logs and grants access only after an exact,
finalized transfer. A small unique raw-unit suffix makes the amount the invoice identifier.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from .config import Settings
from .models import PaymentOrder
from .store import MemoryStore

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USDC_DECIMALS = 6
CANONICAL_BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
SALT_MAX = 10_000
OPEN_ORDERS = 200
MAX_OPEN_ORDERS_PER_GRANTEE = 20
SCAN_ROUNDS = 6
MIN_SCAN_SPAN = 10
ORDER_ID = re.compile(r"^pay_[0-9a-f]{32}$")
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
BLOCK_HASH = TX_HASH
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
RANGE_HINTS = (
    "block range", "blocks range", "block_range", "range is too large",
    "exceed maximum block range", "archive request", "limited to", "too many blocks",
)


class PaymentError(ValueError):
    pass


class RpcUnavailable(RuntimeError):
    pass


class RangeLimited(RpcUnavailable):
    pass


def quantity(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    raise PaymentError("invalid chain quantity")


def format_usdc(raw: int) -> str:
    whole, fraction = divmod(int(raw), 10**USDC_DECIMALS)
    return f"{whole}.{fraction:06d}"


def topic_address(address: str) -> str:
    return "0x" + address.lower().removeprefix("0x").rjust(64, "0")


def address_from_topic(topic: str) -> str:
    return "0x" + str(topic)[-40:].lower()


def iso(timestamp: int | None = None) -> str:
    moment = datetime.fromtimestamp(timestamp, timezone.utc) if timestamp is not None else datetime.now(timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


class RpcPool:
    def __init__(self, urls: tuple[str, ...], timeout: float = 12):
        if not urls:
            raise RuntimeError("at least one Base RPC URL is required")
        for candidate in urls:
            parsed = urlparse(candidate)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise RuntimeError("PAYMENT_BASE_RPC_URLS must contain HTTPS URLs without credentials")
        self.urls = urls
        self.timeout = timeout
        self.index = 0
        # Chain identity is bound per endpoint. A single global flag is unsafe: after
        # the first healthy Base RPC fails, a fallback URL could otherwise answer from
        # another EVM chain without ever receiving its own eth_chainId check.
        self._verified_base_urls: set[str] = set()

    def _post(self, url: str, payload: dict) -> dict:
        request = Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "attested-memory-pay/1.0"},
        )
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - operator-configured RPC
            result = json.loads(response.read(1_000_001))
        if not isinstance(result, dict):
            raise RpcUnavailable("RPC returned a non-object response")
        return result

    def call(self, method: str, params: list) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        errors, ranged = [], 0
        for hop in range(len(self.urls) * 2):
            url = self.urls[(self.index + hop) % len(self.urls)]
            if method != "eth_chainId" and url not in self._verified_base_urls:
                try:
                    chain_body = self._post(url, {
                        "jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": [],
                    })
                    chain_error = chain_body.get("error")
                    if chain_error:
                        raise RpcUnavailable(str(chain_error.get("message", "eth_chainId failed"))[:200])
                    actual_chain = quantity(chain_body.get("result"))
                except Exception as error:
                    errors.append(f"{url}: chain check failed: {str(error)[:100]}")
                    continue
                if actual_chain != 8453:
                    errors.append(f"{url}: chain {actual_chain}, expected Base mainnet 8453")
                    continue
                self._verified_base_urls.add(url)
            try:
                body = self._post(url, payload)
            except Exception as error:
                errors.append(f"{url}: {str(error)[:120]}")
                continue
            rpc_error = body.get("error")
            if rpc_error:
                message = str(rpc_error.get("message", ""))[:200]
                errors.append(f"{url}: {message}")
                if any(hint in message.lower() for hint in RANGE_HINTS):
                    ranged += 1
                    continue
                raise RpcUnavailable(f"{method}: {message}")
            self.index = (self.index + hop) % len(self.urls)
            return body.get("result")
        if ranged:
            raise RangeLimited(f"{method}: every RPC refused the requested block range")
        raise RpcUnavailable(f"{method}: no RPC answered ({'; '.join(errors[-2:])})")


class PaymentDesk:
    def __init__(
        self, store: MemoryStore, settings: Settings, rpc: RpcPool | None = None,
        on_settle: Callable[[PaymentOrder], None] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.rpc = rpc or RpcPool(settings.payment_rpc_urls)
        self.recipient = self._address(settings.payment_recipient, "PAYMENT_RECIPIENT", optional=True)
        self.token_address = self._address(settings.payment_token_address, "PAYMENT_USDC_ADDRESS")
        if settings.payment_chain_id != 8453:
            raise RuntimeError("direct checkout currently supports Base mainnet only (PAYMENT_CHAIN_ID=8453)")
        if settings.payment_asset.upper() != "USDC":
            raise RuntimeError("direct checkout currently supports canonical USDC only")
        if self.token_address != CANONICAL_BASE_USDC:
            raise RuntimeError("PAYMENT_USDC_ADDRESS must be canonical Circle USDC on Base mainnet")
        self.scan_span = settings.payment_log_scan_blocks
        self.on_settle = on_settle
        # Allocation and insertion must be one local critical section: the unique
        # raw-unit suffix is the invoice identity seen on-chain.
        self.order_lock = threading.RLock()

    @staticmethod
    def _address(value: str, name: str, optional: bool = False) -> str:
        candidate = value.strip().lower()
        if not candidate and optional:
            return ""
        if not ADDRESS.fullmatch(candidate) or candidate == "0x" + "0" * 40:
            raise RuntimeError(f"{name} must be a non-zero 20-byte EVM address")
        return candidate

    @property
    def enabled(self) -> bool:
        return bool(self.recipient)

    @property
    def grace_seconds(self) -> int:
        return self.settings.payment_late_grace_hours * 3600

    def rail(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled, "chain": "base", "chain_id": 8453,
            "token": "USDC", "token_address": self.token_address, "decimals": USDC_DECIMALS,
            "pay_to": self.recipient or None,
            "required_confirmations": self.settings.payment_min_confirmations,
            "order_ttl_minutes": self.settings.payment_order_ttl_minutes,
            "late_grace_hours": self.settings.payment_late_grace_hours,
            "explorer": self.settings.payment_explorer_url,
            "mode": "exact-transfer",
            "note": (
                "Send the exact quoted amount in canonical USDC on Base. Its final raw-unit "
                "suffix identifies the order; a rounded transfer cannot be matched."
            ),
        }

    def _view(self, row) -> PaymentOrder:
        amount_raw = int(row["amount_raw"])
        return PaymentOrder(
            order_id=row["order_id"], number="AM-" + row["order_id"][4:12].upper(),
            state=row["state"], settled=row["state"] == "confirmed",
            memory_id=row["memory_id"], memory_title=row["memory_title"],
            grantee_id=row["grantee_id"], price_usdc=row["price_usdc"],
            amount_usdc=row["amount_usdc"], amount_raw=row["amount_raw"],
            chain="base", chain_id=8453, token="USDC", token_address=self.token_address,
            decimals=USDC_DECIMALS, pay_to=row["recipient"],
            eip681=(
                f"ethereum:{self.token_address}@8453/transfer"
                f"?address={row['recipient']}&uint256={amount_raw}"
            ),
            created_at=row["created_at"], expires_at=iso(int(row["expires_unix"])),
            required_confirmations=self.settings.payment_min_confirmations,
            late=bool(row["late"]), tx_hash=row["tx_hash"], payer=row["payer"],
            explorer_address=f"{self.settings.payment_explorer_url}/address/{row['recipient']}",
            explorer_tx=(f"{self.settings.payment_explorer_url}/tx/{row['tx_hash']}" if row["tx_hash"] else None),
            grant_id=row["grant_id"],
        )

    def get(self, order_id: str) -> PaymentOrder:
        if not ORDER_ID.fullmatch(str(order_id or "")):
            raise PaymentError("payment order id is malformed")
        self.store.expire_payment_orders(int(time.time()))
        try:
            return self._view(self.store.payment_order(order_id))
        except KeyError as error:
            raise PaymentError("payment order not found") from error

    def create(self, memory_id: str, grantee_id: str) -> PaymentOrder:
        if not self.enabled:
            raise RuntimeError("crypto checkout is closed: PAYMENT_RECIPIENT is not configured")
        try:
            memory = self.store.get_unchecked(memory_id)
        except KeyError as error:
            raise PaymentError("memory not found") from error
        if memory.visibility != "paid" or not memory.price_usdc:
            raise PaymentError("this Memory Unit is not sold per read")
        price_raw = int(Decimal(memory.price_usdc) * (10**USDC_DECIMALS))
        if price_raw < 1:
            raise PaymentError("memory price is below one raw USDC unit")
        head = quantity(self.rpc.call("eth_blockNumber", []))
        with self.order_lock:
            now = int(time.time())
            grace_floor = now - self.grace_seconds
            if self.store.open_payment_orders_for_grantee(grantee_id, grace_floor) >= MAX_OPEN_ORDERS_PER_GRANTEE:
                raise RuntimeError("too many open payment orders for this actor")
            open_orders = self.store.claimable_payment_orders(grace_floor, OPEN_ORDERS + 1)
            if len(open_orders) >= OPEN_ORDERS:
                raise RuntimeError("payment order capacity reached; retry after an order expires")
            taken = {int(row["amount_raw"]) for row in open_orders}
            amount_raw = next(
                (price_raw + salt for salt in range(1, SALT_MAX) if price_raw + salt not in taken), None,
            )
            if amount_raw is None:
                raise RuntimeError("no free exact-amount payment slots; retry later")
            order_id = "pay_" + secrets.token_hex(16)
            self.store.insert_payment_order((
                order_id, memory.id, grantee_id, memory.price_usdc, format_usdc(amount_raw),
                str(amount_raw), self.recipient, iso(), now,
                now + self.settings.payment_order_ttl_minutes * 60, head, max(0, head - 1),
            ))
        return self.get(order_id)

    def _transfer_in(self, receipt: dict, amount_raw: int) -> tuple[str, int, str | None] | None:
        for log in receipt.get("logs", []):
            if not isinstance(log, dict) or str(log.get("address", "")).lower() != self.token_address:
                continue
            topics = log.get("topics")
            if not isinstance(topics, list) or len(topics) < 3:
                continue
            if str(topics[0]).lower() != TRANSFER_TOPIC or address_from_topic(topics[2]) != self.recipient:
                continue
            try:
                if quantity(log.get("data", "0x0")) != amount_raw:
                    continue
                return (
                    address_from_topic(topics[1]),
                    quantity(log.get("blockNumber") or receipt.get("blockNumber")),
                    str(log.get("blockHash") or receipt.get("blockHash") or "").lower() or None,
                )
            except (PaymentError, ValueError):
                continue
        return None

    def _settle(self, row, tx_hash: str, payer: str, paid_block: int, block_hash: str | None, head: int) -> PaymentOrder:
        if paid_block < int(row["created_block"]):
            raise PaymentError("that transfer predates this payment order")
        confirmations = max(0, head - paid_block + 1)
        if confirmations < self.settings.payment_min_confirmations:
            raise PaymentError(
                f"{confirmations} of {self.settings.payment_min_confirmations} confirmations so far"
            )
        block = self.rpc.call("eth_getBlockByNumber", [hex(paid_block), False])
        canonical_hash = str(block.get("hash") or "").lower() if isinstance(block, dict) else ""
        if not BLOCK_HASH.fullmatch(canonical_hash):
            raise RpcUnavailable("Base RPC did not return a canonical block hash")
        if block_hash and block_hash.lower() != canonical_hash:
            raise PaymentError("payment receipt block is no longer canonical")
        block_hash = canonical_hash
        paid_unix = quantity(block.get("timestamp")) if isinstance(block, dict) else int(time.time())
        if paid_unix > int(row["expires_unix"]) + self.grace_seconds:
            raise PaymentError("transfer landed after this order's grace window")
        if not self.store.settle_payment(
            row["order_id"], tx_hash, payer, paid_block, block_hash, iso(paid_unix), paid_unix,
            paid_unix > int(row["expires_unix"]),
        ):
            raise PaymentError("this transaction is already bound to another payment order")
        order = self.get(row["order_id"])
        if self.on_settle:
            try:
                self.on_settle(order)
            except Exception:
                pass
        return order

    def confirm(self, order_id: str, tx_hash: str) -> PaymentOrder:
        if not TX_HASH.fullmatch(str(tx_hash or "")):
            raise PaymentError("tx_hash must be a 32-byte 0x-prefixed hash")
        current = self.get(order_id)
        if current.settled:
            row = self.store.payment_order(order_id)
            stored_hash = str(row["paid_block_hash"] or "")
            if stored_hash and row["paid_block"] is not None:
                canonical = self.rpc.call("eth_getBlockByNumber", [hex(int(row["paid_block"])), False])
                live_hash = str((canonical or {}).get("hash") or "").lower()
                if live_hash and live_hash != stored_hash.lower():
                    self.store.reorg_payment(order_id)
                else:
                    return current
            else:
                return current
        row = self.store.payment_order(order_id)
        now = int(time.time())
        if row["state"] == "expired" and int(row["expires_unix"]) + self.grace_seconds < now:
            raise PaymentError("payment order expired; create a new one")
        receipt = self.rpc.call("eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            raise PaymentError("transaction is not mined yet")
        if not isinstance(receipt, dict) or quantity(receipt.get("status", "0x0")) != 1:
            raise PaymentError("transaction reverted or has an invalid receipt")
        transfer = self._transfer_in(receipt, int(row["amount_raw"]))
        if transfer is None:
            raise PaymentError("transaction does not contain this order's exact USDC transfer")
        payer, paid_block, block_hash = transfer
        head = quantity(self.rpc.call("eth_blockNumber", []))
        return self._settle(row, tx_hash.lower(), payer, paid_block, block_hash, head)

    def _revalidate_confirmed(self) -> int:
        """Revoke grants whose recorded payment block is no longer canonical."""
        revoked = 0
        for row in self.store.confirmed_payment_orders():
            try:
                block = self.rpc.call("eth_getBlockByNumber", [hex(int(row["paid_block"])), False])
                live_hash = str((block or {}).get("hash") or "").lower()
                if live_hash and live_hash != str(row["paid_block_hash"]).lower():
                    self.store.reorg_payment(row["order_id"])
                    revoked += 1
            except (RpcUnavailable, PaymentError, ValueError, KeyError):
                # A transient RPC failure must not revoke a valid grant. The next poll
                # retries; only a positive hash mismatch is evidence of a reorg.
                continue
        return revoked

    def poll_once(self) -> int:
        if not self.enabled:
            return 0
        self._revalidate_confirmed()
        now = int(time.time())
        self.store.expire_payment_orders(now)
        settled = 0
        for _ in range(SCAN_ROUNDS):
            grace_floor = now - self.grace_seconds
            rows = self.store.claimable_payment_orders(grace_floor, OPEN_ORDERS)
            if not rows:
                break
            head = quantity(self.rpc.call("eth_blockNumber", []))
            safe = head - self.settings.payment_min_confirmations + 1
            start = min(int(row["last_scanned_block"]) for row in rows) + 1
            if safe < start:
                break
            end = min(safe, start + self.scan_span - 1)
            try:
                logs = self.rpc.call("eth_getLogs", [{
                    "address": self.token_address, "fromBlock": hex(start), "toBlock": hex(end),
                    "topics": [TRANSFER_TOPIC, None, topic_address(self.recipient)],
                }])
            except RangeLimited:
                if self.scan_span > MIN_SCAN_SPAN:
                    self.scan_span = max(MIN_SCAN_SPAN, self.scan_span // 2)
                    continue
                raise
            by_amount = {int(row["amount_raw"]): row for row in rows}
            for log in logs if isinstance(logs, list) else []:
                try:
                    topics = log.get("topics")
                    if (
                        str(log.get("address", "")).lower() != self.token_address
                        or not isinstance(topics, list) or len(topics) < 3
                        or str(topics[0]).lower() != TRANSFER_TOPIC
                        or address_from_topic(topics[2]) != self.recipient
                    ):
                        continue
                    row = by_amount.get(quantity(log.get("data", "0x0")))
                    tx_hash = str(log.get("transactionHash", "")).lower()
                    paid_block = quantity(log.get("blockNumber"))
                    if row is None or not TX_HASH.fullmatch(tx_hash) or not isinstance(topics, list) or len(topics) < 2:
                        continue
                    self._settle(row, tx_hash, address_from_topic(topics[1]), paid_block,
                                 str(log.get("blockHash") or "").lower() or None, head)
                    settled += 1
                except (PaymentError, ValueError, KeyError):
                    continue
            # Persist the cursor only after every candidate in the range was
            # processed. An RPC failure while fetching a block timestamp must
            # cause a retry, not permanently skip that transfer.
            self.store.advance_payment_scan(end, grace_floor)
            if end >= safe:
                break
        return settled
