"""Who pays for one invoke, and under whose limits — the mandate and subcontracting layer.

``api.py``'s invoke handler already knows how to reserve, capture and release money on the
credits rail, on its local branch, its federated branch and for the routing fee. This module
decides, BEFORE that handler runs, whether the request is mandated (mandates.md §5), part
of a job (§6.1) or paid from a job's allowance (§6.2), and hands the handler two things:

* the funding account, when it is not the one an X-API-Key would name;
* a ledger to use instead of the plain credits ledger for this one request
  (:class:`~aimarket_hub.mandates.MandatedCredits` or
  :class:`~aimarket_hub.subcontract.AllowanceCredits`).

AFTER the handler, it closes what the request opened: the job node, the allowance and its
mandate reservation, and adds the bill of materials to the answer. Keeping this outside the
handler is deliberate — the handler is two thousand lines with a dozen exits, and a layer
that must run on every one of them belongs around it, not inside it.
"""
from __future__ import annotations

import contextlib
import json
import logging
import secrets
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi.responses import JSONResponse

from aimarket_hub import mandates
from aimarket_hub import subcontract
from aimarket_hub.mandates import Admission, MandateError
from aimarket_hub.subcontract import JobContext, SubcontractError

logger = logging.getLogger(__name__)

_X402_HEADERS = ("X-PAYMENT", "PAYMENT", "PAYMENT-SIGNATURE")


def grant_may_travel_to(invoke_url: str) -> bool:
    """Whether the job's grant may be sent to this provider URL.

    The grant is a bearer credential for the root buyer's allowance: whoever reads it can
    spend what is left of it until the job ends. It goes over TLS, or to a host the operator
    runs (loopback, a named invoke gateway), never in clear text across the internet. A
    plain-http provider elsewhere still gets the job token (linkage, no money) and pays for
    its own subcontractors.
    """
    from urllib.parse import urlparse

    from aimarket_hub.outbound_http import invoke_gateway_hosts, resolve_invoke_url

    target = urlparse(resolve_invoke_url(invoke_url or ""))
    host = (target.hostname or "").lower()
    return target.scheme == "https" or host in {"127.0.0.1", "localhost", "::1"} or host in set(invoke_gateway_hosts())


def _refusal(exc: MandateError | SubcontractError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.body())


@dataclass
class InvokeFunding:
    product_id: str
    capability_id: str
    admission: Admission | None = None
    job: JobContext | None = None
    account_id: str = ""
    allowance_receipt: str = ""
    allowance_micro: int = 0
    _wrap: Callable[[Any], Any] | None = None
    _proxies: list[Any] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.admission is not None or self.job is not None or bool(self.account_id)

    def wrap(self, ledger: Any) -> Any:
        if self._wrap is None or ledger is None:
            return ledger
        proxy = self._wrap(ledger)
        self._proxies.append(proxy)
        return proxy

    def provider_headers(self, jobs: subcontract.JobStore) -> dict[str, str]:
        """Headers for the provider the hub is about to execute LOCALLY (never a peer)."""
        if self.job is None:
            # Linkage for fixed-price subcontracting costs nothing while the call runs: no row
            # is written for a root until its first child joins (or it finishes). Every hop
            # pays for itself, so the depth is the hub's own limit, not a buyer's choice.
            self.job = jobs.open_root(product_id=self.product_id, capability_id=self.capability_id,
                                      max_depth=subcontract.HUB_MAX_DEPTH)
        headers = {
            subcontract.JOB_HEADER: jobs.issue_token(self.job),
            subcontract.HUB_HEADER: jobs.hub_origin,
        }
        if self.job.grant_secret:
            headers[subcontract.GRANT_HEADER] = self.job.grant_secret
        if self.admission is not None:
            headers.update(self.admission.provider_headers())
        return headers

    def receipt_parents(self, jobs: subcontract.JobStore) -> list[dict[str, str]]:
        if self.job is None:
            return []
        try:
            return jobs.child_parents(self.job.node)
        except Exception as exc:  # noqa: BLE001 - a receipt must not fail over its edges
            logger.error("subcontract: could not read child receipts of %s: %s", self.job.node, exc)
            return []

    def precise_status(self) -> int:
        """The HTTP status of that refusal: 402 for a limit, but e.g. 429 for a full approval
        queue (mandates.md §7)."""
        if self.admission is not None and self.admission.last_refusal is not None:
            return int(self.admission.last_refusal.status)
        return 402

    def precise_refusal(self) -> dict[str, Any] | None:
        """The §7 refusal a proxy produced, which the handler reported as a bare 402."""
        if self.admission is not None and self.admission.last_refusal is not None:
            return self.admission.last_refusal.body()
        for proxy in self._proxies:
            refusal = getattr(proxy, "last_refusal", None)
            if isinstance(refusal, SubcontractError):
                return refusal.body()
        return None


