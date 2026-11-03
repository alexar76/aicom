"""One immutable Studio graph, one root SKU, real buyer-signed child payments.

SUB/1 supplies job linkage. The funding authority is the signed transaction bundle,
not a credits grant. No wallet key is accepted, and unexecuted steps are not paid.
"""
from __future__ import annotations

import asyncio
import secrets
import contextlib
import base64
import hashlib
import json
import time
from dataclasses import asdict
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aimarket_hub import pipeline_payments, settle, subcontract
from aimarket_hub.db_backend import returning_one, atomic
from aimarket_hub import pipeline_leases
from aimarket_hub.models import Capability
from aimarket_hub.studio_paid import AdvanceRequest, PaidStudio, PreflightRequest, _json

PRODUCT = "hephaestus"
CAPABILITY = "pipeline.run@v1"
ZERO_WALLET = "0x" + "00" * 20


class PreparePipeline(BaseModel):
    gas_mode: Literal["buyer", "auto", "required"] = "buyer"
    wallet: str = Field(ZERO_WALLET, pattern=r"^0x[0-9a-fA-F]{40}$")


class PrepareGraph(PreflightRequest):
    gas_mode: Literal["buyer", "auto", "required"] = "buyer"
    wallet: str = Field(ZERO_WALLET, pattern=r"^0x[0-9a-fA-F]{40}$")


class PipelineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(..., pattern=r"^paid_[0-9a-f]{32}$")
    access_token: str = Field(..., min_length=20, max_length=128)
    transactions: dict[str, Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]+$", max_length=4098)]] | None = Field(None, max_length=16)

    authorizations: dict[str, Annotated[str, Field(pattern=r"^0x[0-9a-fA-F]{130}$")]] | None = Field(None, max_length=16)


def capability() -> Capability:
    return Capability(product_id=PRODUCT, capability_id=CAPABILITY,
        name="Run a preflighted capability graph", price_per_call_usd=0,
        description="One root invoke executes an immutable Studio graph. Children use buyer-signed "
                    "wallet payments, never a credit line. Preflight and prepare-pipeline first; "
                    "returns a SUB/1 job tree, final result and signed per-step bill.",
        input_schema=PipelineInput.model_json_schema(),
        output_schema={"type": "object", "properties": {
            "status": {"type": "string"}, "final_result": {"type": "object"},
            "bill_of_materials": {"type": "object"}}},
        agent="hephaestus", p50_latency_ms=30000)


