"""USDC that lands in the hub's top-up wallet is credited without anybody presenting it.

Until 2026-10-04 a top-up became credit only when somebody POSTed ``/topups/{nonce}`` with the
transaction hash, and a plain transfer — what a person sends from an ordinary wallet app — could
only be credited by the operator by hand (``/accounts/{id}/credit`` with ``tx_hash``). The first
company-to-company payment (Independent AI prepaying its account at Attested Memory) needed exactly
that hand step, and somebody watching the chain to know it had arrived.

Now the hub watches its own top-up wallet, every ``AIMARKET_DEPOSIT_WATCH_INTERVAL_S``:

* a transfer whose transaction carries an ``AuthorizationUsed`` for an open top-up quote is
  redeemed exactly as ``POST /topups/{nonce}`` would — nobody has to present it;
* a plain transfer from a wallet LINKED to an account is credited to that account as paid credit
  (``POST /account/payer-wallets``: the account proves it controls the wallet with a signature, or
  the operator links it);
* anything else is recorded as an unattributed deposit, listed for the operator
  (``GET /admin/deposits``), counted in the well-known (so an alerter can page) and credited the
  moment its sender is linked.

Only a wallet that receives top-ups and NOTHING ELSE can be watched this way
(``AIMARKET_TOPUP_PAY_TO``). The hub's x402 wallet also receives sales, and its payment-recipient
wallet channel deposits; reading every incoming transfer as a top-up would credit those twice. So
the watcher refuses to run on either.

Every credit goes through the deposit registry every door shares (``channels.claim_deposit_as``)
and the ledger's idempotent reference ``chain:<chain>:<tx>`` — the same reference the operator's
hand credit uses — so a transaction becomes credit once, whichever door sees it first.

**No transfer holds up the others** (independent review, 2026-10-04). Every transfer seen is
recorded on its own row and the cursor moves on: one that cannot be decided yet (a quote over its
account's daily limit, a node that has no receipt yet, a registry that did not answer) is
``pending`` and retried from that row on later scans; one nobody can claim is ``unattributed``
and re-examined — a link, the operator's hand credit or a quote presented by hand settles it. Only
a node that cannot be read at all stops a scan, and then the same blocks are read again.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any, Callable

from aimarket_hub import settle, topup, x402

logger = logging.getLogger(__name__)

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
#: USDC's ``AuthorizationUsed(address indexed authorizer, bytes32 indexed nonce)``.
AUTHORIZATION_USED_TOPIC = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
DEPOSIT_STACK = "aimarket-hub-deposit-watch"
LINK_VERSION = "aimarket-payer-wallet/1"
LINK_MAX_AGE_S = 600

CREDITED, UNATTRIBUTED, ELSEWHERE = "credited", "unattributed", "credited_elsewhere"
#: Not decided yet (a daily limit, a node without the receipt, a registry that did not answer):
#: retried automatically. Below a millicent: nothing to credit. Settled by the operator out of band.
PENDING, IGNORED, RESOLVED = "pending", "ignored", "resolved"
#: Statuses no later scan may change.
FINAL = (CREDITED, ELSEWHERE, IGNORED, RESOLVED)
#: Blocks re-read behind the cursor on every scan. A public node behind a load balancer can
#: answer eth_blockNumber from one backend and eth_getLogs from another a block or two behind;
#: re-reading is free, because every decision is idempotent.
OVERLAP_BLOCKS = 12
#: Open deposits (pending, unattributed) re-examined per scan, least recently looked at first.
REVISIT_BATCH = 25
SEVERAL_SENDERS = "several senders in one transaction"
QUOTE_REFUSED = "quote refused"


# ── configuration ────────────────────────────────────────────────────────────


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def dedicated_wallet() -> str:
    """The top-up wallet, only when it is set explicitly — never the x402 fallback."""
    raw = (os.getenv("AIMARKET_TOPUP_PAY_TO") or "").strip()
    return raw.lower() if settle.is_address(raw) else ""


def _other_payee_wallets() -> set[str]:
    """Wallets the hub names for OTHER money: x402 sales (AIMARKET_X402_PAY_TO, falling back to
    AIMARKET_PAYMENT_RECIPIENT — x402.recipient()) and channel deposits (AIMARKET_PAYMENT_RECIPIENT)."""
    names = (os.getenv("AIMARKET_X402_PAY_TO"), os.getenv("AIMARKET_PAYMENT_RECIPIENT"), x402.recipient())
    return {str(n).strip().lower() for n in names if n and str(n).strip()}


def switched_on() -> bool:
    return os.getenv("AIMARKET_DEPOSIT_WATCH", "1").strip().lower() not in ("0", "false", "no", "off")


def interval_s() -> int:
    return max(15, _int("AIMARKET_DEPOSIT_WATCH_INTERVAL_S", 60))


def chunk_blocks() -> int:
    # Public Base RPCs refuse eth_getLogs over ~2000 blocks.
    return min(2000, max(10, _int("AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS", 500)))


def lookback_blocks() -> int:
    """Where a first scan starts: this many blocks behind the head (~1 h on Base)."""
    return max(0, _int("AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS", 1800))


#: A scan with more windows than this ahead of it is catching up, and rests between them.
CATCH_UP_CHUNKS = 4


def catch_up_pause_s() -> float:
    """Rest between log windows while a scan catches up. Free nodes cap requests per IP per
    second, and one refusal ends the scan until the next interval: on 2026-10-21 the Independent
    node, 13 days behind, read ~10 windows a minute back to back; paced at ~3 a second, the same
    node served 1138 in a row."""
    try:
        return min(5.0, max(0.0, float(os.getenv("AIMARKET_DEPOSIT_WATCH_PAUSE_S", "0.3"))))
    except ValueError:
        return 0.3


def _rest(seconds: float) -> None:
    time.sleep(seconds)


def unavailable_reason() -> str:
    reason = topup.unavailable_reason()
    if reason:
        return reason
    if not switched_on():
        return "the deposit watcher is switched off (AIMARKET_DEPOSIT_WATCH=0)"
    if not dedicated_wallet():
        return ("plain transfers are not watched: set AIMARKET_TOPUP_PAY_TO to a wallet that receives "
                "top-ups and nothing else")
    if dedicated_wallet() in _other_payee_wallets():
        return ("plain transfers are not watched: AIMARKET_TOPUP_PAY_TO is also the hub's sales or "
                "channel-deposit wallet (AIMARKET_X402_PAY_TO / AIMARKET_PAYMENT_RECIPIENT), which "
                "receives other money — give top-ups a wallet of their own")
    if not settle.rpc_urls(x402.chain_id()):
        return "this hub has no RPC for its chain"
    return ""


def enabled() -> bool:
    return not unavailable_reason()


def link_message(*, hub_url: str, account_id: str, address: str, issued_at: int) -> str:
    """What a wallet signs (EIP-191 personal_sign) to say its transfers are this account's."""
    return "\n".join((
        LINK_VERSION,
        f"hub: {(hub_url or '').rstrip('/')}",
        f"account: {account_id}",
        f"address: {address.lower()}",
        f"issued_at: {int(issued_at)}",
    ))