async def prepare(
    *,
    request: Any,
    body: Any,
    credits_ledger: Any,
    store: mandates.MandateStore,
    jobs: subcontract.JobStore,
    resolve_product: Callable[[str, str], str] | None = None,
    routing_fee_bps: int = 0,
) -> InvokeFunding | JSONResponse:
    """Everything that must be decided before the handler reserves a cent.

    ``resolve_product`` maps the request's (product_id, capability_id) to the product the hub
    will really execute. The handler falls back to a lookup by capability id alone, so a
    request's own product_id is whatever the caller typed — a per-product limit keyed on it
    could be dodged by sending a fresh product_id on every call. ``routing_fee_bps`` is the
    hub's fee on a routed call, which an owner approval (mandates.md §5.6) has to cover.
    """
    headers = request.headers
    digest = (headers.get(mandates.MANDATE_HEADER) or "").strip()
    proof = (headers.get(mandates.PROOF_HEADER) or "").strip()
    token = (headers.get(subcontract.JOB_HEADER) or "").strip()
    grant = (headers.get(subcontract.GRANT_HEADER) or "").strip()
    api_key = (headers.get("X-API-Key") or "").strip()
    other_rail = bool(
        headers.get("X-Payment-Channel")
        or any(headers.get(h) for h in _X402_HEADERS)
        or headers.get("X-AIMarket-Sandbox-Visitor")
    )
    product_id = body.product_id
    if resolve_product is not None:
        try:
            product_id = resolve_product(body.product_id, body.capability_id) or body.product_id
        except Exception:  # noqa: BLE001 - the handler answers an unknown capability itself
            product_id = body.product_id
    funding = InvokeFunding(product_id=product_id, capability_id=body.capability_id)
    wants_allowance = body.subcontract is not None

    api_account = ""
    if api_key and credits_ledger is not None:
        api_account = credits_ledger.resolve(api_key)

    try:
        if not (digest or token or grant or wants_allowance):
            if api_account and store.account_requires_mandate(api_account):
                raise MandateError(
                    402, "mandate_required",
                    "this account pays only for mandated calls: send X-AIMarket-Mandate",
                )
            return funding

        if (digest or grant or wants_allowance) and credits_ledger is None:
            raise MandateError(
                503, "mandates_unavailable",
                "mandates and subcontracting allowances are enforced on the credits rail, "
                "which is switched off on this hub",
            )
        if grant and not token:
            raise SubcontractError(403, "job_invalid", f"{subcontract.GRANT_HEADER} needs its {subcontract.JOB_HEADER}")
        if grant and (digest or api_key or other_rail):
            raise SubcontractError(
                403, "job_invalid",
                "a grant pays for this call from the job's allowance; send no other payment with it",
            )

        if digest:
            raw_body = await request.body()
            funding.admission = mandates.admit(
                store, digest=digest, proof_header=proof, method=request.method,
                path=mandates.signed_path(request), body=raw_body, capability_id=body.capability_id,
                product_id=product_id, api_key_account=api_account, other_rail=other_rail,
                source_hub=body.source_hub or "local", routing_fee_bps=routing_fee_bps,
            )
        elif api_account and not grant and store.account_requires_mandate(api_account):
            raise MandateError(
                402, "mandate_required",
                "this account pays only for mandated calls: send X-AIMarket-Mandate",
            )

        if token:
            if wants_allowance:
                raise SubcontractError(
                    400, "subcontract_unsupported",
                    "an allowance is set by the root call of a job; a subcontracted call "
                    "draws on that one",
                )
            funding.job = jobs.join(token=token, grant_secret=grant, product_id=body.product_id,
                                    capability_id=body.capability_id)

        admission = funding.admission
        if funding.job is not None and funding.job.funded_by == "allowance":
            grant_row = funding.job.grant or {}
            leaf_digest = str(grant_row.get("mandate_digest") or "")
            if leaf_digest:
                chain = store.chain(leaf_digest)
                if not mandates.scope_allows(chain[-1].scope, body.capability_id):
                    raise MandateError(403, "mandate_scope",
                                       f"{body.capability_id} is outside the root mandate's scope")
            funding.account_id = str(grant_row.get("account_id") or "")
            allowance_receipt = str(grant_row.get("allowance_receipt") or "")
            funding._wrap = lambda inner: subcontract.AllowanceCredits(inner, allowance_receipt)
        elif admission is not None:
            funding.account_id = admission.account_id
            funding._wrap = lambda inner: mandates.MandatedCredits(inner, admission)

        if wants_allowance:
            # Stranded allowances are swept by the hub's background task (api.py lifespan),
            # not here: a sweep retries failing releases, and on the request path that is a
            # stall every caller behind this one would share.
            await _open_allowance(funding, body=body, credits_ledger=credits_ledger,
                                  api_account=api_account, other_rail=other_rail, jobs=jobs)
    except (MandateError, SubcontractError) as exc:
        # An allowance reserved before the refusal must not stay frozen, and a child that
        # joined its job but will never run must not hold its slots or show as running.
        _undo(funding, credits_ledger=credits_ledger, store=store, jobs=jobs)
        return _refusal(exc)
    except Exception:
        _undo(funding, credits_ledger=credits_ledger, store=store, jobs=jobs)
        raise
    return funding