class PipelineProvider:
    def __init__(self, studio: PaidStudio, jobs: subcontract.JobStore):
        self.studio, self.jobs, self.conn = studio, jobs, studio.conn
        self.broadcaster = pipeline_payments.broadcast
        from aimarket_hub.pipeline_relay import PipelineRelay
        self.relay = PipelineRelay(self.conn)

    def prepare(self, run_id: str, token: str, wallet: str, gas_mode: str = "buyer") -> dict:
        state, busy = self.studio.load(run_id, token)
        if busy or state["status"] != "quoted" or state.get("pipeline_job_id"):
            raise HTTPException(409, "only an unstarted quote can prepare a pipeline")
        if time.time() >= state["expires_at"]:
            raise HTTPException(409, "quote expired; run preflight again")
        sponsorship = self.relay.describe(state["steps"])
        sponsored = bool(state["total_units"] and gas_mode != "buyer" and sponsorship["enabled"])
        if state["total_units"] and gas_mode == "required" and not sponsored:
            raise HTTPException(409, sponsorship["reason"])
        if state.get("gas_sponsorship") is not None and state["gas_sponsorship"]["enabled"] != sponsored:
            raise HTTPException(409, "the prepared gas mode cannot change")
        sponsorship = {**sponsorship, "enabled": sponsored}
        wallet = wallet.lower()
        if state["total_units"]:
            if wallet == ZERO_WALLET:
                raise HTTPException(400, "paid steps need the buyer wallet")
            try:
                import eth_account.typed_transactions  # noqa: F401
            except ImportError as exc:
                raise HTTPException(503, "install aimarket-hub[escrow] to accept signed pipeline payments") from exc
        if state["wallet"] and state["wallet"] != wallet:
            raise HTTPException(409, "the prepared wallet cannot change")
        try:
            for step in state["steps"]:
                if self.studio.describe(step["node"], remote=step.get("remote")) != {"terms": step["terms"], "input_schema": step["input_schema"]}:
                    raise ValueError("listing terms changed; run preflight again")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        claim = returning_one(self.conn,
            "UPDATE studio_paid_runs SET busy = 1, started = 1 WHERE run_id = ? AND busy = 0 AND state_json = ? RETURNING run_id",
            (run_id, _json(state)), commit=True)
        if not claim:
            raise HTTPException(409, "run changed; reload it")
        try:
            state["executor"], state["wallet"] = CAPABILITY, wallet
            state["gas_sponsorship"] = sponsorship
            offers = []
            for step in state["steps"]:
                terms = step["terms"]
                if not terms:
                    continue
                if not step.get("invoice") and step.get("remote"):
                    step["invoice"] = step["remote"]["offer"]["invoice"]
                if not step.get("invoice"):
                    secret = settle.mint_secret()
                    step["invoice"] = self.studio.invoices.mint(nonce=settle.nonce_for_secret(secret),
                        capability_id=step["node"]["capability_id"], pay_to=terms["pay_to"],
                        amount_units=terms["amount_units"], ttl_s=settle.invoice_ttl_s(), secret=secret)
                    step["invoice"]["secret"] = secret
                offer = self.studio.public_step(step)
                offer["authorization"] = pipeline_payments.authorization_data(step, wallet)
                offers.append(offer)
            self.studio.save(state, unlock=True)
        except BaseException:
            self.studio.save(state, unlock=True)
            raise
        return {"run_id": run_id, "graph_digest": state["graph_digest"], "wallet": wallet,
                "budget_units": str(state["total_units"]), "expires_at": state["expires_at"],
                "offers": offers, "gas_sponsorship": sponsorship, "executor": {"product_id": PRODUCT, "capability_id": CAPABILITY,
                                             "source_hub": "local"}}

    def resumable(self, state, row):
        # Only the explicit durable peer protocol is safe after an uncertain dispatch.
        step = next((s for s in state['steps'] if s['status'] != 'succeeded'), None)
        return bool(row and row['busy'] and time.time() - row['updated_at'] > pipeline_leases.TTL
                    and step and (step['status'] in ('payment_pending', 'relay_pending')
                                  or (step.get('remote') and step.get('job')
                                      and step['status'] in ('running', 'remote_pending')))
                    and state['status'] in ('active', 'reconciliation_required'))

    async def heartbeat(self, run_id, lease):
        while True:
            await asyncio.sleep(30)
            self.conn.execute('UPDATE studio_pipeline_invocations SET updated_at = ? WHERE run_id = ? AND lease_token = ? AND busy = 1',
                              (time.time(), run_id, lease))
            self.conn.commit()

    def status(self, run_id: str, token: str) -> dict:
        """Read-only: never broadcast, dispatch or renew a payment."""
        state, busy = self.studio.load(run_id, token)
        row = self._row(run_id)
        if row and row["response_json"]:
            return json.loads(row["response_json"])
        resumable = self.resumable(state, row)
        answer = self._response(state, busy=False if resumable else busy or bool(row and row["busy"]))
        uncertain = state["status"] == "reconciliation_required" or bool(row and row["busy"] and time.time() - row["updated_at"] > 180)
        answer["recovery"] = {
            "action": "resume_same_run" if resumable else "contact_operator" if uncertain else "wait" if answer["busy"] else "resume_same_run",
            "status_url": f"/studio/paid-runs/{run_id}/pipeline",
            "replacement_payment_allowed": False,
            "detail": "An uncertain provider dispatch must be reconciled from its receipt; do not buy it again."
                      if answer["busy"] or state["status"] == "reconciliation_required" else "Resume with the original signed bundle.",
        }
        return answer

    def _row(self, run_id: str):
        return self.conn.execute("SELECT * FROM studio_pipeline_invocations WHERE run_id = ?", (run_id,)).fetchone()

    def _response(self, state: dict, *, busy: bool = False) -> dict:
        view = self.studio.view(state, busy)
        job_id = state.get("pipeline_job_id")
        return {**view, "success": state["status"] == "completed", "price_usd": 0,
                "product_id": PRODUCT, "capability_id": CAPABILITY,
                "result": {"status": state["status"], "final_result": view["final_result"],
                           "bill_of_materials": view["bill_of_materials"]},
                "subcontracting": {"job_id": job_id, "funding": "buyer_wallet",
                    "nodes": (self.jobs.tree(job_id) or {}).get("nodes", []) if job_id else [],
                    "budget_usd": view["bill_of_materials"]["budget_usd"],
                    "spent_usd": view["bill_of_materials"]["total_usd"],
                    "unspent_budget_usd": view["bill_of_materials"]["remaining_budget_usd"]},
                "protocol_version": "v2"}

    async def invoke(self, body: PipelineInput, caller: str) -> dict:
        if body.transactions is not None and body.authorizations is not None:
            raise HTTPException(400, "choose transactions or authorizations, not both")
        lease = secrets.token_hex(16)
        state, step_busy = self.studio.load(body.run_id, body.access_token)
        row = self._row(body.run_id)
        sponsored = bool(state.get("gas_sponsorship", {}).get("enabled"))
        if sponsored and body.transactions is not None or not sponsored and body.authorizations is not None:
            raise HTTPException(400, "payment bundle differs from the prepared gas mode")
        if row:
            if body.authorizations is not None:
                original = {s["node"]["id"]: s["relay_authorization"] for s in state["steps"] if s.get("relay_authorization")}
                if {k: v.lower() for k, v in body.authorizations.items()} != original:
                    raise HTTPException(409, "this run already has its immutable authorization bundle")
            if body.transactions is not None:
                original = {s["node"]["id"]: s["signed_payment"]["raw"] for s in state["steps"] if s.get("signed_payment")}
                if {k: v.lower() for k, v in body.transactions.items()} != original:
                    raise HTTPException(409, "this run already has its immutable signed payment bundle")
            if row["response_json"]:
                return json.loads(row["response_json"])
            resumable = self.resumable(state, row)
            if (row['busy'] or step_busy) and not resumable:
                return self._response(state, busy=True)
            ctx = subcontract.JobContext(**json.loads(row['context_json']))
            with atomic(self.conn):
                claimed = returning_one(self.conn,
                    "UPDATE studio_pipeline_invocations SET busy = 1, updated_at = ?, lease_token = ? "
                    "WHERE run_id = ? AND lease_token = ? AND updated_at = ? AND response_json = '' RETURNING run_id",
                    (time.time(), lease, body.run_id, row['lease_token'], row['updated_at']))
                if claimed and resumable:
                    # This operation's immutable request can safely be recovered by GET.
                    state['status'] = 'active'
                    self.conn.execute('UPDATE studio_paid_runs SET busy = 0, state_json = ? WHERE run_id = ?',
                                      (_json(state), body.run_id))
            if not claimed:
                fresh, _ = self.studio.load(body.run_id, body.access_token)
                return self._response(fresh, busy=True)
        else:
            original_state = _json(state)
            if step_busy or state["status"] != "quoted" or state.get("executor") != CAPABILITY:
                raise HTTPException(409, "prepare-pipeline before invoking this SKU")
            if time.time() >= state["expires_at"]:
                raise HTTPException(409, "quote expired; run preflight again")
            payments = (body.authorizations if sponsored else body.transactions) or {}
            paid_steps = [s for s in state["steps"] if s["terms"]]
            if set(payments) != {s["node"]["id"] for s in paid_steps}:
                raise HTTPException(400, "provide exactly one payment signature for every paid step")
            nonces = []
            try:
                for step in paid_steps:
                    if time.time() + 10 >= step["invoice"]["expires_at"]:
                        raise ValueError("payment offer expired; prepare a fresh quote")
                    if sponsored:
                        signature = payments[step["node"]["id"]].lower()
                        pipeline_payments.validate_authorization(step, state["wallet"], signature)
                        step["relay_authorization"] = signature
                        continue
                    validated = pipeline_payments.validate_transaction(step, state["wallet"], payments[step["node"]["id"]])
                    step["signed_payment"] = validated
                    nonces.append(validated["nonce"])
                if nonces and nonces != list(range(nonces[0], nonces[0] + len(nonces))):
                    raise ValueError("payment transaction nonces must be consecutive in graph order")
            except (ValueError, TypeError) as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx = self.jobs.open_root(product_id=PRODUCT, capability_id=CAPABILITY,
                                      max_depth=subcontract.HUB_MAX_DEPTH)
            with atomic(self.conn):
                claimed = returning_one(self.conn,
                    "UPDATE studio_paid_runs SET busy = 1, started = 1 WHERE run_id = ? AND busy = 0 AND state_json = ? RETURNING run_id",
                    (body.run_id, original_state))
                if not claimed:
                    raise HTTPException(409, "run changed; reload it")
                self.conn.execute(
                    "INSERT INTO studio_pipeline_invocations (run_id, context_json, updated_at, lease_token) VALUES (?, ?, ?, ?)",
                    (body.run_id, _json(asdict(ctx)), time.time(), lease))
                self.jobs._ensure_node(ctx.job_id, ctx.node, parent="", depth=0,
                    product_id=PRODUCT, capability_id=CAPABILITY, funded_by="own")
                state['pipeline_job_id'] = ctx.job_id
                self.conn.execute('UPDATE studio_paid_runs SET state_json = ?, busy = 0, updated_at = ? WHERE run_id = ?',
                                  (_json(state), time.time(), body.run_id))
        lease_context = pipeline_leases.current.set((body.run_id, lease))
        heartbeat = asyncio.create_task(self.heartbeat(body.run_id, lease))
        try:
            # Bounded HTTP work: after one unconfirmed transfer, return 202. A retry
            # resumes this SAME root and transaction; completed roots return the cache.
            while state["status"] not in ("completed", "failed"):
                step = next(s for s in state["steps"] if s["status"] != "succeeded")
                await self.studio.advance(body.run_id, body.access_token,
                    AdvanceRequest(step_id=step["node"]["id"], wallet=state["wallet"]), caller,
                    managed=True, job_headers=lambda: {subcontract.JOB_HEADER: self.jobs.issue_token(ctx)},
                    broadcaster=self.broadcaster, relay=self.relay)
                pipeline_leases.check(self.conn, body.run_id)
                state, step_busy = self.studio.load(body.run_id, body.access_token)
                if step_busy or any(s["status"] in ("payment_pending", "remote_pending", "relay_pending") for s in state["steps"]):
                    break
            terminal = state["status"] in ("completed", "failed")
            if terminal:
                # The standard invoke tree describes delivered work. The real-money
                # bill must also account for an external payment when delivery failed.
                for step in state["steps"]:
                    child = (step.get("job") or {}).get("node")
                    if child and step.get("payment"):
                        public = self.studio.public_step(step)
                        micro = int(Decimal(str(public["price_usd"])) * 1_000_000)
                        self.conn.execute("UPDATE job_nodes SET amount_micro = ? WHERE receipt_id = ? AND job_id = ?",
                                          (micro, child, ctx.job_id))
                self.conn.commit()
                answer = self._response(state)
                bill = answer["bill_of_materials"]
                receipt = {"kind": "pipeline.run/1", "run_id": body.run_id, "job_id": ctx.job_id,
                    "product_id": PRODUCT, "capability_id": CAPABILITY, "graph_digest": state["graph_digest"],
                    "success": state["status"] == "completed", "parents": self.jobs.child_parents(ctx.node),
                    "result_digest": hashlib.sha256(_json(answer["result"]).encode()).hexdigest(),
                    "bill_digest": hashlib.sha256(_json(bill).encode()).hexdigest()}
                receipt["signature"] = self.studio.signer.sign_object(receipt)
                digest = "sha256-" + base64.b64encode(hashlib.sha256(_json(receipt).encode()).digest()).decode()
                self.jobs.finish_root(ctx, product_id=PRODUCT, capability_id=CAPABILITY,
                    status="captured" if receipt["success"] else "failed", receipt_digest=digest,
                    work_receipt_id=f"urn:aimarket:pipeline:{body.run_id}")
                answer["receipt"] = receipt
                answer["subcontracting"]["nodes"] = self.jobs.tree(ctx.job_id)["nodes"]
                self.conn.execute("UPDATE studio_pipeline_invocations SET response_json = ? WHERE run_id = ?",
                                  (_json(answer), body.run_id))
                self.conn.commit()
            else:
                answer = self._response(state, busy=step_busy)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            pipeline_leases.current.reset(lease_context)
        self.conn.execute("UPDATE studio_pipeline_invocations SET busy = 0, updated_at = ? WHERE run_id = ? AND lease_token = ?",
                          (time.time(), body.run_id, lease))
        self.conn.commit()
        return answer


