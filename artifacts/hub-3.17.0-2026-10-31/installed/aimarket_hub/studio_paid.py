"""Wallet-funded Studio runs, separate from the existing trial forwarder.

The hub holds no buyer key or cash. A quote pins the graph and payment terms; the
browser signs and broadcasts one EIP-3009 payment at a time. Only a chain-verified
payment admits a priced step. Persistent single-winner claims prevent retrying a
provider after a lost response. An interrupted dispatch requires reconciliation,
never an automatic second purchase. All money is counted in token base units.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import hmac
import json
import math
import re
import secrets
import time
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Callable

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, Field
from referencing import Registry
from referencing.exceptions import Unresolvable

from aimarket_hub import settle, x402
from aimarket_hub.api_models import StudioNode
from aimarket_hub.db_backend import returning_one
from aimarket_hub.pipeline_references import references_in, resolve, validate_graph

QUOTE_TTL = int(os.environ.get("AIMARKET_STUDIO_QUOTE_TTL_S", "900"))  # until the run starts


class PreflightRequest(BaseModel):
    nodes: list[StudioNode] = Field(..., min_length=1, max_length=16)
    max_budget_usd: float | None = Field(None, ge=0, le=100_000, allow_inf_nan=False)


class AdvanceRequest(BaseModel):
    step_id: str = Field(..., min_length=1, max_length=64)
    wallet: str = Field(..., pattern=r"^0x[0-9a-fA-F]{40}$")
    tx_hash: str | None = Field(None, pattern=r"^0x[0-9a-fA-F]{64}$")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def result_sha256(result: Any) -> str:
    """SHA-256 of UTF-8 sorted, compact, ASCII-escaped JSON (non-finite refused).

    Same result commitment as the trial executor; unlike object signatures, this
    digest includes every field of the result, including a nested signature.
    """
    return hashlib.sha256(_json(result).encode("utf-8")).hexdigest()


def ordered_graph(nodes: list[dict]) -> list[dict]:
    nodes = [{**n, "id": n.get("id") or f"n{i}", "source_hub": n.get("source_hub") or "local"}
             for i, n in enumerate(nodes)]
    known = {n["id"] for n in nodes}
    if len(known) != len(nodes):
        raise ValueError("duplicate step ids")
    for n in nodes:
        if not re.fullmatch(r"[^{}\s.]+", n["id"]):
            raise ValueError("step ids cannot contain dots, braces or whitespace")
        if not set(n.get("depends_on") or []) <= known:
            raise ValueError(f"{n['id']}: unknown dependency")
    # input_from follows the same dependency contract as field references.
    problems = validate_graph([{**n, "input": {"fields": n.get("input", {}),
        **({"context": "${" + n["input_from"] + "}"} if n.get("input_from") else {})}} for n in nodes])
    if problems:
        raise ValueError("; ".join(problems))
    done: set[str] = set()
    ordered = []
    while len(done) < len(nodes):
        ready = [n for n in nodes if n["id"] not in done and set(n.get("depends_on") or []) <= done]
        if not ready:
            raise ValueError("the graph contains a cycle")
        for n in ready:
            source = n.get("input_from")
            if source and source not in done:
                raise ValueError(f"{n['id']}: input_from must name an earlier dependency")
            ordered.append(n)
            done.add(n["id"])
    return ordered


def check_input(value: dict, schema: dict, *, dynamic: bool) -> None:
    Draft202012Validator.check_schema(schema)
    try:
        # Catalogue schemas are untrusted. Resolve embedded definitions only; never
        # let validation fetch a remote $ref (including internal network addresses).
        for error in Draft202012Validator(schema, registry=Registry()).iter_errors(value):
            # A typed field supplied by an upstream output is checked after resolution.
            if dynamic and references_in(error.instance) and error.validator not in {
                "required", "additionalProperties", "minProperties", "maxProperties", "propertyNames",
            }:
                continue
            raise ValueError(error.message[:300])
    except Unresolvable as exc:
        raise ValueError("input schema has an unresolved reference; embed its definitions") from exc


def blocker_code(detail: str) -> str:
    if "peer bills independently" in detail or "separate routing-fee" in detail:
        return "settlement_route_unsupported"
    if "budget" in detail:
        return "service_budget_exceeded"
    if "unavailable" in detail or "stale" in detail:
        return "route_unavailable"
    if "one chain" in detail:
        return "mixed_assets_unsupported"
    return "invalid_graph_or_terms"


class PaidStudio:
    def __init__(self, *, db, config, signer, invoke: Callable, route_ok: Callable):
        self.db, self.config, self.signer = db, config, signer
        self.conn = db._conn
        self.invoke, self.route_ok = invoke, route_ok
        self.invoices = settle.InvoiceStore(self.conn)
        self._bill_signatures: dict[str, str] = {}  # bill digest -> signature (insertion-ordered, bounded)
        self.remote = None
        self.jobs = None

    def describe(self, node: dict, *, remote=None, validate_input=True) -> dict:
        if node["capability_id"] == "pipeline.run@v1":
            raise ValueError("a pipeline cannot recursively purchase pipeline.run@v1")
        cap = self.db.get_capability(node["product_id"], node["capability_id"], node["source_hub"])
        if cap is None or not self.route_ok(cap):
            raise ValueError("listing unavailable or route stale")
        price = cap.price_per_call_usd
        if price is None or not math.isfinite(float(price)) or float(price) < 0:
            raise ValueError("listing has no valid price")
        if remote is not None:
            if self.remote is None:
                raise ValueError("independent seller adapter unavailable")
            return self.remote.validate(node, remote)
        terms = None
        if price > 0:
            if not (x402.enabled() and x402.accept_enabled() and settle.rpc_urls()):
                raise ValueError("seller-direct payment verification is unavailable on this hub")
            source = node["source_hub"]
            if source != "local":
                sells = self.config.sells_on_behalf_of(source)
                resells = bool(self.config.peer_api_key(source))
                if not (sells or resells):
                    raise ValueError("peer bills independently; no supported seller-direct settlement route")
                if not sells and self.config.routing_fee_bps > 0:
                    raise ValueError("this peer requires a separate routing-fee rail")
            payment = settle.terms_for(cap, operator_pay_to=x402.recipient())
            if payment is None:
                raise ValueError("listing has no supported seller payout or token")
            if (not settle.is_address(payment.token_contract) or payment.chain_id <= 0
                    or not 0 <= payment.decimals <= 36 or payment.amount_units <= 0):
                raise ValueError("listing has invalid payment token, chain or quantity")
            terms = asdict(payment)
        schema = cap.input_schema or {}
        if isinstance(schema, str):
            schema = json.loads(schema)
        value = dict(node.get("input") or {})
        if node.get("input_from"):
            value.setdefault("context", "${" + node["input_from"] + "}")
        if validate_input:
            check_input(value, schema, dynamic=True)
        return {"terms": terms, "input_schema": schema}

    async def preflight_external(self, body: PreflightRequest) -> dict:
        if self.remote is None:
            return self.preflight(body)
        try:
            nodes = ordered_graph([n.model_dump(exclude_none=True) for n in body.nodes])
        except ValueError:
            return self.preflight(body)
        prepared = {}
        for node in nodes:
            source = node['source_hub']
            cap = self.db.get_capability(node['product_id'], node['capability_id'], source)
            if (source != 'local' and cap is not None and cap.price_per_call_usd > 0
                    and not self.config.sells_on_behalf_of(source) and not self.config.peer_api_key(source)):
                if not self.route_ok(cap):
                    continue
                try:
                    remote = await self.remote.prepare(node, getattr(body, 'wallet', '0x' + '00' * 20))
                    description = self.describe(node, remote=remote)
                    value = dict(node.get('input') or {})
                    if node.get('input_from'):
                        value.setdefault('context', '${' + node['input_from'] + '}')
                    check_input(value, description['input_schema'], dynamic=True)
                    prepared[node['id']] = {**description, 'remote': remote}
                except Exception as exc:
                    return {'ready': False, 'blockers': [{'id': node['id'], 'code': 'settlement_route_unsupported',
                        'detail': 'Independent seller preparation failed: ' + str(exc)[:200]}], 'steps': []}
        return self.preflight(body, prepared=prepared)

    def preflight(self, body: PreflightRequest, *, prepared=None) -> dict:
        try:
            nodes = ordered_graph([n.model_dump(exclude_none=True) for n in body.nodes])
        except ValueError as exc:
            return {"ready": False, "blockers": [{"code": blocker_code(str(exc)), "detail": str(exc)}], "steps": []}
        steps, blockers = [], []
        for node in nodes:
            try:
                description = (prepared or {}).get(node['id']) or self.describe(node)
                steps.append({"node": node, **description, "status": "queued"})
            except (ValueError, SchemaError) as exc:
                blockers.append({"id": node["id"], "capability_id": node["capability_id"], "code": blocker_code(str(exc)), "detail": str(exc)[:500]})
        assets = {(s["terms"]["chain_id"], s["terms"]["token_contract"].lower(), s["terms"]["decimals"])
                  for s in steps if s["terms"]}
        if len(assets) > 1:
            blockers.append({"code": "mixed_assets_unsupported", "detail": "a funded run must use one chain and one token"})
        total = sum(s["terms"]["amount_units"] for s in steps if s["terms"])
        decimals = next(iter(assets))[2] if assets else 6
        total_usd = float(Decimal(total) / 10 ** decimals)
        if body.max_budget_usd is not None and Decimal(str(body.max_budget_usd)) * 10 ** decimals < total:
            blockers.append({"code": "service_budget_exceeded", "detail": "the graph exceeds the requested budget"})
        result = {"ready": not blockers, "blockers": blockers, "total_usd": total_usd,
                  "total_units": str(total), "steps": [self.public_step(s) for s in steps]}
        if blockers:
            return result
        run_id, token = "paid_" + secrets.token_hex(16), secrets.token_urlsafe(32)
        now = time.time()
        state = {"run_id": run_id, "status": "quoted", "steps": steps, "results": {},
                 "total_units": total, "decimals": decimals, "wallet": "", "created_at": now,
                 "expires_at": now + QUOTE_TTL, "graph_digest": hashlib.sha256(_json(nodes).encode()).hexdigest()}
        # Anyone may ask for a quote, and every quote is a row: a quote nobody ever started is
        # dropped an hour after it expired, so preflight is not an unbounded disk-growth path.
        # A run that was advanced, claimed or saved even once is kept (started = 1).
        self.conn.execute("DELETE FROM studio_paid_runs WHERE started = 0 AND expires_at < ?", (now - 3600,))
        self.conn.execute(
            "INSERT INTO studio_paid_runs (run_id, token_hash, state_json, updated_at, expires_at, started) VALUES (?, ?, ?, ?, ?, 0)",
            (run_id, hashlib.sha256(token.encode()).hexdigest(), _json(state), now, state["expires_at"]),
        )
        self.conn.commit()
        return {**result, "run_id": run_id, "access_token": token, "expires_at": state["expires_at"],
                "graph_digest": state["graph_digest"]}

    def load(self, run_id: str, token: str) -> tuple[dict, bool]:
        row = self.conn.execute("SELECT * FROM studio_paid_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(404, "run not found")
        return json.loads(row["state_json"]), bool(row["busy"])

    def save(self, state: dict, *, unlock: bool = False) -> None:
        from aimarket_hub.pipeline_leases import current, LeaseLost
        lease = current.get()
        condition, args = '', []
        if lease and lease[0] == state['run_id']:
            condition = ' AND EXISTS (SELECT 1 FROM studio_pipeline_invocations WHERE run_id = ? AND lease_token = ?)'
            args = list(lease)
        saved = returning_one(self.conn,
            "UPDATE studio_paid_runs SET state_json = ?, updated_at = ?, busy = ?, started = 1 WHERE run_id = ?" + condition + " RETURNING run_id",
            (_json(state), time.time(), 0 if unlock else 1, state["run_id"], *args), commit=True)
        if not saved:
            raise LeaseLost('Pipeline execution transferred to another worker')

    @staticmethod
    def public_step(step: dict) -> dict:
        node, terms = step["node"], step["terms"]
        out = {k: node[k] for k in ("id", "product_id", "capability_id", "source_hub")}
        out.update({"status": step["status"], "quoted_usd": float(Decimal(terms["amount_units"]) / 10 ** terms["decimals"]) if terms else 0,
                    "payment_rail": "seller_direct" if terms else "free", "terms": terms})
        for key in ("success", "status_code", "error", "receipt", "result_sha256", "job", "tx_hash", "payment", "started_at", "finished_at"):
            if key in step:
                out[key] = ({k: v for k, v in step[key].items() if k != "grant_secret"}
                            if key == "job" and isinstance(step[key], dict) else step[key])
        # Decimal quantities travel as strings: JS numbers cannot carry uint256 values.
        if terms:
            out["terms"] = {**terms, **{k: str(terms[k]) for k in ("amount_units", "seller_units", "fee_units")}}
        if step.get("remote"):
            out["payment_rail"] = "independent_seller"
            out["seller_operation"] = step["remote"]["offer"]
        if step.get("invoice") and not step.get("payment"):
            out["invoice"] = {k: step["invoice"][k] for k in ("nonce", "expires_at")}
        if step.get("signed_payment", {}).get("sponsored"):
            out["gas_sponsorship"] = {"gas_payer": step["signed_payment"]["gas_payer"], "buyer_fee_units": "0"}
        paid = step.get("payment") or {}
        if paid:
            out["payment"] = {**paid, **{k: str(paid[k]) for k in ("paid_units", "fee_units") if k in paid}}
        out["price_usd"] = float(Decimal(int(paid.get("paid_units", 0)) + int(paid.get("fee_units", 0))) /
                                  10 ** (terms["decimals"] if terms else 6))
        return out

    def view(self, state: dict, busy: bool = False) -> dict:
        steps = [self.public_step(s) for s in state["steps"]]
        # The token-gated run response may return source data. Public signed bills
        # carry only its digest; never copy these results into ``steps`` or ``bill``.
        step_results = {}
        for step in state["steps"]:
            nid = step["node"]["id"]
            if "response_result" in step or nid in state.get("results", {}):
                evidence = {"result": step.get("response_result", state["results"].get(nid))}
                if step.get("receipt") is not None:
                    evidence["receipt"] = step["receipt"]
                step_results[nid] = evidence
        paid = sum(int((s.get("payment") or {}).get("paid_units", 0)) +
                   int((s.get("payment") or {}).get("fee_units", 0)) for s in state["steps"])
        unresolved = [s["node"]["id"] for s in state["steps"] if s.get("tx_hash") and not s.get("payment")]
        bill = {"trace_id": state["run_id"], "graph_digest": state["graph_digest"],
                "funding": "buyer_wallet", "wallet": state["wallet"], "status": state["status"],
                "budget_usd": float(Decimal(state["total_units"]) / 10 ** state["decimals"]),
                "total_usd": float(Decimal(paid) / 10 ** state["decimals"]),
                "remaining_budget_usd": float(Decimal(max(0, state["total_units"] - paid)) / 10 ** state["decimals"]),
                "payment_unresolved": unresolved, "steps": steps,
                "created_at": state["created_at"], "completed_at": state.get("completed_at")}
        if state.get("gas_sponsorship"):
            bill["gas_sponsorship"] = state["gas_sponsorship"]
        if state.get("pipeline_job_id"):
            bill["job_id"] = state["pipeline_job_id"]
        # Secrets, inputs and payment authorizations never enter the signed bill.
        # A finished run's bill is signed once and kept: with post-quantum signing on, each
        # signature differs, and "repeated requests return the stored outcome" must hold
        # byte for byte (a pipeline receipt commits to the bill's digest).
        # A run still in progress is not written here (claims compare state_json), so its
        # signature is kept in memory per bill digest: same content, same bytes, in this process.
        digest = hashlib.sha256(_json(bill).encode()).hexdigest()
        kept = state.get("bill_signature") or {}
        if kept.get("digest") == digest:
            bill["signature"] = kept["signature"]
        elif digest in self._bill_signatures:
            bill["signature"] = self._bill_signatures[digest]
        else:
            bill["signature"] = self.signer.sign_object(bill)
            self._bill_signatures[digest] = bill["signature"]
            while len(self._bill_signatures) > 2048:
                self._bill_signatures.pop(next(iter(self._bill_signatures)))
            if state["status"] in ("completed", "failed"):
                state["bill_signature"] = {"digest": digest, "signature": bill["signature"]}
                self.conn.execute("UPDATE studio_paid_runs SET state_json = ? WHERE run_id = ?", (_json(state), state["run_id"]))
                self.conn.commit()
        current = next((s for s in steps if s["status"] not in ("succeeded", "failed")), None)
        return {"trace_id": state["run_id"], "status": state["status"], "busy": busy,
                "bill_of_materials": bill, "next_step": current if state["status"] not in ("completed", "failed") else None,
                "final_result": state.get("final_result", {}), "step_results": step_results,
                "detail": state.get("detail", "")}

    async def advance(self, run_id: str, token: str, body: AdvanceRequest, caller: str,
                      *, managed: bool = False, job_headers: Callable | None = None,
                      broadcaster: Callable | None = None, relay=None) -> dict:
        from aimarket_hub import pipeline_leases
        pipeline_leases.check(self.conn, run_id)
        state, busy = self.load(run_id, token)
        if state.get("executor") == "pipeline.run@v1" and not managed:
            raise HTTPException(409, "this run is managed by pipeline.run@v1")
        # Repeated requests, including a retry after response loss, observe durable state.
        if busy or state["status"] in ("completed", "failed"):
            return self.view(state, busy)
        step = next(s for s in state["steps"] if s["status"] != "succeeded")
        if step["node"]["id"] != body.step_id:
            return self.view(state)
        # A stale browser must not terminate a run that still has money in flight.
        if state["wallet"] and state["wallet"] != body.wallet.lower():
            raise HTTPException(409, "the connected wallet changed")
        if step.get("tx_hash") and body.tx_hash and step["tx_hash"] != body.tx_hash.lower():
            raise HTTPException(409, "a payment is already pending; reconcile it before paying again")
        claimed = returning_one(self.conn,
            "UPDATE studio_paid_runs SET busy = 1, started = 1, updated_at = ? WHERE run_id = ? AND busy = 0 AND state_json = ? RETURNING run_id",
            (time.time(), run_id, _json(state)), commit=True)
        if not claimed:
            fresh, locked = self.load(run_id, token)
            return self.view(fresh, locked)
        try:
            state["wallet"] = body.wallet.lower()
            if managed and step.get("relay_authorization"):
                # A worker may have committed relay bytes, then died before saving
                # the run. Those bytes may already be mined: reconcile past expiry.
                cached = step.get("signed_payment") or relay.cached(state, step)
                if cached:
                    step["signed_payment"] = cached
                    step["tx_hash"] = cached["tx_hash"]
            terms = settle.PaymentTerms(**step["terms"]) if step["terms"] else None
            # A previously broadcast transaction may be reconciled after quote expiry.
            if not (body.tx_hash or step.get("tx_hash")):
                # The quote binds the plan until the run starts. After that each step re-checks its
                # own terms below and pays its own invoice; expiring the whole quote mid-run failed
                # slow graphs after earlier steps had already been paid, free steps included.
                if state["status"] == "quoted" and time.time() > state["expires_at"]:
                    raise ValueError("quote expired; run payment preflight again")
                # Before the first paid step, validate the WHOLE plan again.
                check = state["steps"] if state["status"] == "quoted" else [step]
                for item in check:
                    if self.describe(item["node"], remote=item.get("remote")) != {"terms": item["terms"], "input_schema": item["input_schema"]}:
                        raise ValueError(f"{item['node']['id']}: listing terms changed; run payment preflight again")
            if "resolved_input" not in step:
                value = dict(step["node"].get("input") or {})
                source = step["node"].get("input_from")
                if source:
                    value.setdefault("context", state["results"][source])
                value = resolve(value, state["results"])
                check_input(value, step["input_schema"], dynamic=False)
                step["resolved_input"] = value
            state["status"] = "active"
            if terms:
                if not step.get("invoice") and step.get("remote"):
                    step["invoice"] = step["remote"]["offer"]["invoice"]
                if not step.get("invoice"):
                    if body.tx_hash:
                        raise ValueError("prepare this step before submitting a payment")
                    secret = settle.mint_secret()
                    step["invoice"] = self.invoices.mint(
                        nonce=settle.nonce_for_secret(secret), capability_id=step["node"]["capability_id"],
                        pay_to=terms.pay_to, amount_units=terms.amount_units, ttl_s=settle.invoice_ttl_s(), secret=secret)
                    step["invoice"]["secret"] = secret
                if managed and step.get("relay_authorization") and not step.get("signed_payment"):
                    step["status"] = "relay_pending"
                    self.save(state)  # Recoverable before any provider dispatch.
                    step["signed_payment"] = await relay.payment(state, step)
                    step["tx_hash"] = step["signed_payment"]["tx_hash"]
                    self.save(state)  # Same raw bytes on every retry, including expiry.
                if not (body.tx_hash or step.get("tx_hash") or (managed and step.get("signed_payment"))):
                    if time.time() >= step["invoice"]["expires_at"]:
                        raise ValueError("payment authorization expired; run payment preflight again")
                    step["status"] = "awaiting_payment"
                    self.save(state, unlock=True)
                    return self.view(state)
                signed = step.get("signed_payment") if managed else None
                if signed and not step.get("tx_hash") and time.time() >= step["invoice"]["expires_at"]:
                    raise ValueError("payment authorization expired before broadcast")
                step["tx_hash"] = (step.get("tx_hash") or body.tx_hash or signed["tx_hash"]).lower()
                step["status"] = "payment_pending"
                self.save(state)  # Persist BEFORE chain lookup or any provider dispatch.
                if signed and broadcaster:
                    try:
                        await broadcaster(signed["raw"], step["tx_hash"])
                    except Exception:
                        # It may already be mined, or the broadcast response was lost.
                        # Verify the deterministic hash; never replace the transaction.
                        pass
                try:
                    paid = await asyncio.to_thread(settle.verify_transfer,
                        tx_hash=step["tx_hash"], terms=terms, require_nonce=step["invoice"]["nonce"])
                except settle.PaymentFinal as exc:
                    # Mined and conclusively not a payment (reverted, mined after expiry, the wrong
                    # transfer): waiting cannot change that, so the step stops pointing at it. Nothing
                    # was dispatched. A sponsored transaction is forgotten only if the chain shows it
                    # reverted; the EIP-3009 nonce is then still unused.
                    if managed and step.get("signed_payment") and not await relay.forget_reverted(state, step):
                        state["detail"] = f"Payment not yet verified: {str(exc)[:250]}"
                        self.save(state, unlock=True)
                        return self.view(state)
                    step.setdefault("rejected_payments", []).append({"tx_hash": step["tx_hash"], "reason": str(exc)[:200]})
                    for key in ("tx_hash", "signed_payment", "relay_authorization"):
                        step.pop(key, None)
                    step["status"] = "awaiting_payment"
                    state["detail"] = f"Payment did not pay this step ({str(exc)[:160]}); nothing was dispatched. Pay again."
                    self.save(state, unlock=True)
                    return self.view(state)
                except Exception as exc:
                    # Neither an RPC timeout nor missing confirmations authorizes a second payment.
                    state["detail"] = f"Payment not yet verified: {str(exc)[:250]}"
                    self.save(state, unlock=True)
                    return self.view(state)
                step["payment"] = paid
                if str(paid.get("authorizer", "")).lower() != state["wallet"]:
                    raise ValueError("the payment was made by a different wallet")
                if int(paid["paid_units"]) + int(paid.get("fee_units", 0)) != terms.amount_units:
                    raise ValueError("the payment does not match the approved amount")
            elif body.tx_hash:
                raise ValueError("a free step does not accept a payment")
            step["status"], step["started_at"] = "running", time.time()
            state["detail"] = ""
            self.save(state)  # A crash after this point is never automatically replayed.
            headers = {}
            if terms and not step.get("remote"):
                headers = {"X-Payment": step["tx_hash"], "X-Payment-Nonce": step["invoice"]["nonce"],
                           "X-Payment-Secret": step["invoice"]["secret"]}
            if job_headers:
                headers.update(job_headers())
            node = step["node"]
            payload = {k: node[k] for k in ("product_id", "capability_id", "source_hub")}
            payload.update(input=step["resolved_input"], max_price_usd=terms.amount_usd if terms else 0)
            if step.get("remote"):
                from aimarket_hub import subcontract
                from dataclasses import asdict
                import base64
                if self.jobs and job_headers and not step.get("job"):
                    ctx = self.jobs.join(token=headers[subcontract.JOB_HEADER], grant_secret='',
                                         product_id=node['product_id'], capability_id=node['capability_id'])
                    step['job'] = asdict(ctx)
                    self.save(state)
                status, answer = await self.remote.advance(step, state['wallet'])
                pipeline_leases.check(self.conn, run_id)
                if step.get('job') and self.jobs:
                    receipt = answer['receipt']
                    digest = 'sha256-' + base64.b64encode(hashlib.sha256(_json(receipt).encode()).digest()).decode()
                    self.jobs.finish_node(step['job']['node'], status='captured' if answer['success'] else 'failed',
                        amount_micro=int(Decimal(str(terms.amount_usd)) * 1_000_000) if terms else 0,
                        receipt_digest=digest, work_receipt_id='urn:aimarket:seller-operation:' + receipt['operation_id'])
            else:
                status, answer = await self.invoke(payload, headers, caller)
            success = 200 <= status < 300 and answer.get("success", answer.get("ok", False)) is True
            step.update(status="succeeded" if success else "failed", success=success,
                        status_code=status, finished_at=time.time(), receipt=answer.get("receipt"))
            result = answer.get("result", answer.get("output", {}))
            step["response_result"] = result
            step["result_sha256"] = result_sha256(result)
            if isinstance(answer.get("job"), dict):
                step["job"] = answer["job"]
            if success:
                state["results"][node["id"]] = result
                state["final_result"] = result
                if all(s["status"] == "succeeded" for s in state["steps"]):
                    state["status"], state["completed_at"] = "completed", time.time()
            else:
                step["error"] = str(answer.get("detail") or answer.get("error") or f"HTTP {status}")[:500]
                state["status"], state["completed_at"] = "failed", time.time()
        except pipeline_leases.LeaseLost:
            raise
        except Exception as exc:
            from aimarket_hub.pipeline_relay import RelayPending
            if isinstance(exc, RelayPending):
                step['status'], state['detail'] = 'relay_pending', str(exc)
                self.save(state, unlock=True)
                return self.view(state)
            from aimarket_hub.peer_operations import RemotePending
            if isinstance(exc, RemotePending):
                step['status'], state['detail'] = 'remote_pending', str(exc)
                state['status'] = 'reconciliation_required' if exc.reconciliation else 'active'
                self.save(state, unlock=True)
                return self.view(state)
            if not isinstance(exc, (ValueError, SchemaError)):
                state['status'] = 'reconciliation_required'
                self.save(state)
                raise
            step.update(status="failed", success=False, error=str(exc)[:500])
            state["status"], state["completed_at"] = "failed", time.time()
        except BaseException:
            # Keep the claim: the upstream may have executed. Operators reconcile this
            # state using the stored transaction and invoice; retries must not dispatch.
            state["status"] = "reconciliation_required"
            self.save(state)
            raise
        self.save(state, unlock=True)
        return self.view(state)


def attach_paid_routes(app, *, studio: PaidStudio, caller: Callable, allow_request: Callable) -> None:
    @app.post("/studio/preflight")
    async def preflight(body: PreflightRequest, request: Request):
        if not allow_request("studio:" + caller(request)):
            raise HTTPException(429, "slow down")
        return JSONResponse(await studio.preflight_external(body), headers={"Cache-Control": "no-store"})

    @app.get("/studio/paid-runs/{run_id}")
    async def read_run(run_id: str, x_studio_run_token: str = Header(default="")):
        state, busy = studio.load(run_id, x_studio_run_token)
        return JSONResponse(studio.view(state, busy), headers={"Cache-Control": "no-store"})

    @app.post("/studio/paid-runs/{run_id}/advance")
    async def advance(run_id: str, body: AdvanceRequest, request: Request, x_studio_run_token: str = Header(default="")):
        # Each advance may verify a caller-supplied hash against every settlement RPC.
        if not allow_request("studio-advance:" + caller(request)):
            raise HTTPException(429, "slow down")
        result = await studio.advance(run_id, x_studio_run_token, body, caller(request))
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