def _undo(funding: InvokeFunding, *, credits_ledger: Any, store: mandates.MandateStore,
          jobs: subcontract.JobStore) -> None:
    release(funding, credits_ledger=credits_ledger, store=store, jobs=jobs)
    if funding.job is not None and not funding.job.is_root:
        try:
            jobs.abandon(funding.job)
        except Exception as exc:  # noqa: BLE001
            logger.error("subcontract: abandoning node %s raised: %s", funding.job.node, exc)


async def _open_allowance(funding: InvokeFunding, *, body: Any, credits_ledger: Any,
                          api_account: str, other_rail: bool, jobs: subcontract.JobStore) -> None:
    block = body.subcontract
    if (body.source_hub or "local") != "local":
        raise SubcontractError(
            400, "subcontract_unsupported",
            "an allowance can only be passed through on a call this hub executes itself",
        )
    payer = funding.account_id or api_account
    if other_rail or not payer:
        raise SubcontractError(
            400, "subcontract_unsupported",
            "an allowance is reserved on the credits rail: pay this call with X-API-Key or a mandate",
        )
    allowance_usd = float(block.allowance_usd)
    if allowance_usd > subcontract.max_allowance_usd():
        raise SubcontractError(
            400, "subcontract_unsupported",
            f"this hub passes through at most {subcontract.max_allowance_usd()} USD per call",
        )
    from aimarket_hub.credits import usd_to_mc

    allowance_micro = usd_to_mc(allowance_usd) * 10   # what the ledger will actually hold
    max_depth = int(block.max_depth)
    admission = funding.admission
    if admission is not None:
        leaf = admission.leaf
        if leaf.subcontract is None:
            raise MandateError(403, "mandate_invalid", "this mandate does not allow subcontracting")
        if allowance_micro > leaf.subcontract["perCallAllowance"]:
            raise MandateError(402, "mandate_limit", "the allowance is over the mandate's perCallAllowance",
                               limit="subcontract.perCallAllowance", mandate=leaf.digest)
        if max_depth > leaf.subcontract["maxDepth"]:
            raise MandateError(403, "mandate_invalid", "max_depth is over the mandate's subcontract.maxDepth")
    receipt = f"alw_{secrets.token_hex(16)}"
    ledger = funding.wrap(credits_ledger)
    hold = getattr(ledger, "hold_allowance", None) or ledger.hold
    held = hold(payer, allowance_usd, receipt)
    if held.get("error"):
        refusal = funding.precise_refusal()
        if refusal is not None:
            raise MandateError(402, refusal.get("error", "mandate_limit"), refusal.get("detail", ""),
                               **{k: v for k, v in refusal.items()
                                  if k not in ("success", "error", "detail", "protocol_version")})
        raise SubcontractError(402, "payment_required", f"the allowance could not be reserved: {held['error']}")
    # Recorded before the job row is written, so a failure there still releases the hold.
    funding.allowance_receipt = receipt
    funding.allowance_micro = allowance_micro
    funding.account_id = payer
    funding.job = jobs.open_root(
        product_id=body.product_id, capability_id=body.capability_id,
        allowance_micro=allowance_micro, max_depth=max_depth, account_id=payer,
        allowance_receipt=receipt,
        mandate_digest=admission.leaf.digest if admission is not None else "",
    )


