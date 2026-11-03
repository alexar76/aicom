"""Credits — the payment rail that works with the chain switched off.

Why this exists. Before this module the hub had exactly one way to be paid: a payment
channel funded on Base. Reaching it takes six configuration interlocks
(``config.py`` :meth:`HubConfig.crypto_preflight_errors`), an ``AIMarketEscrow`` the
operator must deploy and own — ``debitChannel`` gates on ``authorizedHubs[msg.sender]``,
so the address shipped in ``deployments/base-mainnet.json`` is unusable by anyone but its
owner — and a deposit verifier (``channels._verify_tx_onchain``) that is not even present
in the hub wheel or its Docker image. The practical consequence, measured rather than
guessed: a stranger who deploys this hub serves every invoke for free, because
``AIFACTORY_CRYPTO_ENABLED`` defaults to ``0`` and with it off ``price`` is forced to
``0.0``. A node that cannot be paid is a node nobody runs twice.

So: one env var (``AIMARKET_CREDITS_ENABLED=1``), no chain, no contract, no wallet.
A buyer gets an API key, the operator credits it (by hand, or via a checkout the operator
wires up), and invokes debit it. That is the whole rail.

**Millicents, not cents.** The channel ledger bills in whole cents rounded UP
(``channels._dollars_to_cents_bill``), so the ecosystem's own measured average price of
$0.0059 bills as $0.01 — a ~70% overcharge — and nothing below a cent can be priced at
all. Agent capabilities are priced in tenths of a cent. This ledger's unit is a
**millicent** (1/1000 of a cent, i.e. $0.00001), so $0.0059 is 590mc exactly and stays
exact through hold → capture.

**Custody, stated plainly.** A prepaid balance is the operator physically holding a
buyer's money, exactly like the transfer-funded channel path (``channels`` ACCT-001).
Nothing here can send value either: :func:`stats` publishes ``outstanding_credit_usd`` so
the liability is a number the operator can see and a buyer can ask about, and refunds are
an operator action, not an automatic one. Do not switch this on for balances you are not
prepared to honour.

**The hold contract is the channel ledger's contract**, deliberately: the invoke path's
reserve-before-execute invariant (auth/capture) must behave identically on either rail, so
``hold`` / ``capture_hold`` / ``release_hold`` return the same ``{"error": ...}`` or
``{"remaining_balance": ...}`` shapes and the same "already resolved is a no-op" rule.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from typing import Any
from aimarket_hub import security_posture
from aimarket_hub.db_backend import atomic, returning_one
from aimarket_hub.paging import page_limit


# Ledger entries: the default page and the most one request may read.
LEDGER_PAGE = 50
LEDGER_PAGE_MAX = 500

logger = logging.getLogger(__name__)

# 1 cent = 1000 millicents; $1.00 = 100_000 millicents.
MILLICENTS_PER_DOLLAR = 100_000

KEY_PREFIX = "aimk_"
_KEY_BYTES = 24  # 192 bits — a guessable API key is a free invoke


def enabled() -> bool:
    """Is the credits rail switched on?

    Off by default so an existing deployment does not start demanding API keys the day it
    upgrades. It is a single variable rather than a preflight because there is nothing to
    get wrong: no address, no contract, no chain.
    """
    return os.getenv("AIMARKET_CREDITS_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def signup_open() -> bool:
    """May a stranger mint their own key, or must the operator issue it?

    Open by default *when the rail is on*: the blocker this whole module exists to remove
    is "one customer = edit .env and restart the hub". A self-minted key starts with a
    zero balance, so an open signup gives away nothing but a row.
    """
    return os.getenv("AIMARKET_CREDITS_OPEN_SIGNUP", "1").strip().lower() not in ("0", "false", "no")


def free_grant_usd() -> float:
    """Starting balance for a self-minted key, in USD.

    A small non-zero default (5 cents ≈ eight invokes at the measured average price) is
    what turns "here is my hub" into a demo the recipient can actually run without asking
    the operator for anything. Set to 0 to disable.
    """
    try:
        return max(0.0, float(os.getenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0.05")))
    except (TypeError, ValueError):
        return 0.0


# An operator top-up and a signup grant both land in the ledger as kind='grant'
# — the money moves the same way. Only the note tells them apart, and the budget
# has to count the second without being tripped by the first: one settled $25
# invoice would otherwise spend a whole day's grant budget.
SIGNUP_GRANT_NOTE = "signup grant"
# An account the operator opens with a starting balance is a decision, not a
# giveaway, so it must not eat the budget that protects self-serve signups.
OPERATOR_GRANT_NOTE = "operator opening balance"
# The row every self-serve signup updates first (job_counters), so budget checks queue.
_SIGNUP_COUNTER = "credits:signup-grant"


def signup_grant_usd() -> float:
    """What a self-minted key starts with — the separate switch for the grant.

    Kept apart from AIMARKET_CREDITS_FREE_GRANT_USD (which it falls back to, so
    an existing deployment does not change) because a grant is a growth
    experiment: it has to be switchable on its own, and killable in one edit,
    without touching the rest of the rail.
    """
    for name in ("AIMARKET_SIGNUP_GRANT_USD", "AIMARKET_CREDITS_FREE_GRANT_USD"):
        raw = os.getenv(name)
        if raw is None:
            continue
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 0.0
    return 0.05


def _budget(name: str, default: float) -> float:
    """A ceiling of 0 means "no grants", never "unlimited"."""
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def grant_budget_daily_usd() -> float:
    """Hard ceiling on grants minted in a rolling 24h, across every signup.

    This is the control that cannot be defeated. Every other defence against a
    farmed grant — per-address caps, signup limits — is a filter that a proxy
    pool can pay to get around. A budget just runs out, so the worst case is a
    number the operator chose rather than a number an attacker chose.
    """
    return _budget("AIMARKET_SIGNUP_GRANT_DAILY_USD", 5.0)


def grant_budget_total_usd() -> float:
    """Lifetime ceiling. 0 disables the lifetime limit and leaves only the daily one."""
    return _budget("AIMARKET_SIGNUP_GRANT_TOTAL_USD", 0.0)


def usd_to_mc(usd: float) -> int:
    """USD → millicents, rounded to nearest (not up — see the module docstring)."""
    try:
        return int(round(float(usd) * MILLICENTS_PER_DOLLAR))
    except (TypeError, ValueError):
        return 0


def mc_to_usd(mc: int) -> float:
    return round(int(mc or 0) / MILLICENTS_PER_DOLLAR, 6)


def hash_key(api_key: str) -> str:
    """Keys are stored hashed. 192 bits of entropy needs no salt or KDF — there is no
    low-entropy secret here to grind, and a per-hub salt would only break key portability
    across a restore."""
    return hashlib.sha256((api_key or "").strip().encode("utf-8")).hexdigest()


def _mint_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(_KEY_BYTES)


def _now() -> str:
    return "datetime('now')"


class CreditsLedger:
    """Prepaid balances over the hub's own database backend.

    Takes the backend (``HubDatabase._conn``) rather than a path so the rail works on
    PostgreSQL deployments too — every statement here goes through the same translating
    backend the rest of the hub uses.
    """

    def __init__(self, conn: Any):
        self._conn = conn

    # ── accounts ──────────────────────────────────────────────────────────

    def create_account(
        self, label: str = "", grant_usd: float = 0.0, grant_note: str = SIGNUP_GRANT_NOTE
    ) -> dict[str, Any]:
        """Mint an account and return its key ONCE. The key is never recoverable after
        this call — only its hash is stored."""
        with atomic(self._conn):
            return self._insert_account(label, grant_usd, grant_note)

    def open_signup_account(self, label: str = "") -> dict[str, Any]:
        """A self-serve account, with the signup grant if the grant budget still has room.

        The budget check and the grant are one transaction, and every signup first updates
        the same counter row, so they run one at a time on every worker and replica (the row
        lock on PostgreSQL, the write lock on SQLite). Checked and minted as two steps, as
        until 2026-10-22, concurrent signups on more than one process all read the same
        remaining budget and all minted: each one past the ceiling was a grant the operator
        never agreed to. ``grant_note`` says why an account opened at zero.
        """
        grant = signup_grant_usd()
        self._conn.execute(
            "INSERT INTO job_counters (counter, n) VALUES (?, 0) ON CONFLICT DO NOTHING", (_SIGNUP_COUNTER,),
        )
        self._conn.commit()
        note = ""
        with atomic(self._conn):
            self._conn.execute("UPDATE job_counters SET n = n + 1 WHERE counter = ?", (_SIGNUP_COUNTER,))
            if grant > 0:
                allowed, reason = self.grant_within_budget(grant)
                if not allowed:
                    grant, note = 0.0, reason
            account = self._insert_account(label, grant, SIGNUP_GRANT_NOTE)
        return {**account, **({"grant_note": note} if note else {})}

    def _insert_account(self, label: str, grant_usd: float, grant_note: str) -> dict[str, Any]:
        """The rows of a new account; the caller commits (inside ``atomic``)."""
        api_key = _mint_key()
        account_id = "acct_" + secrets.token_hex(8)
        grant_mc = max(0, usd_to_mc(grant_usd))
        self._conn.execute(
            "INSERT INTO credit_accounts (account_id, key_hash, label, balance_mc, granted_mc) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, hash_key(api_key), (label or "")[:120], grant_mc, grant_mc),
        )
        if grant_mc:
            self._log(account_id, "grant", grant_mc, note=grant_note or SIGNUP_GRANT_NOTE)
        return {
            "account_id": account_id,
            "api_key": api_key,
            "balance_usd": mc_to_usd(grant_mc),
            "label": (label or "")[:120],
        }

    def resolve(self, api_key: str) -> str:
        """API key → account_id, or "" when unknown/disabled."""
        key = (api_key or "").strip()
        if not key:
            return ""
        row = self._conn.execute(
            "SELECT account_id, status FROM credit_accounts WHERE key_hash = ?",
            (hash_key(key),),
        ).fetchone()
        if not row:
            # A key no account owns: one is a typo, a stream of them is someone guessing.
            security_posture.record_once(security_posture.BAD_API_KEY, hash_key(key)[:16])
            return ""
        if str(row["status"] or "active") != "active":
            return ""
        return str(row["account_id"])

    def account(self, account_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT account_id, label, balance_mc, held_mc, spent_mc, granted_mc, "
            "collateral_mc, topped_up_mc, status, created_at "
            "FROM credit_accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "account_id": row["account_id"],
            "label": row["label"],
            "balance_usd": mc_to_usd(row["balance_mc"]),
            "held_usd": mc_to_usd(row["held_mc"]),
            "spent_usd": mc_to_usd(row["spent_mc"]),
            "collateral_usd": mc_to_usd(row["collateral_mc"]),
            "granted_usd": mc_to_usd(row["granted_mc"]),
            "topped_up_usd": mc_to_usd(row["topped_up_mc"] or 0),
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def balance(self, account_id: str) -> float:
        row = self._conn.execute(
            "SELECT balance_mc FROM credit_accounts WHERE account_id = ?", (account_id,),
        ).fetchone()
        return mc_to_usd(row["balance_mc"]) if row else 0.0

    def grant(
        self,
        account_id: str,
        amount_usd: float,
        note: str = "",
        reference: str = "",
    ) -> dict[str, Any]:
        """Add credit. This is the operator's action — a top-up rail (checkout, invoice,
        an on-chain transfer they watched land) calls this after it has the money.

        ``reference`` is the processor event id, invoice id or chain transaction id. When
        present it is unique across the hub, making webhook/CLI retries safe.
        """
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "grant amount must be positive"}
        reference = (reference or "").strip()[:200]
        note = (note or "")[:200]
        try:
            with atomic(self._conn):
                if reference:
                    existing = self._conn.execute(
                        "SELECT account_id, amount_mc FROM credit_topups WHERE reference = ?",
                        (reference,),
                    ).fetchone()
                    if existing:
                        if str(existing["account_id"]) != account_id or int(existing["amount_mc"]) != amount_mc:
                            return {"error": "top-up reference already belongs to a different account or amount"}
                        return {
                            "account_id": account_id,
                            "credited_usd": mc_to_usd(amount_mc),
                            "balance_usd": self.balance(account_id),
                            "reference": reference,
                            "idempotent_replay": True,
                        }
                    self._conn.execute(
                        "INSERT INTO credit_topups (reference, account_id, amount_mc, note) VALUES (?, ?, ?, ?)",
                        (reference, account_id, amount_mc, note),
                    )
                cur = self._conn.execute(
                    "UPDATE credit_accounts SET balance_mc = balance_mc + ?, granted_mc = granted_mc + ? "
                    "WHERE account_id = ? AND status = 'active'",
                    (amount_mc, amount_mc, account_id),
                )
                if not _changed(cur):
                    # Raised, not returned, so the reference row written above rolls back with it.
                    raise _UnknownAccount(account_id)
                self._log(account_id, "grant", amount_mc, note=note)
                return {
                    "account_id": account_id,
                    "credited_usd": mc_to_usd(amount_mc),
                    "balance_usd": self.balance(account_id),
                    "reference": reference,
                    "idempotent_replay": False,
                }
        except _UnknownAccount:
            return {"error": f"unknown or disabled account {account_id}"}

    def deposit(self, account_id: str, amount_mc: int, *, reference: str, note: str = "") -> dict[str, Any]:
        """Credit money the buyer PAID (a USDC top-up), once per ``reference``.

        Not :meth:`grant`: a grant is credit given away and counts toward ``granted_mc``,
        which the signup-grant budget and the solvency report read as "free". Paid credit
        goes to ``topped_up_mc`` and the ledger as ``topup``.

        The reference row, the balance and the ledger line are written as ONE transaction
        (``db_backend.atomic``), so a retry — or two redemptions racing — credits once, and no
        other thread's statement can undo part of it between the writes. An account the
        operator disabled is still credited: the money has arrived, and a disabled account
        cannot spend it anyway.
        """
        amount_mc = int(amount_mc)
        reference = (reference or "").strip()[:200]
        if amount_mc <= 0:
            return {"error": "deposit amount must be positive"}
        if not reference:
            return {"error": "a deposit needs a reference"}

        def replay(row: Any) -> dict[str, Any]:
            if str(row["account_id"]) != account_id or int(row["amount_mc"]) != amount_mc:
                return {"error": "deposit reference already belongs to a different account or amount"}
            return {"account_id": account_id, "credited_usd": mc_to_usd(amount_mc),
                    "balance_usd": self.balance(account_id), "reference": reference,
                    "idempotent_replay": True}

        def existing() -> Any:
            return self._conn.execute(
                "SELECT account_id, amount_mc FROM credit_topups WHERE reference = ?", (reference,),
            ).fetchone()

        class _Unknown(Exception):
            pass

        try:
            with atomic(self._conn):
                row = existing()
                if row:
                    return replay(row)
                self._conn.execute(
                    "INSERT INTO credit_topups (reference, account_id, amount_mc, note) VALUES (?, ?, ?, ?)",
                    (reference, account_id, amount_mc, (note or "")[:200]),
                )
                cur = self._conn.execute(
                    "UPDATE credit_accounts SET balance_mc = balance_mc + ?, topped_up_mc = topped_up_mc + ? "
                    "WHERE account_id = ?",
                    (amount_mc, amount_mc, account_id),
                )
                if not _changed(cur):
                    raise _Unknown(account_id)
                self._log(account_id, "topup", amount_mc, receipt_id=reference, note=note)
        except _Unknown:
            return {"error": f"unknown account {account_id}"}
        except Exception as exc:  # noqa: BLE001 - one read back, never a retry loop
            row = existing()
            if row:
                return replay(row)     # the same reference committed by a racing redemption
            logger.error("credits: deposit %s for %s not written: %s", reference, account_id, exc)
            return {"error": "the deposit could not be written; nothing was credited"}
        return {"account_id": account_id, "credited_usd": mc_to_usd(amount_mc),
                "balance_usd": self.balance(account_id), "reference": reference,
                "idempotent_replay": False}

    def rotate_key(self, api_key: str) -> dict[str, Any]:
        """Replace an account's key with a new one; the old key stops working at once.

        The holder authenticates with the key itself — a leaked key (pasted in a notebook,
        logged in a URL) used to need the operator to disable the whole account. The new
        key is returned ONCE, like at signup; balance, ledger and links are unchanged.
        """
        account_id = self.resolve(api_key)
        if not account_id:
            return {"error": "unknown or disabled key"}
        new_key = _mint_key()
        cur = self._conn.execute(
            "UPDATE credit_accounts SET key_hash = ? WHERE account_id = ? AND key_hash = ?",
            (hash_key(new_key), account_id, hash_key(api_key)),
        )
        if not _changed(cur):
            return {"error": "the key changed concurrently; use the newer one"}
        self._log(account_id, "key_rotated", 0, note="holder rotated the API key")
        self._conn.commit()
        return {"account_id": account_id, "api_key": new_key}

    def set_status(self, account_id: str, status: str) -> dict[str, Any]:
        if status not in ("active", "disabled"):
            return {"error": "status must be active or disabled"}
        cur = self._conn.execute(
            "UPDATE credit_accounts SET status = ? WHERE account_id = ?", (status, account_id),
        )
        if not _changed(cur):
            return {"error": f"unknown account {account_id}"}
        self._conn.commit()
        return {"account_id": account_id, "status": status}

    # ── the money path ────────────────────────────────────────────────────

    def hold(self, account_id: str, amount_usd: float, receipt_id: str) -> dict[str, Any]:
        """Reserve funds before the provider runs (the auth leg of auth/capture).

        The reservation is a single conditional UPDATE — ``balance_mc >= ?`` inside the
        statement, not a read-then-write — because N concurrent invokes on one account
        would otherwise all observe the same sufficient balance and only discover the
        shortfall after the provider had already done billable work.
        """
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "hold amount must be positive"}
        if not receipt_id:
            return {"error": "hold requires a receipt id"}
        with atomic(self._conn):
            existing = self._conn.execute(
                "SELECT status FROM credit_holds WHERE receipt_id = ?", (receipt_id,),
            ).fetchone()
            if existing:
                return {"error": f"receipt {receipt_id} already used"}
            cur = self._conn.execute(
                "UPDATE credit_accounts SET balance_mc = balance_mc - ?, held_mc = held_mc + ? "
                "WHERE account_id = ? AND status = 'active' AND balance_mc >= ?",
                (amount_mc, amount_mc, account_id, amount_mc),
            )
            if not _changed(cur):
                return {"error": (
                    f"insufficient credit: {mc_to_usd(amount_mc)} needed, "
                    f"{self.balance(account_id)} available"
                )}
            self._conn.execute(
                "INSERT INTO credit_holds (receipt_id, account_id, amount_mc, status) "
                "VALUES (?, ?, ?, 'held')",
                (receipt_id, account_id, amount_mc),
            )
            self._log(account_id, "hold", amount_mc, receipt_id=receipt_id)
            return {"held_usd": mc_to_usd(amount_mc), "remaining_balance": self.balance(account_id)}

    def _claim_resolution(self, receipt_id: str, status: str) -> Any:
        """Move a hold out of 'held' and say whether THIS call did it. Call it inside the
        ``atomic`` block that moves the money.

        The status change comes first and decides the winner. The old order — read the
        status, then move the money, then mark the row — let two concurrent resolutions of
        one hold both see 'held' and both move the money: a double refund, or a refund plus
        a capture. RETURNING hands the row only to the statement that changed it; a row
        count would not do, because on the shared SQLite connection it is read from a
        connection-global counter another thread can overwrite (see db_backend.claim_unique).

        The claim and the money move commit together. Until 2026-10-22 the claim committed
        on its own first, so that another thread's failed statement could not roll it back
        under a balance change that still committed — and that opened the opposite hole: a
        process that died (or a foreign rollback that landed) between the two left a hold
        marked resolved whose money never moved, which no sweep looks at again. One
        transaction under the connection's lock closes both (tests/test_ledger_crash_consistency.py).
        On PostgreSQL the claim's row lock makes a concurrent resolver wait for the commit
        and then find the row resolved.
        """
        return returning_one(
            self._conn,
            "UPDATE credit_holds SET status = ?, resolved_at = datetime('now') "
            "WHERE receipt_id = ? AND status = 'held' "
            "RETURNING account_id, amount_mc, parent_receipt_id",
            (status, receipt_id),
        )

    def _unresolved_answer(self, receipt_id: str, key: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT status FROM credit_holds WHERE receipt_id = ?", (receipt_id,),
        ).fetchone()
        if not row:
            return {"error": f"no hold for receipt {receipt_id}"}
        return {key: 0.0, "already": str(row["status"])}

    def capture_hold(self, receipt_id: str) -> dict[str, Any]:
        """Turn a reservation into a recorded debit. A no-op on an already-resolved hold,
        so a late exception on a settled invoke cannot double-charge."""
        with atomic(self._conn):
            won = self._claim_resolution(receipt_id, "captured")
            if won is None:
                return self._unresolved_answer(receipt_id, "captured_usd")
            amount_mc = int(won["amount_mc"])
            account_id = str(won["account_id"])
            self._conn.execute(
                "UPDATE credit_accounts SET held_mc = held_mc - ?, spent_mc = spent_mc + ? "
                "WHERE account_id = ?",
                (amount_mc, amount_mc, account_id),
            )
            self._log(account_id, "capture", amount_mc, receipt_id=receipt_id)
            return {"captured_usd": mc_to_usd(amount_mc), "remaining_balance": self.balance(account_id)}

    def release_hold(self, receipt_id: str) -> dict[str, Any]:
        """Hand a reservation back. Ungated and idempotent for the same reason the channel
        ledger's is: an in-flight hold must resolve even if the operator flips the rail off
        mid-invoke, otherwise the buyer's balance stays frozen.

        A hold carved out of an allowance (:meth:`transfer_hold`) goes back to that
        allowance while it is still open, so a subcontractor that failed does not shrink
        the budget a retry would be paid from. Once the allowance is closed the money goes
        to the balance like any other release. Either way the account's ``held_mc`` stays
        exact: money returned to the parent is still held, just under the parent's id.
        """
        with atomic(self._conn):
            won = self._claim_resolution(receipt_id, "released")
            if won is None:
                return self._unresolved_answer(receipt_id, "released_usd")
            amount_mc = int(won["amount_mc"])
            account_id = str(won["account_id"])
            parent = str(won["parent_receipt_id"] or "")
            if parent:
                back = returning_one(
                    self._conn,
                    "UPDATE credit_holds SET amount_mc = amount_mc + ? "
                    "WHERE receipt_id = ? AND status = 'held' RETURNING receipt_id",
                    (amount_mc, parent),
                )
                if back is not None:
                    self._log(account_id, "release", amount_mc, receipt_id=receipt_id,
                              note=f"back to allowance {parent}"[:200])
                    return {
                        "released_usd": mc_to_usd(amount_mc),
                        "returned_to": parent,
                        "remaining_balance": self.balance(account_id),
                    }
            self._conn.execute(
                "UPDATE credit_accounts SET held_mc = held_mc - ?, balance_mc = balance_mc + ? "
                "WHERE account_id = ?",
                (amount_mc, amount_mc, account_id),
            )
            self._log(account_id, "release", amount_mc, receipt_id=receipt_id)
            return {"released_usd": mc_to_usd(amount_mc), "remaining_balance": self.balance(account_id)}

    def transfer_hold(
        self, parent_receipt_id: str, receipt_id: str, amount_usd: float,
    ) -> dict[str, Any]:
        """Carve a hold for ``receipt_id`` out of the still-held ``parent_receipt_id``.

        This is how a subcontractor is paid from a job's allowance (mandates.md §6.2). The
        money is already reserved — it left the balance when the allowance was held — so
        nothing about the account changes: part of one reservation becomes a reservation of
        its own. The parent is shrunk by ONE conditional statement (`amount_mc >= ?`), so
        however many children race for the same allowance, together they can never take
        more than it holds, and a closed allowance cannot be drawn on at all.
        """
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "hold amount must be positive"}
        if not receipt_id or not parent_receipt_id or receipt_id == parent_receipt_id:
            return {"error": "transfer_hold needs two distinct receipt ids"}
        # The decrement and the child row are one transaction. Committing the decrement first
        # (as until 2026-10-22) meant a process that died before the child row existed took
        # the money out of the allowance for a child nobody would ever release; a child row
        # that fails to insert now simply rolls the decrement back with it.
        with atomic(self._conn):
            if self._conn.execute(
                "SELECT 1 FROM credit_holds WHERE receipt_id = ?", (receipt_id,),
            ).fetchone():
                return {"error": f"receipt {receipt_id} already used"}
            taken = returning_one(
                self._conn,
                "UPDATE credit_holds SET amount_mc = amount_mc - ? "
                "WHERE receipt_id = ? AND status = 'held' AND amount_mc >= ? "
                "AND EXISTS (SELECT 1 FROM credit_accounts a "
                "WHERE a.account_id = credit_holds.account_id AND a.status = 'active') "
                "RETURNING account_id, amount_mc",
                (amount_mc, parent_receipt_id, amount_mc),
            )
            if taken is None:
                return {"error": "the allowance is closed or cannot cover this price"}
            account_id = str(taken["account_id"])
            self._conn.execute(
                "INSERT INTO credit_holds (receipt_id, account_id, amount_mc, status, parent_receipt_id) "
                "VALUES (?, ?, ?, 'held', ?)",
                (receipt_id, account_id, amount_mc, parent_receipt_id),
            )
            self._log(account_id, "hold", amount_mc, receipt_id=receipt_id,
                      note=f"from allowance {parent_receipt_id}"[:200])
            return {
                "held_usd": mc_to_usd(amount_mc),
                "allowance_left_usd": mc_to_usd(int(taken["amount_mc"])),
                "remaining_balance": self.balance(account_id),
            }

    def hold_status(self, receipt_id: str) -> dict[str, Any] | None:
        """Who a hold belongs to and where it stands, or None when there is no such hold."""
        row = self._conn.execute(
            "SELECT account_id, amount_mc, status FROM credit_holds WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "account_id": str(row["account_id"]),
            "amount_usd": mc_to_usd(row["amount_mc"]),
            "status": str(row["status"]),
        }

    def hold_amount_usd(self, receipt_id: str) -> float:
        """What a hold currently reserves (an allowance shrinks as children draw on it)."""
        row = self._conn.execute(
            "SELECT amount_mc FROM credit_holds WHERE receipt_id = ?", (receipt_id,),
        ).fetchone()
        return mc_to_usd(row["amount_mc"]) if row else 0.0

    def debit(self, account_id: str, amount_usd: float, receipt_id: str = "",
              note: str = "", *, as_collateral: bool = False) -> dict[str, Any]:
        """Charge immediately, without a reservation.

        Used for the routing fee (collected after a peer has already answered, so there is
        nothing left to reserve against) and for posted collateral.

        ``as_collateral`` decides which column the money lands in, and the distinction is
        not cosmetic: a publisher's stake is money the operator holds and may have to give
        back, so booking it as revenue overstates earnings by the whole stake the moment
        anybody publishes — the operator would read `credits_earned_usd: 25.00` off a hub
        that had earned nothing.
        """
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc < 0:
            return {"error": "debit amount must not be negative"}
        if amount_mc == 0:
            return {"debited_usd": 0.0, "remaining_balance": self.balance(account_id)}
        column = "collateral_mc" if as_collateral else "spent_mc"
        with atomic(self._conn):
            cur = self._conn.execute(
                f"UPDATE credit_accounts SET balance_mc = balance_mc - ?, {column} = {column} + ? "
                "WHERE account_id = ? AND status = 'active' AND balance_mc >= ?",
                (amount_mc, amount_mc, account_id, amount_mc),
            )
            if not _changed(cur):
                return {"error": (
                    f"insufficient credit: {mc_to_usd(amount_mc)} needed, "
                    f"{self.balance(account_id)} available"
                )}
            self._log(
                account_id, "collateral" if as_collateral else "debit", amount_mc,
                receipt_id=receipt_id, note=note,
            )
            return {"debited_usd": mc_to_usd(amount_mc), "remaining_balance": self.balance(account_id)}

    def return_collateral(self, account_id: str, amount_usd: float, note: str = "") -> dict[str, Any]:
        """Give posted collateral back — an unstake, or a stake the ledger then refused."""
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "amount must be positive"}
        with atomic(self._conn):
            cur = self._conn.execute(
                "UPDATE credit_accounts SET balance_mc = balance_mc + ?, "
                "collateral_mc = CASE WHEN collateral_mc >= ? THEN collateral_mc - ? ELSE 0 END "
                "WHERE account_id = ?",
                (amount_mc, amount_mc, amount_mc, account_id),
            )
            if not _changed(cur):
                return {"error": f"unknown account {account_id}"}
            self._log(account_id, "collateral_return", amount_mc, note=note)
            return {"returned_usd": mc_to_usd(amount_mc), "balance_usd": self.balance(account_id)}

    def refund(self, account_id: str, amount_usd: float, note: str = "") -> dict[str, Any]:
        """Put money back (safety refusal, operator goodwill). Separate from `grant` so the
        ledger can tell revenue reversal apart from new money."""
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "refund amount must be positive"}
        with atomic(self._conn):
            cur = self._conn.execute(
                "UPDATE credit_accounts SET balance_mc = balance_mc + ?, "
                "spent_mc = CASE WHEN spent_mc >= ? THEN spent_mc - ? ELSE 0 END "
                "WHERE account_id = ?",
                (amount_mc, amount_mc, amount_mc, account_id),
            )
            if not _changed(cur):
                return {"error": f"unknown account {account_id}"}
            self._log(account_id, "refund", amount_mc, note=note)
            return {"refunded_usd": mc_to_usd(amount_mc), "balance_usd": self.balance(account_id)}

    def pay_publisher(self, account_id: str, amount_usd: float, *,
                      receipt_id: str = "", note: str = "") -> dict[str, Any]:
        """Credit a seller their share of a call a buyer just paid for.

        This is the seller-earnings route the hub never had. Its absence is why the
        marketplace was one-sided: `channels` states plainly that nothing in it can send
        value, the only obligations table refunds depositors rather than paying providers,
        and the one rev-share design in the tree (`data_capability`, 70% to the owner) was
        imported by nothing but its tests. A publisher could list, could be invoked, and had
        no way to be paid short of the operator wiring money by hand.

        Inside one ledger this is just a transfer, and it is honest about what it is: the
        seller's balance goes up, which makes it money the operator OWES rather than money
        the operator earned. `stats` reports both sides.
        """
        amount_mc = usd_to_mc(amount_usd)
        if amount_mc <= 0:
            return {"error": "payout amount must be positive"}
        with atomic(self._conn):
            cur = self._conn.execute(
                "UPDATE credit_accounts SET balance_mc = balance_mc + ? WHERE account_id = ?",
                (amount_mc, account_id),
            )
            if not _changed(cur):
                return {"error": f"unknown account {account_id}"}
            self._log(account_id, "payout", amount_mc, receipt_id=receipt_id, note=note)
            return {"paid_usd": mc_to_usd(amount_mc), "balance_usd": self.balance(account_id)}

    def payouts_total_usd(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_mc), 0) AS total FROM credit_ledger WHERE kind = 'payout'",
        ).fetchone()
        return mc_to_usd(int(row["total"] or 0)) if row else 0.0

    def earnings(self, account_id: str) -> float:
        """What one seller has been paid through this hub."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_mc), 0) AS total FROM credit_ledger "
            "WHERE kind = 'payout' AND account_id = ?",
            (account_id,),
        ).fetchone()
        return mc_to_usd(int(row["total"] or 0)) if row else 0.0

    # ── reporting ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Rail-level totals.

        ``outstanding_credit_usd`` is the solvency number: prepaid money the operator holds
        and has not yet earned. It is published for the same reason the channel ledger
        publishes its obligations — a custodial balance nobody can see is how a hub ends up
        insolvent without noticing.
        """
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(balance_mc), 0) AS bal, "
            "COALESCE(SUM(held_mc), 0) AS held, COALESCE(SUM(spent_mc), 0) AS spent, "
            "COALESCE(SUM(granted_mc), 0) AS granted, "
            "COALESCE(SUM(topped_up_mc), 0) AS topped_up, "
            "COALESCE(SUM(collateral_mc), 0) AS collateral FROM credit_accounts",
        ).fetchone()
        if not row:
            return {"accounts": 0, "credits_earned_usd": 0.0, "outstanding_credit_usd": 0.0,
                    "held_usd": 0.0, "granted_usd": 0.0, "topped_up_usd": 0.0, "collateral_usd": 0.0}
        return {
            "accounts": int(row["n"] or 0),
            # What the hub has actually earned on this rail — the only number that answers
            # "is the node's P&L non-zero". Collateral is excluded on purpose.
            "credits_earned_usd": mc_to_usd(row["spent"]),
            # Everything the operator is holding for somebody else: unspent balances,
            # in-flight reservations, and posted stake.
            "outstanding_credit_usd": mc_to_usd(
                int(row["bal"] or 0) + int(row["held"] or 0) + int(row["collateral"] or 0)
            ),
            "held_usd": mc_to_usd(row["held"]),
            "collateral_usd": mc_to_usd(row["collateral"]),
            "granted_usd": mc_to_usd(row["granted"]),
            # Credit buyers PAID for (USDC top-ups): money the operator received and still
            # owes as service, as opposed to credit it gave away.
            "topped_up_usd": mc_to_usd(row["topped_up"]),
            # Gross is what buyers spent; the hub keeps gross minus what it paid sellers.
            "publisher_payouts_usd": self.payouts_total_usd(),
            "operator_net_usd": round(
                mc_to_usd(row["spent"]) - self.payouts_total_usd(), 6
            ),
        }

    def granted_mc(self, *, since_hours: float = 0.0) -> int:
        """Signup grants minted, all accounts. `since_hours=0` counts from the beginning.

        Operator top-ups are excluded on purpose — see SIGNUP_GRANT_NOTE.

        The window is applied in Python, not as ``created_at >= datetime('now', ?)``: the
        PostgreSQL translator rewrites only a bare ``datetime('now')``, so the query failed
        there outright, and ``created_at`` holds NOW() as text in the SESSION's zone, which no
        text comparison reads correctly. The newest rows are read by id and their timestamps
        parsed with any offset they carry.
        """
        if since_hours <= 0:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(amount_mc), 0) AS total FROM credit_ledger "
                "WHERE kind = 'grant' AND note = ?",
                (SIGNUP_GRANT_NOTE,),
            ).fetchone()
            return int((row["total"] if row else 0) or 0)
        from aimarket_hub.invoke_funding import _age_s

        now = time.time()
        window = float(since_hours) * 3600.0
        total = 0
        rows = self._conn.execute(
            "SELECT amount_mc, created_at FROM credit_ledger WHERE kind = 'grant' AND note = ? "
            "ORDER BY id DESC LIMIT 20000",
            (SIGNUP_GRANT_NOTE,),
        ).fetchall()
        for r in rows:
            age = _age_s(r["created_at"], now)
            if age is None:
                continue
            if age > window:
                break          # ids grow with time: everything older follows
            total += int(r["amount_mc"] or 0)
        return total

    def grant_within_budget(self, grant_usd: float) -> tuple[bool, str]:
        """May this grant be minted without breaching a ceiling?"""
        amount_mc = usd_to_mc(grant_usd)
        if amount_mc <= 0:
            return False, "grant is off"
        daily = grant_budget_daily_usd()
        if daily <= 0:
            return False, "signup grants are disabled by AIMARKET_SIGNUP_GRANT_DAILY_USD=0"
        if self.granted_mc(since_hours=24) + amount_mc > usd_to_mc(daily):
            return False, "the daily signup-grant budget is spent; try again tomorrow"
        total = grant_budget_total_usd()
        if total > 0 and self.granted_mc() + amount_mc > usd_to_mc(total):
            return False, "the lifetime signup-grant budget is spent"
        return True, ""

    def recent(self, account_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        limit = page_limit(limit, default=LEDGER_PAGE, maximum=LEDGER_PAGE_MAX)
        if account_id:
            rows = self._conn.execute(
                "SELECT account_id, kind, amount_mc, receipt_id, note, created_at "
                "FROM credit_ledger WHERE account_id = ? ORDER BY id DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT account_id, kind, amount_mc, receipt_id, note, created_at "
                "FROM credit_ledger ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "account_id": r["account_id"],
                "kind": r["kind"],
                "amount_usd": mc_to_usd(r["amount_mc"]),
                "receipt_id": r["receipt_id"],
                "note": r["note"],
                "created_at": r["created_at"],
            }
            for r in (rows or [])
        ]

    # ── internals ─────────────────────────────────────────────────────────

    def _log(self, account_id: str, kind: str, amount_mc: int,
             receipt_id: str = "", note: str = "") -> None:
        self._conn.execute(
            "INSERT INTO credit_ledger (account_id, kind, amount_mc, receipt_id, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, kind, int(amount_mc), receipt_id or "", (note or "")[:200]),
        )


class _UnknownAccount(Exception):
    """A grant to an account that does not exist or is disabled; rolls its reference row back."""


def _changed(cursor: Any) -> bool:
    """Did the conditional UPDATE actually hit a row?

    The whole atomicity of a hold rests on this answer, so an unknown rowcount is treated
    as failure rather than success: refusing a good invoke is recoverable, serving an
    unpaid one is not.
    """
    count = getattr(cursor, "rowcount", None)
    if count is None:
        return False
    return int(count) > 0


# ── process-wide instance ────────────────────────────────────────────────
_LEDGER: CreditsLedger | None = None


def configure(conn: Any) -> CreditsLedger:
    """Bind the rail to the hub's database backend. Called once from ``create_app``."""
    global _LEDGER
    _LEDGER = CreditsLedger(conn)
    return _LEDGER


def ledger() -> CreditsLedger | None:
    return _LEDGER