def signature_links_available() -> bool:
    """Can this hub recover a wallet signature? (eth-account, the hub's ``escrow`` extra)"""
    import importlib.util

    return importlib.util.find_spec("eth_account") is not None


def signer_of(message: str, signature: str) -> str:
    """The address that signed ``message`` (EIP-191), lower case, or "" when it does not recover."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        return Account.recover_message(encode_defunct(text=message), signature=signature).lower()
    except Exception:  # noqa: BLE001 - a malformed signature is simply not a signature
        return ""


# ── storage ──────────────────────────────────────────────────────────────────


class DepositStore:
    """``payer_wallets``, ``deposit_watch_cursor``, ``hub_deposits`` (migration 050)."""

    def __init__(self, conn: Any):
        self._conn = conn

    def cursor(self, key: str) -> int | None:
        row = self._conn.execute(
            "SELECT next_block FROM deposit_watch_cursor WHERE key = ?", (key,)).fetchone()
        return int(row["next_block"]) if row else None

    def set_cursor(self, key: str, next_block: int) -> None:
        # An upsert, not UPDATE-then-INSERT: rowcount is not reliable on the shared connection.
        self._conn.execute(
            "INSERT INTO deposit_watch_cursor (key, next_block, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET next_block = excluded.next_block, updated_at = excluded.updated_at",
            (key, int(next_block), time.time()))
        self._conn.commit()

    def link(self, address: str, account_id: str, linked_by: str) -> str:
        """"linked", "already" (to this account) or "taken" (by another account)."""
        address = address.lower()
        owner = self.account_for(address)
        if owner == account_id:
            return "already"
        if owner:
            return "taken"
        # ON CONFLICT DO NOTHING, never a caught IntegrityError: rolling back a failed statement on
        # the shared SQLite connection reverts another thread's uncommitted row (db_backend.py).
        self._conn.execute(
            "INSERT INTO payer_wallets (address, account_id, linked_by, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(address) DO NOTHING", (address, account_id, linked_by, time.time()))
        self._conn.commit()
        return "linked" if self.account_for(address) == account_id else "taken"

    def unlink(self, address: str, account_id: str) -> bool:
        owned = self.account_for(address) == account_id        # rowcount lies on the shared connection
        self._conn.execute(
            "DELETE FROM payer_wallets WHERE address = ? AND account_id = ?", (address.lower(), account_id))
        self._conn.commit()
        return owned

    def account_for(self, address: str) -> str:
        row = self._conn.execute(
            "SELECT account_id FROM payer_wallets WHERE address = ?", ((address or "").lower(),)).fetchone()
        return str(row["account_id"]) if row else ""

    def wallets(self, account_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT address, linked_by, created_at FROM payer_wallets WHERE account_id = ? ORDER BY created_at",
            (account_id,)).fetchall()
        return [dict(r) for r in rows]

    def deposit(self, tx_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM hub_deposits WHERE tx_hash = ?", (tx_hash,)).fetchone()
        return dict(row) if row else None

    def record(self, *, tx_hash: str, sender: str, amount_units: int, block: int, status: str,
               account_id: str = "", detail: str = "") -> None:
        # A final status is never overwritten: a scan that read the wallet as unlinked must not
        # turn a deposit the link endpoint credited meanwhile back into "unattributed".
        now = time.time()
        self._conn.execute(
            "INSERT INTO hub_deposits (tx_hash, sender, amount_units, block, status, account_id, detail, "
            "seen_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(tx_hash) DO UPDATE SET "
            "status = excluded.status, account_id = excluded.account_id, detail = excluded.detail, "
            "updated_at = excluded.updated_at WHERE hub_deposits.status NOT IN (?, ?, ?, ?)",
            (tx_hash, sender.lower(), int(amount_units), int(block), status, account_id, detail[:300], now, now,
             *FINAL))
        self._conn.commit()

    def open_rows(self, limit: int = REVISIT_BATCH) -> list[dict[str, Any]]:
        """Pending and unattributed deposits, least recently looked at first."""
        rows = self._conn.execute(
            f"SELECT * FROM hub_deposits WHERE status IN (?, ?) ORDER BY updated_at LIMIT {int(limit)}",
            (PENDING, UNATTRIBUTED)).fetchall()
        return [dict(r) for r in rows]

    def count_status(self, status: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM hub_deposits WHERE status = ?", (status,)).fetchone()
        return int((row["n"] if row else 0) or 0)

    def resolve(self, tx_hash: str, note: str) -> bool:
        """The operator settled an open deposit out of band (a refund, a credit elsewhere)."""
        row = self.deposit(tx_hash)
        if row is None or row["status"] not in (PENDING, UNATTRIBUTED):
            return False
        self._conn.execute(
            "UPDATE hub_deposits SET status = ?, detail = ?, updated_at = ? WHERE tx_hash = ? AND status IN (?, ?)",
            (RESOLVED, f"resolved by the operator: {note}"[:300], time.time(), tx_hash, PENDING, UNATTRIBUTED))
        self._conn.commit()
        return (self.deposit(tx_hash) or {}).get("status") == RESOLVED

    def last_scan_at(self, key: str) -> float | None:
        row = self._conn.execute(
            "SELECT updated_at FROM deposit_watch_cursor WHERE key = ?", (key,)).fetchone()
        return float(row["updated_at"]) if row else None

    def unattributed(self, sender: str = "", limit: int = 100) -> list[dict[str, Any]]:
        if sender:
            rows = self._conn.execute(
                "SELECT * FROM hub_deposits WHERE status = ? AND sender = ? ORDER BY block",
                (UNATTRIBUTED, sender.lower())).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM hub_deposits WHERE status = ? ORDER BY block DESC LIMIT {int(limit)}",
                (UNATTRIBUTED,)).fetchall()
        return [dict(r) for r in rows]

    def count_unattributed(self) -> int:
        return self.count_status(UNATTRIBUTED)


# ── one transfer ─────────────────────────────────────────────────────────────


class Retry(Exception):
    """A transient failure. Raised for ONE transfer, it leaves that transfer pending and the scan
    moves on; raised while reading the chain itself (head, logs), it stops the scan and the same
    blocks are read again next time."""


def credit_plain(*, store: DepositStore, ledger: Any, claim_deposit: Callable[..., dict[str, Any]],
                 release_deposit: Callable[..., None], tx_hash: str, account_id: str, amount_units: int,
                 sender: str, block: int, chain: str, chain_id: int | None, decimals: int) -> str:
    """Credit a plain transfer from a linked wallet. Same reference as the operator's hand credit."""
    credited_mc = topup.units_to_mc(amount_units, decimals)
    if credited_mc <= 0:
        store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                     status=IGNORED, detail="less than a millicent: nothing to credit")
        return IGNORED
    claim = claim_deposit(stack=DEPOSIT_STACK, chain=chain, tx_hash=tx_hash, claim_id=account_id,
                          amount_cents=amount_units * 100 // 10 ** decimals, chain_id=chain_id)
    held = claim.get("claim") or {}
    ours = held.get("stack") == DEPOSIT_STACK and held.get("claim_id") == account_id
    if not claim.get("ok") and not ours:
        if claim.get("error") == "already_claimed":
            # Another door had it first (the operator by hand, a top-up redemption): it is credit
            # already, somewhere, and must not become credit twice.
            store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                         status=ELSEWHERE, detail=f"claimed by {held.get('stack') or 'another door'}")
            return ELSEWHERE
        raise Retry(f"deposit registry: {claim.get('error')}")
    result = ledger.deposit(account_id, credited_mc, reference=f"chain:{chain}:{tx_hash}",
                            note=f"plain USDC transfer from linked wallet {sender[:10]}…")
    if result.get("error"):
        if claim.get("ok"):
            release_deposit(stack=DEPOSIT_STACK, chain=chain, tx_hash=tx_hash, claim_id=account_id,
                            chain_id=chain_id)
        raise Retry(f"ledger: {result['error']}")
    store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                 status=CREDITED, account_id=account_id)
    logger.warning("deposit watch: credited $%.5f to %s (plain transfer %s from %s)",
                   credited_mc / 100_000, account_id, tx_hash[:18], sender[:12])
    return CREDITED