def _settle_allowance(*, receipt: str, allowance_micro: int, mandated: bool, credits_ledger: Any,
                      store: mandates.MandateStore) -> dict[str, Any] | None:
    """Release what is left of an allowance and settle its mandate reservation to what was
    drawn. None when this call did not settle it (a failure the sweeper will retry, or
    someone else already did)."""
    result = None
    for attempt in range(3):
        try:
            result = credits_ledger.release_hold(receipt)
            break
        except Exception as exc:  # noqa: BLE001 - "database is locked" is transient
            logger.error("subcontract: releasing allowance %s raised (try %d): %s", receipt, attempt + 1, exc)
            time.sleep(0.05 * (attempt + 1))
    if result is None or result.get("error") or result.get("already"):
        # Not ours to settle: it failed (the sweeper retries — the mandate hold stays
        # reserved, which errs toward refusing, never toward overspending) or it was
        # settled already.
        return None
    from aimarket_hub.credits import usd_to_mc

    released_micro = usd_to_mc(result.get("released_usd") or 0.0) * 10
    spent_micro = max(0, allowance_micro - released_micro)
    if mandated:
        try:
            store.settle(receipt, spent_micro)
        except Exception as exc:  # noqa: BLE001
            logger.error("mandates: settling allowance %s raised: %s", receipt, exc)
    return {"released_micro": released_micro, "spent_micro": spent_micro}