def attach_prepare_route(app, provider: PipelineProvider, *, caller, allow_request):
    @app.get("/studio/paid-runs/{run_id}/pipeline")
    async def pipeline_status(run_id: str, request: Request, x_studio_run_token: str = Header(default="")):
        if not allow_request("studio-status:" + caller(request)):
            raise HTTPException(429, "slow down", headers={"Retry-After": "2"})
        return JSONResponse(provider.status(run_id, x_studio_run_token), headers={"Cache-Control": "no-store"})

    @app.post("/studio/prepare-pipeline")
    async def prepare_graph(body: PrepareGraph, request: Request):
        if not allow_request("studio:" + caller(request)):
            raise HTTPException(429, "slow down")
        quote = await provider.studio.preflight_external(body)
        if quote["ready"]:
            prepared = provider.prepare(quote["run_id"], quote["access_token"], body.wallet, body.gas_mode)
            quote.update(prepared)
            quote["signer_public_key"] = provider.studio.signer.public_key_b64
            quote["signature"] = provider.studio.signer.sign_object(quote)
        return JSONResponse(quote, headers={"Cache-Control": "no-store"})

    @app.post("/studio/paid-runs/{run_id}/prepare-pipeline")
    async def prepare(run_id: str, body: PreparePipeline,
                      x_studio_run_token: str = Header(default="")):
        answer = provider.prepare(run_id, x_studio_run_token, body.wallet, body.gas_mode)
        return JSONResponse(answer, headers={"Cache-Control": "no-store"})