def _no_claim(**_: Any) -> dict[str, Any] | None:
    return None


class Watcher:
    """One hub's top-up wallet. ``scan_once`` is safe to run any number of times."""

    def __init__(self, *, store: DepositStore, ledger: Any, topups: topup.TopupStore, payments: Any,
                 claim_deposit: Callable[..., dict[str, Any]], release_deposit: Callable[..., None],
                 claim_holder: Callable[..., dict[str, Any] | None] = _no_claim,
                 rpc: Callable[[str, list[Any]], Any] | None = None):
        self.store = store
        self.ledger = ledger
        self.topups = topups
        self.payments = payments
        self.claim_deposit = claim_deposit
        self.release_deposit = release_deposit
        # Read-only: who already holds the registry claim on a transaction (channels.deposit_claim_holder).
        self.claim_holder = claim_holder
        self._rpc = rpc

    def rpc(self, method: str, params: list[Any]) -> Any:
        if self._rpc is not None:
            return self._rpc(method, params)
        # In rotation, not first-come: a scan that catches up reads hundreds of log windows, and
        # free nodes cap them per IP. The Independent node's only one (mainnet.base.org) answered
        # 429 to every eth_getLogs for 13 days (2026-10-08..21) while the scan retried it alone.
        chain_id = x402.chain_id()
        try:
            return settle.rpc_call(settle.rpc_urls(chain_id), method, params, chain_id=chain_id, timeout=15.0)
        except Exception as exc:  # noqa: BLE001 - every node refused or none is configured
            raise Retry(f"no RPC answered {method}: {exc}") from exc

    def _context(self) -> dict[str, Any]:
        profile = x402.asset_profile() or {}
        wallet = dedicated_wallet()
        return {"wallet": wallet, "wallet_topic": "0x" + wallet[2:].rjust(64, "0") if wallet else "",
                "token": str(profile.get("address") or "").lower(),
                "chain": x402.chain(), "chain_id": x402.chain_id() or None,
                "decimals": int(profile.get("decimals") or 6)}

    @staticmethod
    def _transfers_into(logs: list[dict[str, Any]], ctx: dict[str, Any]) -> list[tuple[str, int]]:
        """(sender, units) of every token Transfer into the wallet — re-checked here, not trusted
        to the node's filter: the token's address, the Transfer topic and the recipient."""
        out: list[tuple[str, int]] = []
        for log in logs or []:
            topics = [str(x).lower() for x in (log.get("topics") or [])]
            if (str(log.get("address") or "").lower() != ctx["token"] or len(topics) < 3
                    or topics[0] != TRANSFER_TOPIC or topics[2] != ctx["wallet_topic"]):
                continue
            try:
                units = int(str(log.get("data") or "0x0"), 16)
            except ValueError:
                continue
            out.append(("0x" + topics[1][-40:], units))
        return out

    def _pending(self, *, tx_hash: str, sender: str, amount_units: int, block: int, why: str) -> str:
        self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                          status=PENDING, detail=f"retried automatically: {why}")
        return PENDING

    def _elsewhere(self, *, tx_hash: str, sender: str, amount_units: int, block: int,
                   ctx: dict[str, Any]) -> str:
        """ELSEWHERE when another door already holds this transaction's claim, else ""."""
        try:
            holder = self.claim_holder(chain=ctx["chain"], tx_hash=tx_hash, chain_id=ctx["chain_id"])
        except Exception as exc:  # noqa: BLE001 - an unreadable registry decides nothing
            raise Retry(f"deposit registry unreadable: {type(exc).__name__}") from None
        if holder and holder.get("stack") != DEPOSIT_STACK:
            self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                              status=ELSEWHERE, detail=f"claimed by {holder.get('stack') or 'another door'}")
            return ELSEWHERE
        return ""

    def _redeem_quotes(self, *, tx_hash: str, logs: list[dict[str, Any]], sender: str, amount_units: int,
                       block: int, ctx: dict[str, Any]) -> str:
        """Redeem every authorization in this transaction over one of OUR top-up quotes, exactly as
        POST /topups/{nonce} would. "" when the transaction pays no quote of ours."""
        credited: list[str] = []
        pending: list[str] = []
        refused: list[str] = []
        elsewhere: list[str] = []
        account = ""
        for log in logs:
            topics = [str(x).lower() for x in (log.get("topics") or [])]
            if (str(log.get("address") or "").lower() != ctx["token"] or len(topics) < 3
                    or topics[0] != AUTHORIZATION_USED_TOPIC):
                continue
            quote = self.topups.get(topics[2])
            if quote is None or quote.pay_to.lower() != ctx["wallet"]:
                continue
            try:
                topup.redeem(store=self.topups, ledger=self.ledger, payments=self.payments,
                             nonce=quote.nonce, tx_hash=tx_hash, claim_deposit=self.claim_deposit)
            except topup.TopupError as exc:
                # `retryable` travels in the error's extras (topup.TopupError), never as an attribute:
                # reading it as one raised AttributeError on every refusal and stopped the watcher.
                if exc.extra.get("retryable"):
                    pending.append(f"{quote.nonce[:12]}: {exc.error}")
                elif exc.error == "payment_already_used":
                    elsewhere.append(quote.nonce[:12])
                else:
                    refused.append(f"{quote.nonce[:12]}: {exc.error}")
                continue
            credited.append(quote.nonce[:12])
            account = account or quote.account_id
        if not (credited or pending or refused or elsewhere):
            return ""
        detail = "; ".join(filter(None, (
            f"top-up quote(s) {', '.join(credited)}" if credited else "",
            f"waiting: {', '.join(pending)}" if pending else "",
            f"{QUOTE_REFUSED}: {', '.join(refused)}" if refused else "")))
        if pending:
            return self._pending(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                                 why=detail)
        if credited:
            self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                              status=CREDITED, account_id=account, detail=detail)
            return CREDITED
        if elsewhere and not refused:
            self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                              status=ELSEWHERE, detail="the quote payment was used at another door")
            return ELSEWHERE
        self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                          status=UNATTRIBUTED, detail=detail)
        return UNATTRIBUTED

    def _plain(self, *, tx_hash: str, sender: str, amount_units: int, block: int,
               ctx: dict[str, Any], first_sight: bool) -> str:
        """A plain transfer: credited to the linked account, or kept as unattributed."""
        settled = self._elsewhere(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                  block=block, ctx=ctx)
        if settled:
            return settled
        if topup.units_to_mc(amount_units, ctx["decimals"]) <= 0:
            self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                              status=IGNORED, detail="less than a millicent: nothing to credit")
            return IGNORED
        account_id = self.store.account_for(sender)
        if account_id:
            return credit_plain(store=self.store, ledger=self.ledger, claim_deposit=self.claim_deposit,
                                release_deposit=self.release_deposit, tx_hash=tx_hash,
                                account_id=account_id, amount_units=amount_units, sender=sender,
                                block=block, chain=ctx["chain"], chain_id=ctx["chain_id"],
                                decimals=ctx["decimals"])
        self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                          status=UNATTRIBUTED, detail="no account has linked the sending wallet")
        if first_sight:
            logger.warning("deposit watch: %s base units from %s (tx %s) match no account — listed as "
                           "unattributed", amount_units, sender[:12], tx_hash[:18])
        return UNATTRIBUTED

    def handle_receipt(self, *, tx_hash: str, receipt: dict[str, Any], block: int) -> str:
        """Decide one transaction into the wallet from its receipt: the single source of truth for
        who paid what (the logs a filter returned are only how the transaction was found)."""
        ctx = self._context()
        known = self.store.deposit(tx_hash)
        if known and known["status"] in FINAL:
            return str(known["status"])
        logs = receipt.get("logs") or []
        transfers = self._transfers_into(logs, ctx)
        if not transfers:
            return self._pending(tx_hash=tx_hash, sender=str((known or {}).get("sender") or ""),
                                 amount_units=int((known or {}).get("amount_units") or 0), block=block,
                                 why="the receipt shows no transfer into the wallet yet")
        sender, amount_units = transfers[0][0], sum(units for _, units in transfers)
        try:
            # 1. Payments over our top-up quotes.
            outcome = self._redeem_quotes(tx_hash=tx_hash, logs=logs, sender=sender,
                                          amount_units=amount_units, block=block, ctx=ctx)
            if outcome:
                return outcome
            # 2. Several payers in one transaction (a bundler, or a dust transfer placed in front of
            #    somebody else's): no account can be named for the whole, as the channel door says too.
            if len({s for s, _ in transfers}) > 1:
                settled = self._elsewhere(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                          block=block, ctx=ctx)
                if settled:
                    return settled
                self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                                  status=UNATTRIBUTED,
                                  detail=f"{SEVERAL_SENDERS}: credit it by hand with its tx_hash")
                return UNATTRIBUTED
            # 3. A plain transfer.
            return self._plain(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                               ctx=ctx, first_sight=known is None)
        except Retry as exc:
            return self._pending(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                                 why=str(exc))

    def reexamine(self, row: dict[str, Any]) -> str:
        """Look again at one open deposit. Pending: from its receipt. Unattributed: is it credit
        elsewhere now (a hand credit, a quote presented by hand), or is its sender linked now?"""
        ctx = self._context()
        tx_hash, sender = str(row["tx_hash"]), str(row["sender"] or "")
        amount_units, block = int(row["amount_units"] or 0), int(row["block"] or 0)
        if row["status"] == PENDING:
            try:
                receipt = self.rpc("eth_getTransactionReceipt", [tx_hash])
            except Retry as exc:
                return self._pending(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                     block=block, why=str(exc))
            if not receipt:
                return self._pending(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                     block=block, why="the node has no receipt yet")
            return self.handle_receipt(tx_hash=tx_hash, receipt=receipt, block=block)
        detail = str(row.get("detail") or "")
        try:
            if detail.startswith(SEVERAL_SENDERS) or QUOTE_REFUSED in detail:
                # Never credited automatically; settled only by another door or by the operator.
                settled = self._elsewhere(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                          block=block, ctx=ctx)
                if not settled:
                    self.store.record(tx_hash=tx_hash, sender=sender, amount_units=amount_units,
                                      block=block, status=UNATTRIBUTED, detail=detail)
                return settled or UNATTRIBUTED
            return self._plain(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                               ctx=ctx, first_sight=False)
        except Retry as exc:
            return self._pending(tx_hash=tx_hash, sender=sender, amount_units=amount_units, block=block,
                                 why=str(exc))

    def _decimals_refusal(self, ctx: dict[str, Any]) -> str:
        """Why no transfer may be credited now: the token's own decimals() is not the scale the
        hub converts with. The quote door refuses this case; a plain transfer is the same money
        through a second door, so it is refused here too — one 18-decimal token would otherwise
        credit 1e12 times its value."""
        try:
            topup.check_decimals(ctx["token"], ctx["decimals"])
        except topup.TopupError as exc:
            return exc.detail
        return ""

    def credit_linked(self, sender: str) -> list[str]:
        """After a wallet is linked: credit whatever it already sent."""
        refusal = self._decimals_refusal(self._context())
        if refusal:
            logger.warning("deposit watch: not crediting linked wallet — %s", refusal)
            return []
        return [self.reexamine(row) for row in self.store.unattributed(sender)]

    def revisit_open(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for row in self.store.open_rows(REVISIT_BATCH):
            out[self.reexamine(row)] += 1
        return dict(out)

    def scan_once(self) -> dict[str, Any]:
        """Re-examine open deposits, then read new Transfer logs into the wallet up to the
        confirmed head, chunk by chunk, every transfer recorded on its own row."""
        if not enabled():
            return {"scanned": False, "reason": unavailable_reason()}
        ctx = self._context()
        refusal = self._decimals_refusal(ctx)
        if refusal:
            return {"scanned": False, "reason": refusal}
        if ctx["chain_id"]:
            answered = int(str(self.rpc("eth_chainId", [])), 16)
            if answered != int(ctx["chain_id"]):
                raise Retry(f"the node answers for chain {answered}, this hub reads {ctx['chain_id']}")
        head = int(self.rpc("eth_blockNumber", []), 16)
        safe = head - (topup.min_confirmations() - 1)
        key = f"{ctx['chain']}:{ctx['wallet']}"
        cursor = self.store.cursor(key)
        start = max(0, safe - lookback_blocks()) if cursor is None else max(0, cursor - OVERLAP_BLOCKS)
        revisited = self.revisit_open()
        outcomes: dict[str, int] = defaultdict(int)
        while start <= safe:
            end = min(start + chunk_blocks() - 1, safe)
            logs = self.rpc("eth_getLogs", [{"address": ctx["token"], "fromBlock": hex(start),
                                             "toBlock": hex(end),
                                             "topics": [TRANSFER_TOPIC, None, ctx["wallet_topic"]]}]) or []
            seen: dict[str, dict[str, Any]] = {}
            for log in logs:
                tx = str(log.get("transactionHash") or "").lower()
                transfers = self._transfers_into([log], ctx)
                if not settle.is_tx_hash(tx) or not transfers:
                    continue
                entry = seen.setdefault(tx, {"sender": transfers[0][0], "units": 0,
                                             "block": int(str(log.get("blockNumber") or "0x0"), 16)})
                entry["units"] += transfers[0][1]
            for tx, entry in seen.items():
                known = self.store.deposit(tx)
                if known and known["status"] in FINAL:
                    continue   # re-read in the overlap, decided before
                try:
                    receipt = self.rpc("eth_getTransactionReceipt", [tx])
                except Retry as exc:
                    receipt, why = None, str(exc)
                else:
                    why = "the node has no receipt yet"
                if not receipt:
                    outcomes[self._pending(tx_hash=tx, sender=entry["sender"], amount_units=entry["units"],
                                           block=entry["block"], why=why)] += 1
                    continue
                outcomes[self.handle_receipt(tx_hash=tx, receipt=receipt, block=entry["block"])] += 1
            self.store.set_cursor(key, end + 1)
            start = end + 1
            if (safe - start) // chunk_blocks() + 1 > CATCH_UP_CHUNKS:
                _rest(catch_up_pause_s())
        return {"scanned": True, "head": head, "next_block": start, **dict(outcomes),
                **({"revisited": revisited} if revisited else {})}


def well_known(store: "DepositStore | None", hub_url: str) -> dict[str, Any]:
    """The ``payment_rails.credits.topup.deposit_watch`` block of the well-known."""
    out: dict[str, Any] = {"enabled": enabled()}
    if not enabled():
        out["reason"] = unavailable_reason()
        return out
    out.update({
        "wallet": dedicated_wallet(),
        "interval_s": interval_s(),
        "quotes": "a payment over a top-up quote is redeemed by the hub itself; presenting it is optional",
        "plain_transfers": "credited to the account that linked the sending wallet",
        "link": "/ai-market/v2/account/payer-wallets",
        "link_message": link_message(hub_url=hub_url, account_id="<account_id>", address="<address>",
                                     issued_at=0).replace("issued_at: 0", "issued_at: <unix seconds>"),
        "link_signature": "EIP-191 personal_sign by the wallet",
    })
    if store is not None:
        last = store.last_scan_at(f"{x402.chain()}:{dedicated_wallet()}")
        out.update({
            "unattributed_deposits": store.count_unattributed(),
            "pending_deposits": store.count_status(PENDING),
            # When the wallet was last read (unix seconds; null before the first scan): a watcher
            # that stopped scanning shows here, not as a green "enabled".
            "last_scan_at": round(last) if last else None,
        })
    return out