def release(funding: InvokeFunding, *, credits_ledger: Any, store: mandates.MandateStore,
            jobs: subcontract.JobStore) -> dict[str, Any]:
    """Close the allowance and settle its mandate reservation. Safe to call more than once."""
    out = {"released_micro": 0, "spent_micro": 0}
    if not funding.allowance_receipt or credits_ledger is None:
        return out
    job = funding.job
    if job is not None:
        try:
            jobs.close_grant(job.job_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("subcontract: closing grant of %s failed: %s", job.job_id, exc)
    settled = _settle_allowance(receipt=funding.allowance_receipt, allowance_micro=funding.allowance_micro,
                                mandated=funding.admission is not None, credits_ledger=credits_ledger, store=store)
    if settled is not None:
        out.update(settled)
        if job is not None:
            _record_settlement(jobs, job.job_id, settled)
    funding.allowance_receipt = ""
    return out


def _record_settlement(jobs: subcontract.JobStore, job_id: str, settled: dict[str, Any]) -> None:
    try:
        jobs.settle_grant(job_id, spent_micro=settled["spent_micro"], released_micro=settled["released_micro"])
    except Exception as exc:  # noqa: BLE001 - the money is settled; this is the report of it
        logger.error("subcontract: recording the settlement of %s raised: %s", job_id, exc)


def sweep_stale_allowances(*, credits_ledger: Any, store: mandates.MandateStore, jobs: subcontract.JobStore,
                           now: float | None = None, limit: int = 10) -> int:
    """Settle allowances whose root call ended without settling them (a crash, a release that
    kept failing). An allowance is only ever meant to live as long as its root call, so one
    still held well after its grant expired is money frozen in the buyer's account."""
    if credits_ledger is None:
        return 0
    settled = 0
    try:
        stale = jobs.stale_grants(older_than=(time.time() if now is None else now) - 300, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.error("subcontract: listing stale allowances raised: %s", exc)
        return 0
    for grant in stale:
        with contextlib.suppress(Exception):
            jobs.close_grant(grant["job_id"])
        result = _settle_allowance(receipt=grant["allowance_receipt"], allowance_micro=int(grant["allowance_micro"]),
                                   mandated=bool(grant["mandate_digest"]), credits_ledger=credits_ledger,
                                   store=store)
        if result is not None:
            _record_settlement(jobs, grant["job_id"], result)
            settled += 1
    return settled


def _micro_or_zero(value: Any) -> int:
    """A response's price as µUSD, or 0. The body can carry anything a hostile peer sent
    (``"price_usd": "lots"``); bookkeeping must never be what turns a delivered call into
    an error."""
    try:
        micro = subcontract.usd_to_micro(float(value or 0.0))
    except (TypeError, ValueError, OverflowError):
        return 0
    return micro if micro > 0 else 0


def _age_s(created_at: Any, now: float) -> float | None:
    """Seconds since ``created_at``, or None when it cannot be read (never swept then).

    The column is TEXT filled by the database: SQLite's datetime('now') is naive UTC, while
    PostgreSQL's NOW() as text carries the SESSION time zone's offset. Compared as strings
    against a UTC cutoff, a session west of UTC made a hold seconds old look hours old — the
    sweep released it mid-call and the capture then found nothing to take. Parsed here,
    with an offset honoured and a naive value read as UTC.
    """
    if isinstance(created_at, datetime):
        when = created_at
    else:
        try:
            when = datetime.fromisoformat(str(created_at or "").strip())
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return now - when.timestamp()


def sweep_stale_credit_holds(*, credits_ledger: Any, store: mandates.MandateStore,
                             now: float | None = None, limit: int = 50,
                             max_age_s: float = 3600.0) -> int:
    """Recover ordinary invokes abandoned for an hour, including their mandate budget.

    Allowances and their children have their own settlement accounting. Verification
    holds and appeal bonds belong to the verifier, however long its decision takes.
    A captured receipt keeps its mandate usage; an abandoned reservation gives it back.
    """
    if credits_ledger is None:
        return 0
    from aimarket_hub.channels import UNRESOLVED_SETTLEMENT_STATUSES

    now = time.time() if now is None else now
    conn = credits_ledger._conn
    marks = ",".join("?" for _ in UNRESOLVED_SETTLEMENT_STATUSES)
    rows = conn.execute(
        "SELECT receipt_id, created_at FROM credit_holds h WHERE status = 'held' "
        "AND parent_receipt_id = '' AND receipt_id NOT LIKE 'appeal_%' "
        "AND NOT EXISTS (SELECT 1 FROM job_grants g WHERE g.allowance_receipt = h.receipt_id) "
        f"AND NOT EXISTS (SELECT 1 FROM verified_settlements v WHERE v.nonce = h.receipt_id "
        f"AND v.status IN ({marks})) LIMIT ?",
        (*UNRESOLVED_SETTLEMENT_STATUSES, max(limit * 20, 500)),
    ).fetchall()
    stale = [r for r in rows if (age := _age_s(r["created_at"], now)) is not None and age > max_age_s]
    released = 0
    for row in stale[:limit]:
        result = credits_ledger.release_hold(row["receipt_id"])
        if not result.get("error") and result.get("already") in (None, "released"):
            store.settle(row["receipt_id"], 0)
            released += 1
    # A crash can occur before the credit hold exists or after it resolved but before
    # the mandate counters settled. Reconcile both without replaying the credit debit.
    orphaned = conn.execute(
        "SELECT DISTINCT m.receipt_id, m.created_at, h.status AS credit_status, h.amount_mc "
        "FROM mandate_holds m LEFT JOIN credit_holds h ON h.receipt_id = m.receipt_id "
        "WHERE m.status = 'held' "
        "AND (h.receipt_id IS NULL OR h.status IN ('captured', 'released')) "
        "AND NOT EXISTS (SELECT 1 FROM job_grants g WHERE g.allowance_receipt = m.receipt_id) LIMIT ?",
        (max(limit * 20, 500),),
    ).fetchall()
    for row in [r for r in orphaned if (age := _age_s(r["created_at"], now)) is not None and age > max_age_s][:limit]:
        store.settle(row["receipt_id"], int(row["amount_mc"] or 0) * 10 if row["credit_status"] == "captured" else 0)
    return released


def sweep_orphaned_child_holds(*, credits_ledger: Any, store: mandates.MandateStore,
                               now: float | None = None, limit: int = 50, max_age_s: float = 3600.0) -> int:
    """Release the holds of subcontracted calls that died before resolving them.

    A child's price is a hold carved out of its job's allowance. Its own request captures or
    releases it; a process that dies mid-call leaves it 'held'. The invoke sweep above skips
    children (they belong to an allowance) and the allowance sweep releases only the
    allowance, so until 2026-10-22 nothing ever released such a child: its price stayed frozen
    in the buyer's account. An hour is far past any provider timeout. A child released while
    its allowance is still held goes back into the allowance, which then settles as usual;
    once the allowance has settled the money goes to the balance, and the root mandate's
    counters get it back too (what :func:`finish` does for a child that fails late).
    Verification holds stay with their verifier, as above.
    """
    if credits_ledger is None:
        return 0
    from aimarket_hub.channels import UNRESOLVED_SETTLEMENT_STATUSES
    from aimarket_hub.credits import usd_to_mc

    now = time.time() if now is None else now
    conn = credits_ledger._conn
    marks = ",".join("?" for _ in UNRESOLVED_SETTLEMENT_STATUSES)
    rows = conn.execute(
        "SELECT h.receipt_id, h.created_at, h.parent_receipt_id, "
        "(SELECT g.mandate_digest FROM job_grants g WHERE g.allowance_receipt = h.parent_receipt_id) AS mandate_digest "
        "FROM credit_holds h WHERE h.status = 'held' AND h.parent_receipt_id != '' "
        "AND h.receipt_id NOT LIKE 'appeal_%' "
        f"AND NOT EXISTS (SELECT 1 FROM verified_settlements v WHERE v.nonce = h.receipt_id "
        f"AND v.status IN ({marks})) LIMIT ?",
        (*UNRESOLVED_SETTLEMENT_STATUSES, max(limit * 20, 500)),
    ).fetchall()
    stale = [r for r in rows if (age := _age_s(r["created_at"], now)) is not None and age > max_age_s]
    released = 0
    for row in stale[:limit]:
        result = credits_ledger.release_hold(row["receipt_id"])
        if result.get("error") or result.get("already"):
            continue
        released += 1
        if not result.get("returned_to") and row["mandate_digest"]:
            try:
                store.give_back(row["parent_receipt_id"], usd_to_mc(result.get("released_usd") or 0.0) * 10)
            except Exception as exc:  # noqa: BLE001 - the money is back; this is the counter
                logger.error("mandates: giving back orphaned child %s to %s raised: %s",
                             row["receipt_id"], row["parent_receipt_id"], exc)
    return released


def _body_of(result: Any) -> tuple[int, dict[str, Any] | None]:
    if isinstance(result, JSONResponse):
        try:
            return result.status_code, json.loads(bytes(result.body))
        except Exception:
            return result.status_code, None
    if isinstance(result, dict):
        return 200, result
    return getattr(result, "status_code", 500), None


def _with_body(result: Any, status: int, content: dict[str, Any]) -> Any:
    if isinstance(result, dict):
        return content
    headers = {k: v for k, v in result.headers.items() if k.lower() not in ("content-length", "content-type")}
    return JSONResponse(status_code=status, content=content, headers=headers)


def finish(funding: InvokeFunding, result: Any, *, credits_ledger: Any,
           store: mandates.MandateStore, jobs: subcontract.JobStore) -> Any:
    """Settle what :func:`prepare` opened and complete the answer. ``result`` is the
    handler's return value, or None when it raised."""
    status, content = _body_of(result) if result is not None else (500, None)
    if content is not None and not isinstance(content, dict):
        content = None
    delivered = status == 200 and bool((content or {}).get("success"))
    price_micro = _micro_or_zero((content or {}).get("price_usd")) if delivered else 0
    provenance = (content or {}).get("provenance_receipt")
    receipt_digest = str(provenance.get("digest_sri") or "") if isinstance(provenance, dict) else ""
    work_receipt_id = str(provenance.get("receipt_id") or "") if isinstance(provenance, dict) else ""

    release(funding, credits_ledger=credits_ledger, store=store, jobs=jobs)

    job = funding.job
    if job is not None:
        amount_micro = price_micro
        if job.funded_by == "allowance":
            # What the allowance really paid for this node, from the ledger's own captures —
            # not the response's `price_usd`. They differ for a federated child: its routing
            # fee is carved from the allowance too, and it is not in the price. They differ
            # again when the peer delivered and the fee capture then failed: the price was
            # taken for a call the hub reports as failed, and the bill has to show that money.
            amount_micro = sum(p.captured_micro for p in funding._proxies
                               if isinstance(p, subcontract.AllowanceCredits))
        outcome = "captured" if delivered else "failed"
        try:
            if job.is_root:
                jobs.finish_root(job, product_id=funding.product_id, capability_id=funding.capability_id,
                                 status=outcome, amount_micro=amount_micro, receipt_digest=receipt_digest,
                                 work_receipt_id=work_receipt_id)
            else:
                jobs.finish_node(job.node, status=outcome, amount_micro=amount_micro,
                                 receipt_digest=receipt_digest, work_receipt_id=work_receipt_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("subcontract: finishing node %s raised: %s", job.node, exc)
        if job.funded_by == "allowance" and (job.grant or {}).get("mandate_digest"):
            # A child that failed after its root closed is refunded to the buyer's balance,
            # not to the allowance — which the root already settled as spent. Take it back
            # off the root mandate's counters, or the limit over-counts forever.
            back = sum(p.released_micro for p in funding._proxies
                       if isinstance(p, subcontract.AllowanceCredits))
            if back:
                try:
                    store.give_back(job.grant["allowance_receipt"], back)
                except Exception as exc:  # noqa: BLE001
                    logger.error("mandates: giving back %s µUSD to %s raised: %s",
                                 back, job.grant["allowance_receipt"], exc)

    if result is None or content is None:
        return result

    changed = False
    if status == 402:
        refusal = funding.precise_refusal()
        if refusal is not None:
            return _with_body(result, funding.precise_status(), refusal)
    if job is not None and job.is_root:
        tree = None
        try:
            tree = jobs.tree(job.job_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("subcontract: reading job %s raised: %s", job.job_id, exc)
        if tree is not None:
            block = {
                "job_id": job.job_id,
                "nodes": [n for n in tree["nodes"] if n["node"] != job.node],
                "spent_from_allowance_usd": tree.get("spent_from_allowance_usd", 0.0),
            }
            if job.allowance_micro:
                # The handler read the balance while the allowance was still held; what is
                # left of it has been released since, so the figure it put in the answer
                # is low by exactly that much.
                if "remaining_balance" in content and funding.account_id and credits_ledger is not None:
                    with contextlib.suppress(Exception):
                        content["remaining_balance"] = credits_ledger.balance(funding.account_id)
                block["allowance_usd"] = subcontract.micro_to_usd(job.allowance_micro)
                # What the ledger settled, as recorded on the grant — the same figures
                # GET /jobs/{id} reports later. Unrecorded means not settled yet (the release
                # failed; the sweeper retries), which is not the same as "nothing spent".
                block["spent_usd"] = tree.get("spent_usd")
                block["released_usd"] = tree.get("released_usd")
            content["subcontracting"] = block
            changed = True
    if job is not None and not job.is_root:
        content["job"] = {"job_id": job.job_id, "node": job.node, "parent": job.parent,
                          "depth": job.depth, "funded_by": job.funded_by}
        changed = True
    if funding.admission is not None and delivered:
        content["mandate"] = funding.admission.summary()
        changed = True
    return _with_body(result, status, content) if changed else result
