"""Subcontracting — a provider that buys from another provider while serving a call.

Normative text: ``aimarket-protocol/mandates.md`` §6. This module is the reference
implementation.

Before this, a provider that called the hub from inside its own invocation was just another
anonymous buyer: its purchase had no link to the call it was serving, no budget from the
buyer who started the work, no depth limit and no place in any receipt. A chain of agents
hiring agents was invisible to the market, and nothing stopped A → B → A → B.

Two mechanisms, deliberately separate:

* **The job token** (``X-AIMarket-Job``) is linkage only. The hub signs it and sends it to
  every local provider it executes; a provider that sends it back on a purchase gets that
  purchase recorded as a child in the job tree, with depth, cycle and fan-out limits. It
  carries no money, so a provider paying for its own subcontractors (fixed price) needs
  nothing else.
* **The grant** (``X-AIMarket-Job-Grant``) is money: a bearer secret for a pass-through
  allowance the ROOT buyer set aside for subcontractors (cost-plus). The allowance is a
  credit hold taken with the root call; a child's price is carved out of it by one
  conditional statement (``CreditsLedger.transfer_hold``), so children can never spend more
  than the allowance however many run at once, and a failed child's money flows back into
  the allowance for a retry.

Both are local-execution features: the hub can only link calls it executes and pass through
money it meters.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from aimarket_hub.db_backend import atomic, returning_one

logger = logging.getLogger(__name__)

JOB_HEADER = "X-AIMarket-Job"
GRANT_HEADER = "X-AIMarket-Job-Grant"
HUB_HEADER = "X-AIMarket-Hub"

HUB_MAX_DEPTH = 3
MAX_NODES_PER_JOB = 64
MAX_CHILDREN_PER_NODE = 16
# The provider timeout (outbound_http invoke) plus a margin: a token outliving the call it
# was issued for would let a provider attach purchases to a job that has finished.
TOKEN_TTL_S = 60
# Prepended to the claims before signing: the hub's signing key signs manifests and
# attestations too, and a job token must never verify as one of those (or they as it).
TOKEN_DOMAIN = b"aimarket-job-token/1\n"
MICRO_PER_USD = 1_000_000


def max_allowance_usd() -> float:
    try:
        return max(0.0, float(os.getenv("AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD", "1.0")))
    except (TypeError, ValueError):
        return 1.0


class SubcontractError(Exception):
    def __init__(self, status: int, error: str, detail: str, **extra: Any):
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {"success": False, "error": self.error, "detail": self.detail, **self.extra,
                "protocol_version": "v2"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _canonical(claims: dict[str, Any]) -> bytes:
    # Claims hold only strings, integers and a list of strings, for which sorted-key compact
    # JSON is exactly RFC 8785. Floats are refused so that stays true.
    for value in claims.values():
        if isinstance(value, float):
            raise ValueError("job token claims must not hold floats")
    return json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash_secret(secret: str) -> str:
    return hashlib.sha256((secret or "").encode("utf-8")).hexdigest()


def usd_to_micro(usd: float) -> int:
    return int(round(float(usd) * MICRO_PER_USD))


def micro_to_usd(micro: int) -> float:
    return round(int(micro) / MICRO_PER_USD, 6)


@dataclass
class JobContext:
    """What one invocation knows about the job it belongs to.

    ``node`` is this invocation's node id; the provider the hub runs for it receives a token
    naming it, so anything that provider buys becomes this node's child.
    """

    job_id: str
    node: str
    depth: int
    max_depth: int
    path: list[str]
    product_id: str = ""
    parent: str = ""
    funded_by: str = "own"          # "own" | "allowance"
    grant_secret: str = field(default="", repr=False)  # money credential for this node's provider
    grant: dict[str, Any] | None = field(default=None, repr=False)
    is_root: bool = False
    allowance_receipt: str = ""
    allowance_micro: int = 0
    children_parents: list[dict[str, str]] = field(default_factory=list)


class JobStore:
    """Job trees, grants and the signed tokens that tie them to invocations."""

    def __init__(self, conn: Any, signer: Any, hub_origin: str):
        self._conn = conn
        self._signer = signer
        self.hub_origin = (hub_origin or "").rstrip("/")

    # tokens -----------------------------------------------------------------

    def issue_token(self, ctx: JobContext, *, now: float | None = None) -> str:
        now = time.time() if now is None else now
        claims = {
            "v": 1,
            "iss": self.hub_origin,
            "job": ctx.job_id,
            "node": ctx.node,
            "depth": ctx.depth,
            "maxDepth": ctx.max_depth,
            "exp": int(now) + TOKEN_TTL_S,
            "path": list(ctx.path),
            "product": ctx.product_id,
        }
        payload = _canonical(claims)
        return f"{_b64url(payload)}.{_b64url(self._signer.sign(TOKEN_DOMAIN + payload))}"

    def verify_token(self, token: str, *, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        try:
            payload_b64, sig_b64 = (token or "").strip().split(".", 1)
            payload = _b64url_decode(payload_b64)
            signature = _b64url_decode(sig_b64)
            claims = json.loads(payload)
        except Exception as exc:
            raise SubcontractError(403, "job_invalid", f"{JOB_HEADER} is not a job token") from exc
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            Ed25519PublicKey.from_public_bytes(
                base64.b64decode(self._signer.public_key_b64)
            ).verify(signature, TOKEN_DOMAIN + payload)
        except Exception as exc:
            raise SubcontractError(403, "job_invalid", "the job token was not signed by this hub") from exc
        if not isinstance(claims, dict) or claims.get("v") != 1 or claims.get("iss") != self.hub_origin:
            raise SubcontractError(403, "job_invalid", "the job token was issued for another hub")
        if int(claims.get("exp", 0)) < now:
            raise SubcontractError(403, "job_invalid", "the job token has expired")
        for key in ("job", "node"):
            if not isinstance(claims.get(key), str) or not claims[key]:
                raise SubcontractError(403, "job_invalid", f"the job token has no {key}")
        if not isinstance(claims.get("path"), list):
            raise SubcontractError(403, "job_invalid", "the job token has no path")
        return claims

    # roots ------------------------------------------------------------------

    def open_root(self, *, product_id: str, capability_id: str, allowance_micro: int = 0,
                  max_depth: int = 1, account_id: str = "", allowance_receipt: str = "",
                  mandate_digest: str = "", now: float | None = None) -> JobContext:
        """A job context for a call the hub is about to execute.

        With no allowance nothing is written: the token alone lets the provider attach
        purchases, and the root row is created the first time one does. With an allowance
        the grant row is written now, because it is what a child's payment is checked
        against.
        """
        now = time.time() if now is None else now
        ctx = JobContext(
            job_id=f"job_{secrets.token_hex(12)}",
            node=f"node_{secrets.token_hex(12)}",
            depth=0,
            max_depth=max(1, min(int(max_depth or 1), HUB_MAX_DEPTH)),
            path=[capability_id],
            product_id=product_id,
            is_root=True,
        )
        if allowance_micro > 0:
            secret = secrets.token_urlsafe(32)
            self._conn.execute(
                "INSERT INTO job_grants (job_id, grant_hash, root_receipt, allowance_receipt, account_id, "
                "mandate_digest, allowance_micro, max_depth, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                (ctx.job_id, _hash_secret(secret), ctx.node, allowance_receipt, account_id,
                 mandate_digest, int(allowance_micro), ctx.max_depth, now + TOKEN_TTL_S),
            )
            self._ensure_node(ctx.job_id, ctx.node, parent="", depth=0,
                              product_id=product_id, capability_id=capability_id, funded_by="own")
            self._conn.commit()
            ctx.grant_secret = secret
            ctx.allowance_receipt = allowance_receipt
            ctx.allowance_micro = int(allowance_micro)
        return ctx

    def _ensure_node(self, job_id: str, node: str, *, parent: str, depth: int, product_id: str,
                     capability_id: str, funded_by: str) -> None:
        self._conn.execute(
            "INSERT INTO job_nodes (receipt_id, job_id, parent_receipt, depth, product_id, capability_id, funded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (node, job_id, parent, depth, product_id, capability_id, funded_by),
        )
        # Committed here, not by a later statement of the caller: join() refuses right after
        # this on a finished parent, and on PostgreSQL an uncommitted write left the request's
        # connection "idle in transaction" — out of the pool and holding its locks for good.
        self._conn.commit()

    # children ---------------------------------------------------------------

    def join(self, *, token: str, grant_secret: str, product_id: str, capability_id: str,
             now: float | None = None) -> JobContext:
        """Admit a purchase made from inside a job (§6.1) and, with a grant, fund it (§6.2)."""
        now = time.time() if now is None else now
        claims = self.verify_token(token, now=now)
        job_id, parent = claims["job"], claims["node"]
        depth = int(claims.get("depth", 0)) + 1
        max_depth = min(int(claims.get("maxDepth", 1)), HUB_MAX_DEPTH)
        path = [str(p) for p in claims["path"]]
        if depth > max_depth:
            raise SubcontractError(403, "job_limit", f"this job allows subcontracting {max_depth} level(s) deep",
                                   limit="depth")
        if capability_id in path:
            raise SubcontractError(403, "job_limit", f"{capability_id} is already on this job's path — a cycle",
                                   limit="cycle")

        grant = None
        if grant_secret:
            grant = self._conn.execute(
                "SELECT * FROM job_grants WHERE grant_hash = ?", (_hash_secret(grant_secret),),
            ).fetchone()
            if grant is None or grant["job_id"] != job_id:
                raise SubcontractError(403, "job_invalid", "this grant does not belong to the job token's job")
            grant = dict(grant)
            if grant["status"] != "open" or float(grant["expires_at"]) < now:
                raise SubcontractError(402, "allowance_exhausted", "this job's allowance is closed")

        # The parent row exists already when the root opened a grant; for a linkage-only job
        # it is created by its first child, from the signed claims.
        if depth == 1:
            self._ensure_node(job_id, parent, parent="", depth=0, product_id="",
                              capability_id=path[-1] if path else "", funded_by="own")
        # A token outlives its call by up to the provider timeout. A provider that fires a
        # purchase after the call it was serving has returned must not graft it onto a
        # tree whose bill of materials and receipt are already out.
        parent_row = self._conn.execute(
            "SELECT status FROM job_nodes WHERE receipt_id = ? AND job_id = ?", (parent, job_id),
        ).fetchone()
        if parent_row is None:
            raise SubcontractError(403, "job_invalid", "the job token names a call this hub has no record of")
        if parent_row["status"] != "running":
            raise SubcontractError(403, "job_invalid", "the call this job token was issued to has finished")
        # The root is one of the job's nodes: children may take the other MAX - 1 slots.
        if not self._take(f"nodes:{job_id}", MAX_NODES_PER_JOB - 1):
            raise SubcontractError(403, "job_limit", f"a job holds at most {MAX_NODES_PER_JOB} calls", limit="nodes")
        if not self._take(f"children:{parent}", MAX_CHILDREN_PER_NODE):
            self._give(f"nodes:{job_id}")
            raise SubcontractError(403, "job_limit", f"one call may subcontract at most {MAX_CHILDREN_PER_NODE} times",
                                   limit="children")

        ctx = JobContext(
            job_id=job_id,
            node=f"node_{secrets.token_hex(12)}",
            depth=depth,
            max_depth=max_depth,
            path=path + [capability_id],
            product_id=product_id,
            parent=parent,
            funded_by="allowance" if grant else "own",
            grant_secret=grant_secret if grant else "",
            grant=grant,
        )
        # The read above only gives a precise refusal. The parent can finish between it and
        # the insert (a concurrent request closing the call), so the child is written in the
        # same transaction as a write that requires the parent still running: a no-op UPDATE
        # of the parent's row, which on PostgreSQL also holds the row lock until the child is
        # in, so finish_node waits for this join or this join sees the finish.
        with atomic(self._conn):
            running = returning_one(
                self._conn,
                "UPDATE job_nodes SET status = status WHERE receipt_id = ? AND job_id = ? "
                "AND status = 'running' RETURNING receipt_id",
                (parent, job_id),
            )
            if running is not None:
                self._conn.execute(
                    "INSERT INTO job_nodes (receipt_id, job_id, parent_receipt, depth, product_id, capability_id, "
                    "funded_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ctx.node, job_id, parent, depth, product_id, capability_id, ctx.funded_by),
                )
        if running is None:
            self._give(f"children:{parent}")
            self._give(f"nodes:{job_id}")
            raise SubcontractError(403, "job_invalid", "the call this job token was issued to has finished")
        return ctx

    def _take(self, counter: str, limit: int) -> bool:
        """One slot of a size limit, taken by a single conditional statement."""
        self._conn.execute("INSERT INTO job_counters (counter, n) VALUES (?, 0) ON CONFLICT DO NOTHING", (counter,))
        won = returning_one(
            self._conn,
            "UPDATE job_counters SET n = n + 1 WHERE counter = ? AND n < ? RETURNING n", (counter, limit),
            commit=True,
        )
        return won is not None

    def _give(self, counter: str) -> None:
        self._conn.execute("UPDATE job_counters SET n = n - 1 WHERE counter = ? AND n > 0", (counter,))
        self._conn.commit()

    # completion -------------------------------------------------------------

    def finish_node(self, node: str, *, status: str, amount_micro: int = 0, receipt_digest: str = "",
                    work_receipt_id: str = "") -> None:
        self._conn.execute(
            "UPDATE job_nodes SET status = ?, amount_micro = ?, receipt_digest = ?, work_receipt_id = ?, "
            "resolved_at = datetime('now') WHERE receipt_id = ? AND status = 'running'",
            (status, int(amount_micro), receipt_digest or "", work_receipt_id or "", node),
        )
        self._conn.commit()

    def finish_root(self, ctx: JobContext, *, product_id: str, capability_id: str, status: str,
                    amount_micro: int = 0, receipt_digest: str = "", work_receipt_id: str = "") -> None:
        """Close a root node, writing its row if no child ever did.

        A linkage-only root costs no row while it runs, but once its call has returned the
        hub must remember that it did: the provider still holds a valid token, and
        :meth:`join` refuses children of a finished node only if it can see the node.
        """
        self._ensure_node(ctx.job_id, ctx.node, parent="", depth=0, product_id=product_id,
                          capability_id=capability_id, funded_by="own")
        self.finish_node(ctx.node, status=status, amount_micro=amount_micro,
                         receipt_digest=receipt_digest, work_receipt_id=work_receipt_id)

    def abandon(self, ctx: JobContext) -> None:
        """Undo a :meth:`join` whose call was refused before it ran: the node never became a
        call, so it gives its slots back and is recorded as refused, not left running."""
        if ctx.is_root:
            return
        won = returning_one(
            self._conn,
            "UPDATE job_nodes SET status = 'refused', resolved_at = datetime('now') "
            "WHERE receipt_id = ? AND status = 'running' RETURNING receipt_id",
            (ctx.node,),
            commit=True,
        )
        if won is not None:
            self._give(f"nodes:{ctx.job_id}")
            self._give(f"children:{ctx.parent}")

    def settle_grant(self, job_id: str, *, spent_micro: int, released_micro: int) -> None:
        """Record how the allowance was settled, for GET /jobs/{id} (written once)."""
        self._conn.execute(
            "UPDATE job_grants SET spent_micro = ?, released_micro = ?, settled_at = datetime('now') "
            "WHERE job_id = ? AND settled_at = ''",
            (int(spent_micro), int(released_micro), job_id),
        )
        self._conn.commit()

    def close_grant(self, job_id: str) -> bool:
        """Close the allowance to new children. True when THIS call closed it."""
        won = returning_one(
            self._conn,
            "UPDATE job_grants SET status = 'closed', closed_at = datetime('now') "
            "WHERE job_id = ? AND status = 'open' RETURNING job_id",
            (job_id,),
            commit=True,
        )
        return won is not None

    def stale_grants(self, *, older_than: float, limit: int = 10) -> list[dict[str, Any]]:
        """Grants whose allowance is still held although the grant expired before ``older_than``."""
        rows = self._conn.execute(
            "SELECT g.job_id, g.allowance_receipt, g.allowance_micro, g.mandate_digest "
            "FROM job_grants g JOIN credit_holds h ON h.receipt_id = g.allowance_receipt "
            "WHERE h.status = 'held' AND g.expires_at < ? LIMIT ?",
            (older_than, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def child_parents(self, node: str) -> list[dict[str, str]]:
        """AWR/2 ``parents`` references for the children of ``node`` that delivered."""
        rows = self._conn.execute(
            "SELECT receipt_id, receipt_digest, work_receipt_id FROM job_nodes WHERE parent_receipt = ? "
            "AND status = 'captured' AND receipt_digest != '' ORDER BY created_at",
            (node,),
        ).fetchall()
        # AWR/2 §8.2 matches an edge to its document by `id`, so the edge names the child's
        # work receipt, not the hub's node. A row from before the receipt id was recorded
        # keeps a node URN: the digest still commits to the right bytes.
        return [{"id": r["work_receipt_id"] or f"urn:aimarket:job-node:{r['receipt_id']}",
                 "digestSRI": r["receipt_digest"]} for r in rows]

    def tree(self, job_id: str) -> dict[str, Any] | None:
        rows = self._conn.execute(
            "SELECT receipt_id, parent_receipt, depth, product_id, capability_id, funded_by, amount_micro, "
            "status, receipt_digest, work_receipt_id, created_at FROM job_nodes WHERE job_id = ? "
            "ORDER BY depth, created_at",
            (job_id,),
        ).fetchall()
        if not rows:
            return None
        grant = self._conn.execute(
            "SELECT allowance_micro, max_depth, status, spent_micro, released_micro, settled_at "
            "FROM job_grants WHERE job_id = ?", (job_id,),
        ).fetchone()
        nodes = [{
            "node": r["receipt_id"],
            "parent": r["parent_receipt"],
            "depth": int(r["depth"]),
            "product_id": r["product_id"],
            "capability_id": r["capability_id"],
            "price_usd": micro_to_usd(r["amount_micro"]),
            "funded_by": r["funded_by"],
            "status": r["status"],
            "receipt_digest": r["receipt_digest"] or None,
            "receipt_id": r["work_receipt_id"] or None,
        } for r in rows]
        # Every allowance-funded node, whatever its status: a node records what it actually
        # drew (finish), which is zero for a failure that was released — and not zero for
        # the one failure that still cost money (the peer delivered, the fee capture failed).
        from_allowance = sum(int(r["amount_micro"]) for r in rows if r["funded_by"] == "allowance")
        out: dict[str, Any] = {"job_id": job_id, "nodes": nodes, "spent_from_allowance_usd": micro_to_usd(from_allowance)}
        if grant is not None:
            out["allowance_usd"] = micro_to_usd(grant["allowance_micro"])
            out["max_depth"] = int(grant["max_depth"])
            out["allowance_status"] = grant["status"]
            if grant["settled_at"]:
                out["spent_usd"] = micro_to_usd(grant["spent_micro"])
                out["released_usd"] = micro_to_usd(grant["released_micro"])
        return out


class AllowanceCredits:
    """The credits ledger as a grant-funded child call sees it.

    A hold is carved out of the job's allowance instead of the buyer's balance; capture and
    release are the ledger's own (release returns the money to the allowance while it is
    open). The routing fee of a federated child is money the job spends too, so it is
    carved out of the allowance the same way.

    The call is paid from the ROOT buyer's account, but the caller is a subcontracting
    provider: every figure it could read back about that account (the 402's "balance", the
    answer's "remaining_balance") is the allowance that is left, never the buyer's balance.
    """

    def __init__(self, inner: Any, allowance_receipt: str):
        self._inner = inner
        self._allowance_receipt = allowance_receipt
        self.last_refusal: SubcontractError | None = None
        # How the child's holds resolved: "allowance" (back into the open allowance),
        # "balance" (the allowance had closed) or "" (not released). ``released_micro`` is
        # what went to the BALANCE, summed: a federated child resolves two holds through
        # this one proxy — its price and its routing fee — and when both come back after
        # the root closed, remembering only the last one gave back just the fee to the
        # root mandate's counters and left the price counted as spent forever.
        self.released_to = ""
        self.released_micro = 0
        # What this call actually took out of the allowance (price, routing fee, a
        # post-hoc fee debit). The job node records THIS, not the response's `price_usd`:
        # for a federated child the fee is carved from the allowance too, and a bill of
        # materials whose node prices do not add up to `spent_usd` is not a bill.
        self.captured_micro = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def allowance_left_usd(self) -> float:
        try:
            return float(self._inner.hold_amount_usd(self._allowance_receipt))
        except Exception:  # noqa: BLE001
            return 0.0

    def balance(self, account_id: str) -> float:
        return self.allowance_left_usd()

    def hold(self, account_id: str, amount_usd: float, receipt_id: str) -> dict[str, Any]:
        result = self._inner.transfer_hold(self._allowance_receipt, receipt_id, amount_usd)
        if result.get("error"):
            self.last_refusal = SubcontractError(
                402, "allowance_exhausted",
                f"the job's allowance is closed or cannot cover {amount_usd} USD",
                allowance_left_usd=self.allowance_left_usd(),
            )
            return {"error": self.last_refusal.detail}
        return {**result, "remaining_balance": result.get("allowance_left_usd", 0.0)}

    def release_hold(self, receipt_id: str) -> dict[str, Any]:
        result = self._inner.release_hold(receipt_id)
        if not result.get("error") and not result.get("already"):
            if result.get("returned_to"):
                self.released_to = self.released_to or "allowance"
            else:
                self.released_to = "balance"
                self.released_micro += usd_to_micro(result.get("released_usd") or 0.0)
        return {k: v for k, v in result.items() if k != "remaining_balance"}

    def capture_hold(self, receipt_id: str) -> dict[str, Any]:
        result = self._inner.capture_hold(receipt_id)
        if not result.get("error") and not result.get("already"):
            self.captured_micro += usd_to_micro(result.get("captured_usd") or 0.0)
        return {**{k: v for k, v in result.items() if k != "remaining_balance"},
                "remaining_balance": self.allowance_left_usd()}

    def debit(self, account_id: str, amount_usd: float, receipt_id: str = "", note: str = "",
              **kwargs: Any) -> dict[str, Any]:
        # A direct debit (the post-hoc routing fee) is carved out of the allowance and
        # captured at once, so it cannot reach past what the root buyer set aside.
        rid = receipt_id or f"route_{secrets.token_hex(8)}"
        held = self._inner.transfer_hold(self._allowance_receipt, rid, amount_usd)
        if held.get("error"):
            return held
        return self.capture_hold(rid)
